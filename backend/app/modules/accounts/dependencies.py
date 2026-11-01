from app.core.database import get_connection
from app.integrations.firebase import firebase_app
from app.modules.accounts.service import public_account
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth, exceptions
from google.auth.exceptions import GoogleAuthError
from typing import Annotated
from uuid import UUID


bearer = HTTPBearer(auto_error=False)


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
    if not identity.get("uid") or not identity.get("email") or identity.get('firebase', {}).get('sign_in_provider') == 'phone':
        raise HTTPException(401, {"code": "INVALID_TOKEN", "message": "無法取得會員身分。"})
    return identity


def current_member(identity=Depends(current_identity), connection=Depends(get_connection)):
    row = connection.execute('SELECT * FROM users WHERE firebase_uid = %s', (identity['uid'],)).fetchone()
    if row is None:
        raise HTTPException(403, {'code': 'ACCOUNT_NOT_INITIALIZED', 'message': '請先進入會員中心同步帳號。'})
    public_account(row)
    return row['id']


Member = Annotated[UUID, Depends(current_member)]
