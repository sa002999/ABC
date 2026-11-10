from fastapi import HTTPException
from uuid import uuid4


def public_account(row):
    if not row["active"]:
        raise HTTPException(403, {"code": "ACCOUNT_DISABLED", "message": "此會員帳號已停用，請聯絡客服。"})
    return {"id": row["id"], "email": row["email"], "emailVerified": row["email_verified"],
            "displayName": row["display_name"], "role": row["role"],
            "phoneNumber": row.get('phone_number'), "phoneVerified": bool(row.get('phone_verified_at'))}


def sync_account(body, identity, connection):
    row = connection.execute("""
        INSERT INTO users (id, firebase_uid, email, email_verified, display_name)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (firebase_uid) DO UPDATE SET email = EXCLUDED.email,
            email_verified = EXCLUDED.email_verified, updated_at = now()
        RETURNING *
    """, (uuid4(), identity["uid"], identity["email"], identity.get("email_verified", False), identity.get("name"))).fetchone()
    return public_account(row)


def get_account(identity, connection):
    row = connection.execute("SELECT * FROM users WHERE firebase_uid = %s", (identity["uid"],)).fetchone()
    if row is None:
        raise HTTPException(404, {"code": "ACCOUNT_NOT_FOUND", "message": "會員資料尚未建立。"})
    return public_account(row)


def update_profile(body, identity, connection):
    get_account(identity, connection)
    row = connection.execute('UPDATE users SET display_name=%s, updated_at=now() WHERE firebase_uid=%s RETURNING *',
                             (body.display_name, identity['uid'])).fetchone()
    return public_account(row)


def verified_phone(phone_token, identity):
    import re
    import time
    from app.integrations.firebase import firebase_app
    from firebase_admin import auth, exceptions
    from google.auth.exceptions import GoogleAuthError

    now = time.time()
    try:
        proof = auth.verify_id_token(phone_token, app=firebase_app(), check_revoked=True)
    except auth.CertificateFetchError:
        raise HTTPException(503, {'code': 'AUTH_UNAVAILABLE', 'message': '手機驗證服務暫時無法使用，請稍後重試。'}) from None
    except (auth.InvalidIdTokenError, auth.RevokedIdTokenError, auth.UserDisabledError, auth.UserNotFoundError, ValueError):
        raise HTTPException(422, {'code': 'INVALID_PHONE_PROOF', 'message': '手機驗證已失效，請重新收取驗證碼。'}) from None
    except (exceptions.FirebaseError, GoogleAuthError, OSError):
        raise HTTPException(503, {'code': 'AUTH_UNAVAILABLE', 'message': '手機驗證服務暫時無法使用，請稍後重試。'}) from None
    phone = proof.get('phone_number', '')
    if (proof.get('firebase', {}).get('sign_in_provider') != 'phone' or not proof.get('uid')
            or proof['uid'] == identity['uid'] or proof.get('email')
            or not 0 <= now-proof.get('auth_time', 0) <= 300
            or not re.fullmatch(r'(?:\+8869\d{8}|\+81[789]0\d{8})', phone)):
        raise HTTPException(422, {'code': 'INVALID_PHONE_PROOF', 'message': '請使用台灣或日本手機重新完成簡訊驗證。'})
    return phone, proof


def bind_phone(body, identity, connection):
    import time
    import psycopg

    account = get_account(identity, connection)
    if identity.get('firebase', {}).get('sign_in_provider') != 'password' or not 0 <= time.time()-identity.get('auth_time', 0) <= 300:
        raise HTTPException(401, {'code': 'REAUTH_REQUIRED', 'message': '請先以 Email 與密碼重新驗證身分，再綁定手機。'})
    phone, proof = verified_phone(body.phone_token, identity)
    try:
        with connection.transaction():
            connection.execute('SELECT id FROM users WHERE id=%s FOR UPDATE', (account['id'],))
            used = connection.execute('''INSERT INTO member_phone_proofs(firebase_uid,auth_time,user_id,phone_number)
                VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING user_id''',
                (proof['uid'], proof['auth_time'], account['id'], phone)).fetchone()
            if not used:
                # Allow retry of this successful binding, but never rebind an old proof.
                prior = connection.execute('SELECT user_id FROM member_phone_proofs WHERE firebase_uid=%s AND auth_time=%s',
                                           (proof['uid'], proof['auth_time'])).fetchone()
                current = connection.execute('SELECT * FROM users WHERE id=%s', (account['id'],)).fetchone()
                if prior['user_id'] == current['id'] and current['phone_number'] == phone:
                    return public_account(current)
                raise HTTPException(409, {'code': 'PHONE_PROOF_USED', 'message': '此驗證已使用，請重新收取簡訊驗證碼。'})
            row = connection.execute('UPDATE users SET phone_number=%s,phone_verified_at=now(),updated_at=now() WHERE id=%s RETURNING *',
                                     (phone, account['id'])).fetchone()
    except psycopg.errors.UniqueViolation:
        raise HTTPException(409, {'code': 'PHONE_ALREADY_BOUND', 'message': '此手機已綁定其他會員，請使用其他號碼。'}) from None
    return public_account(row)
