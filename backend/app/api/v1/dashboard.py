from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Dict, Any, Optional
from app.services.cache import get_revenue_summary
from app.services.reservations import RevenueUnavailableError
from app.core.auth import authenticate_request as get_current_user

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(None, ge=1, le=12),
    year: Optional[int] = Query(None, ge=2000, le=2100),
    current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    
    # - fell back to a shared "default_tenant".
    # - auth now guarantees a verified tenant; use it directly.
    tenant_id = current_user.tenant_id
    
    try:
        revenue_data = await get_revenue_summary(property_id, tenant_id, month=month, year=year)
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
