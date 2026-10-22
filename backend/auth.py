import os
from threading import Lock
from typing import Annotated
from uuid import uuid4

import firebase_admin
from firebase_admin import auth, exceptions
from firebase_admin import credentials as firebase_credentials
from google.auth.exceptions import GoogleAuthError
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

from database import get_connection

router = APIRouter(prefix="/api/account", tags=["account"])
bearer = HTTPBearer(auto_error=False)
initialization_lock = Lock()


def firebase_app():
    with initialization_lock:
        try:
            return firebase_admin.get_app("kinu-auth")
        except ValueError:
            path=os.getenv('FIREBASE_SERVICE_ACCOUNT_PATH')
            credential=firebase_credentials.Certificate(path) if path else None
            return firebase_admin.initialize_app(credential=credential,options={
                "projectId": os.getenv("FIREBASE_PROJECT_ID"), "httpTimeout": 10
            }, name="kinu-auth")


def current_identity(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if credentials is None:
        raise HTTPException(401, {"code": "LOGIN_REQUIRED", "message": "請先登入。"})
    try:
        identity = auth.verify_id_token(credentials.credentials, app=firebase_app(), check_revoked=True)
    except auth.CertificateFetchError:
        raise HTTPException(503, {"code": "AUTH_UNAVAILABLE", "message": "登入驗證暫時無法使用，請稍後再試。"}) from None
    except (auth.InvalidIdTokenError, auth.RevokedIdTokenError, auth.UserDisabledError, auth.UserNotFoundError, ValueError):
        raise HTTPException(401, {"code": "INVALID_TOKEN", "message": "登入已失效，請重新登入。"}) from None
    except (exceptions.FirebaseError, GoogleAuthError, OSError):
        raise HTTPException(503, {"code": "AUTH_UNAVAILABLE", "message": "登入驗證暫時無法使用，請稍後再試。"}) from None
    if not identity.get("uid") or not identity.get("email"):
        raise HTTPException(401, {"code": "INVALID_TOKEN", "message": "無法取得會員身分。"})
    return identity


class SyncAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")


def public_account(row):
    if not row["active"]:
        raise HTTPException(403, {"code": "ACCOUNT_DISABLED", "message": "此會員帳號已停用，請聯絡客服。"})
    return {"id": row["id"], "email": row["email"], "emailVerified": row["email_verified"],
            "displayName": row["display_name"], "role": row["role"]}


@router.put("")
def sync_account(body: SyncAccount, identity=Depends(current_identity), connection=Depends(get_connection)):
    row = connection.execute("""
        INSERT INTO users (id, firebase_uid, email, email_verified, display_name)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (firebase_uid) DO UPDATE SET email = EXCLUDED.email,
            email_verified = EXCLUDED.email_verified, display_name = EXCLUDED.display_name, updated_at = now()
        RETURNING *
    """, (uuid4(), identity["uid"], identity["email"], identity.get("email_verified", False), identity.get("name"))).fetchone()
    return public_account(row)


@router.get("")
def get_account(identity=Depends(current_identity), connection=Depends(get_connection)):
    row = connection.execute("SELECT * FROM users WHERE firebase_uid = %s", (identity["uid"],)).fetchone()
    if row is None:
        raise HTTPException(404, {"code": "ACCOUNT_NOT_FOUND", "message": "會員資料尚未建立。"})
    return public_account(row)
