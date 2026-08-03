from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from api.utils.schemas import TenantConfigPayload
from api.utils.models import TenantConfig
from api.utils.database import get_db
from api.utils.logger import logger, trace_id_var

router = APIRouter(prefix="/config", tags=["Configuration"])


@router.post("/rules", status_code=200)
async def upsert_tenant_rules(
    payload: TenantConfigPayload, db: AsyncSession = Depends(get_db)
):
    """Upsert tenant dunning rules into the database.

    Args:
        payload (TenantConfigPayload): The tenant configuration payload containing
            the tenant identifier, active flag, and rule set to persist.
        db (AsyncSession, optional): The database session used to merge the
            tenant configuration. Defaults to Depends(get_db).

    Returns:
        dict: A success payload including the tenant identifier, trace identifier,
            and the applied rules that were stored.
    """
    logger.info(f"Updating rules for tenant: {payload.tenant_id}")
    new_config = TenantConfig(
        tenant_id=payload.tenant_id,
        is_active=payload.is_active,
        dunning_rules=payload.rules.model_dump(),
    )
    await db.merge(new_config)
    await db.commit()

    return {
        "status": "success",
        "message": "Rules updated successfully",
        "tenant_id": payload.tenant_id,
        "trace_id": trace_id_var.get(),
        "applied_rules": payload.rules.model_dump(),
    }
