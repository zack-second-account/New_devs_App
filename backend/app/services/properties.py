from typing import Any, Dict, List

from sqlalchemy import text


async def list_properties(tenant_id: str) -> List[Dict[str, Any]]:
    """
    Lists the properties owned by one tenant.
    """
    # - frontend hardcoded every tenant's properties, so each client saw the other's property names
    # - tenant filter lives in SQL, never in the client
    from app.core.database_pool import db_pool
    await db_pool.initialize()

    async with db_pool.get_session() as session:
        result = await session.execute(
            text("SELECT id, name, timezone FROM properties WHERE tenant_id = :tenant_id ORDER BY name, id"),
            {"tenant_id": tenant_id},
        )
        return [{"id": r.id, "name": r.name, "timezone": r.timezone} for r in result.fetchall()]
