import hmac
import os
import re
import secrets

import httpx
from fastapi import Depends

from app.core.errors import error
from app.modules.accounts.dependencies import current_identity
from app.modules.accounts.service import verified_phone
from app.modules.bookings.queries import lock_member, owned_draft


def verified_identity(identity=Depends(current_identity)):
    if not identity.get('email_verified'):
        error(403, 'EMAIL_VERIFICATION_REQUIRED', '請先到會員中心完成登入 Email 驗證。')
    return identity


def contact_values(data):
    return data.get('contactEmail', '').strip().lower(), data.get('contactPhone', '').strip()


def contact_status(connection, row):
    data = row['data']
    email, phone = contact_values(data)
    account = connection.execute('SELECT email,email_verified,display_name,phone_number,phone_verified_at FROM users WHERE id=%s',
                                 (row['user_id'],)).fetchone()
    member_email = bool(email and account['email_verified'] and email == account['email'].lower())
    member_phone = bool(phone and account['phone_verified_at'] and phone == account['phone_number'])
    if data.get('contactMode') == 'member':
        return {'email': member_email, 'phone': member_phone,
                'memberName': data.get('contactName', '').strip() == (account['display_name'] or '').strip()}
    proofs = connection.execute('''SELECT channel,value FROM booking_contact_verifications
        WHERE draft_id=%s AND verified_at IS NOT NULL AND
        ((channel='email' AND value=%s) OR (channel='phone' AND value=%s))''',
        (row['id'], email, phone)).fetchall()
    verified = {proof['channel'] for proof in proofs}
    return {'email': member_email or 'email' in verified, 'phone': member_phone or 'phone' in verified, 'memberName': True}


def require_contact(connection, row):
    data = row['data']
    email, phone = contact_values(data)
    if not data.get('contactName', '').strip() or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email) or not re.fullmatch(r'(?:\+8869\d{8}|\+81[789]0\d{8})', phone):
        error(422, 'INVALID_CONTACT', '請填寫聯絡姓名、有效 Email 和台灣或日本手機。')
    if not all(contact_status(connection, row).values()):
        error(422, 'CONTACT_VERIFICATION_REQUIRED', '請在第六步確認姓名並完成聯絡 Email 與手機驗證。')


def code_hash(key, draft_id, email, code):
    return hmac.digest(key.encode(), f'{draft_id}:{email}:{code}'.encode(), 'sha256').hex()


def contact_draft(connection, draft_id, member, version):
    row = owned_draft(connection, draft_id, member, True)
    if row['version'] != version:
        error(409, 'DRAFT_VERSION_CONFLICT', '草稿已在其他地方更新，請重新整理後再驗證。')
    return row


def send_email(connection, draft_id, member, version):
    lock_member(connection, member)
    row = contact_draft(connection, draft_id, member, version)
    email, _ = contact_values(row['data'])
    if row['data'].get('contactMode') != 'other' or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', email):
        error(422, 'INVALID_CONTACT_EMAIL', '請先保存有效的其他聯絡 Email。')
    if contact_status(connection, row)['email']:
        return
    key, sender = os.getenv('RESEND_API_KEY'), os.getenv('RESEND_FROM_EMAIL')
    if not key or not sender:
        error(503, 'CONTACT_EMAIL_UNAVAILABLE', '聯絡 Email 寄信服務尚未設定。')
    recent = connection.execute('''SELECT max(v.sent_at) AS latest FROM booking_contact_verifications v
        JOIN booking_drafts d ON d.id=v.draft_id
        WHERE d.user_id=%s AND v.channel='email' AND v.sent_at>now()-interval '1 minute' ''', (member,)).fetchone()
    if recent['latest']:
        error(429, 'CONTACT_EMAIL_RATE_LIMIT', '寄送過於頻繁，請稍後再試。')
    code = f'{secrets.randbelow(1_000_000):06d}'
    connection.execute('''INSERT INTO booking_contact_verifications(draft_id,channel,value,code_hash,expires_at,sent_at)
        VALUES (%s,'email',%s,%s,now()+interval '10 minutes',now())
        ON CONFLICT (draft_id,channel,value) DO UPDATE SET code_hash=excluded.code_hash,
        expires_at=excluded.expires_at,sent_at=excluded.sent_at,attempts=0''',
        (draft_id,email,code_hash(key,draft_id,email,code)))
    connection.commit()
    try:
        response = httpx.post('https://api.resend.com/emails', timeout=8,
                              headers={'Authorization': f'Bearer {key}'},
                              json={'from':sender,'to':[email],'subject':'KINU TABI 預約聯絡 Email 驗證碼',
                                    'text':f'你的預約聯絡 Email 驗證碼為 {code}，10 分鐘內有效。'})
        response.raise_for_status()
    except httpx.HTTPError:
        error(503, 'CONTACT_EMAIL_UNAVAILABLE', '驗證信寄送失敗，請稍後再試。')


def confirm_email(connection, draft_id, member, version, code):
    row = contact_draft(connection, draft_id, member, version)
    email, _ = contact_values(row['data'])
    key = os.getenv('RESEND_API_KEY')
    if row['data'].get('contactMode') != 'other' or not key:
        return False
    proof = connection.execute('''SELECT code_hash FROM booking_contact_verifications
        WHERE draft_id=%s AND channel='email' AND value=%s AND expires_at>now() AND attempts<5
        AND verified_at IS NULL''', (draft_id,email)).fetchone()
    if not proof:
        return False
    valid = hmac.compare_digest(proof['code_hash'], code_hash(key,draft_id,email,code))
    connection.execute('''UPDATE booking_contact_verifications SET attempts=attempts+1,
        verified_at=CASE WHEN %s THEN now() ELSE NULL END
        WHERE draft_id=%s AND channel='email' AND value=%s''', (valid,draft_id,email))
    connection.commit()
    return valid


def confirm_phone(connection, draft_id, member, version, identity, token):
    row = contact_draft(connection, draft_id, member, version)
    phone, proof = verified_phone(token,identity)
    if row['data'].get('contactMode') != 'other' or phone != contact_values(row['data'])[1]:
        error(422, 'CONTACT_PHONE_MISMATCH', '已驗證的手機和目前聯絡手機不符。')
    if contact_status(connection,row)['phone']:
        return
    used = connection.execute('''INSERT INTO booking_contact_phone_proofs(firebase_uid,auth_time,draft_id)
        VALUES (%s,%s,%s) ON CONFLICT DO NOTHING RETURNING draft_id''',
        (proof['uid'],proof['auth_time'],draft_id)).fetchone()
    if not used:
        error(409, 'PHONE_PROOF_USED', '此驗證已使用，請重新收取簡訊驗證碼。')
    connection.execute('''INSERT INTO booking_contact_verifications(draft_id,channel,value,verified_at)
        VALUES (%s,'phone',%s,now()) ON CONFLICT DO NOTHING''', (draft_id,phone))
