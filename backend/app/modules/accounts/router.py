from app.core.database import get_connection
from app.modules.accounts import service as service
from app.modules.accounts.dependencies import current_identity
from app.modules.accounts.schemas import SyncAccount
from fastapi import APIRouter, Depends


router = APIRouter(prefix='/api/account', tags=['account'])

@router.put('')
def sync_account(body: SyncAccount, identity=Depends(current_identity), connection=Depends(get_connection)):
    return service.sync_account(body=body, identity=identity, connection=connection)

@router.get('')
def get_account(identity=Depends(current_identity), connection=Depends(get_connection)):
    return service.get_account(identity=identity, connection=connection)
