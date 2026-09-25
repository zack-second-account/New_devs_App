from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any
from app.services.cache import get_revenue_summary
from app.services.reservations import RevenueUnavailableError
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    # - fell back to a shared "default_tenant".
    # - auth now guarantees a verified tenant; use it directly.
    tenant_id = current_user.tenant_id
    
    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id)
    except RevenueUnavailableError as e:
        raise HTTPException(status_code=503, detail=str(e))
    
    # - float() on money reintroduced binary rounding errors.
    # - send the exact 2-decimal string.
    # - cost: clients parse a string; exact beats convenient for money
    return {
        "property_id": revenue_data['property_id'],
        "total_revenue": revenue_data['total'],
        "currency": revenue_data['currency'],
        "reservations_count": revenue_data['count']
    }
