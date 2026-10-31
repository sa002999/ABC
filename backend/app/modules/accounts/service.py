from fastapi import HTTPException
from uuid import uuid4


def public_account(row):
    if not row["active"]:
        raise HTTPException(403, {"code": "ACCOUNT_DISABLED", "message": "此會員帳號已停用，請聯絡客服。"})
    return {"id": row["id"], "email": row["email"], "emailVerified": row["email_verified"],
            "displayName": row["display_name"], "role": row["role"]}


def sync_account(body, identity, connection):
    row = connection.execute("""
        INSERT INTO users (id, firebase_uid, email, email_verified, display_name)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (firebase_uid) DO UPDATE SET email = EXCLUDED.email,
            email_verified = EXCLUDED.email_verified, display_name = EXCLUDED.display_name, updated_at = now()
        RETURNING *
    """, (uuid4(), identity["uid"], identity["email"], identity.get("email_verified", False), identity.get("name"))).fetchone()
    return public_account(row)


def get_account(identity, connection):
    row = connection.execute("SELECT * FROM users WHERE firebase_uid = %s", (identity["uid"],)).fetchone()
    if row is None:
        raise HTTPException(404, {"code": "ACCOUNT_NOT_FOUND", "message": "會員資料尚未建立。"})
    return public_account(row)
