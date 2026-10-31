from fastapi import HTTPException


def missing_session():
    raise HTTPException(404, {'code': 'SESSION_NOT_FOUND', 'message': '找不到這個試穿工作階段。'})


def owned_session(session_id, member, connection, lock=False):
    row = connection.execute('SELECT * FROM try_on_sessions WHERE id=%s AND user_id=%s' + (' FOR UPDATE' if lock else ''),
                             (session_id, member)).fetchone()
    if not row:
        missing_session()
    return row
