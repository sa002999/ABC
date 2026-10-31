"""Website-managed personal credentials; raw tokens are never persisted."""
import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, ConfigDict
from app.core.database import get_connection
from app.core.errors import error
from app.modules.accounts.dependencies import bearer, current_identity
from fastapi.security import HTTPAuthorizationCredentials

router = APIRouter(tags=['MCP account'])


class Confirmation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    confirmed: Literal[True]


def owner(identity=Depends(current_identity), connection=Depends(get_connection)):
    row = connection.execute('SELECT id,active FROM users WHERE firebase_uid=%s FOR UPDATE', (identity['uid'],)).fetchone()
    if not row or not row['active']:
        error(403, 'ACCOUNT_UNAVAILABLE', '請先進入會員中心同步有效帳號。')
    if not identity.get('email_verified'):
        error(403, 'EMAIL_VERIFICATION_REQUIRED', '請先完成 Email 驗證並重新登入。')
    connection.execute('UPDATE users SET email_verified=true WHERE id=%s AND NOT email_verified', (row['id'],))
    return row['id']


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


def token_state(row):
    return {'valid': bool(row and not row['revoked_at'] and row['expires_at'] > datetime.now(timezone.utc)),
            'expiresAt': row['expires_at'] if row else None, 'createdAt': row['created_at'] if row else None}


@router.get('/api/account/mcp-config')
def config():
    return {'endpoint': os.getenv('MCP_ENDPOINT', 'http://127.0.0.1:3001/mcp'),
            'instructions': '以 Streamable HTTP 連線。公開目錄可不帶 token；會員功能使用 Authorization: Bearer <本人 token>。勿將 token 貼進對話。'}


@router.get('/api/account/mcp-token')
def metadata(_member=Depends(owner), connection=Depends(get_connection)):
    return token_state(connection.execute('SELECT created_at,expires_at,revoked_at FROM mcp_tokens WHERE user_id=%s', (_member,)).fetchone())


def issue(member, connection, rotate=False):
    row = connection.execute('SELECT created_at,expires_at,revoked_at FROM mcp_tokens WHERE user_id=%s', (member,)).fetchone()
    if token_state(row)['valid'] and not rotate:
        error(409, 'TOKEN_ALREADY_EXISTS', '已有有效 token，請使用重建操作。')
    token = 'kt_mcp_' + secrets.token_urlsafe(32)
    expires = datetime.now(timezone.utc) + timedelta(days=90)
    saved = connection.execute('''INSERT INTO mcp_tokens(user_id,token_hash,expires_at) VALUES (%s,%s,%s)
        ON CONFLICT(user_id) DO UPDATE SET token_hash=EXCLUDED.token_hash,created_at=now(),
        expires_at=EXCLUDED.expires_at,revoked_at=NULL RETURNING created_at,expires_at,revoked_at''',
        (member, digest(token), expires)).fetchone()
    return {**token_state(saved), 'token': token}


@router.post('/api/account/mcp-token')
def create(body: Confirmation, member=Depends(owner), connection=Depends(get_connection)):
    return issue(member, connection)


@router.post('/api/account/mcp-token/rotate')
def rotate(body: Confirmation, member=Depends(owner), connection=Depends(get_connection)):
    return issue(member, connection, rotate=True)


@router.delete('/api/account/mcp-token')
def revoke(body: Confirmation, member=Depends(owner), connection=Depends(get_connection)):
    connection.execute('UPDATE mcp_tokens SET revoked_at=now() WHERE user_id=%s', (member,))
    return {'valid': False}


def mcp_member(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)], connection=Depends(get_connection)) -> UUID:
    token = credentials.credentials if credentials else ''
    if not re.fullmatch(r'kt_mcp_[A-Za-z0-9_-]{43}', token):
        error(401, 'MCP_TOKEN_REQUIRED', '請在 MCP 連線設定提供有效的本人 token。')
    row = connection.execute('''SELECT u.id FROM mcp_tokens t JOIN users u ON u.id=t.user_id
        WHERE t.token_hash=%s AND t.revoked_at IS NULL AND t.expires_at>now() AND u.active AND u.email_verified''', (digest(token),)).fetchone()
    if not row:
        error(401, 'INVALID_MCP_TOKEN', 'MCP token 已到期、撤銷或無效，請回會員中心管理。')
    return row['id']


@router.get('/api/mcp/member')
def member_status(response: Response, member=Depends(mcp_member)):
    response.headers['Cache-Control'] = 'no-store'
    return {'authenticated': True, 'channel': 'MCP'}
