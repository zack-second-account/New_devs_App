from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List, Optional


class RevenueUnavailableError(Exception):
    """Revenue could not be read from the database."""


def to_cents(amount) -> Decimal:
    # - amounts are NUMERIC(10,3) (sub-cent) and the API sent a float, so totals drifted by cents.
    # - sum exactly in SQL, round once to cents here, half-up.
    # - cost: sub-cent detail stays in the DB only
    return Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

async def calculate_monthly_revenue(property_id: str, tenant_id: str, month: int, year: int) -> Dict[str, Any]:
    """
    Calculates revenue for a specific month in the property's local time zone.
    """
    # - old stub used naive UTC month bounds and always returned 0
    # - res-tz-1 checks in 2024-02-29 23:30 UTC = 1 March in Paris, so March totals were wrong
    return await calculate_total_revenue(property_id, tenant_id, month=month, year=year)

async def calculate_total_revenue(
    property_id: str, tenant_id: str, month: Optional[int] = None, year: Optional[int] = None
) -> Dict[str, Any]:
    """
    Aggregates revenue from database.
    """
    try:
        # - a new pool per request leaked engines (up to 50 connections each).
        # - one shared pool.
        from app.core.database_pool import db_pool
        await db_pool.initialize()
        
        if db_pool.session_factory:
            async with db_pool.get_session() as session:
                # Use SQLAlchemy text for raw SQL
                from sqlalchemy import text
                
                # - currency was hardcoded to USD.
                # - read it from the rows; GROUP BY currency surfaces mixed currencies.
                # - month boundaries are evaluated in the property's own time zone (properties.timezone).
                # - cost: expression on check_in_date skips the index; fine at this size
                # - upgrade path: precompute UTC bounds per property
                query = text("""
                    SELECT
                        r.currency,
                        SUM(r.total_amount) as total_revenue,
                        COUNT(*) as reservation_count
                    FROM reservations r
                    JOIN properties p ON p.id = r.property_id AND p.tenant_id = r.tenant_id
                    WHERE r.property_id = :property_id AND r.tenant_id = :tenant_id
                      AND (
                        CAST(:month AS int) IS NULL
                        OR date_trunc('month', r.check_in_date AT TIME ZONE p.timezone)
                           = make_timestamp(CAST(:year AS int), CAST(:month AS int), 1, 0, 0, 0)
                      )
                    GROUP BY r.currency
                """)
                params = {"property_id": property_id, "tenant_id": tenant_id, "month": month, "year": year}

                result = await session.execute(query, params)
                rows = result.fetchall()

                if len(rows) > 1:
                    # - refuse rather than add EUR to USD; FX conversion is out of scope
                    raise RevenueUnavailableError("Mixed currencies for one property cannot be summed")

                if not rows:
                    return {
                        "property_id": property_id,
                        "tenant_id": tenant_id,
                        "total": "0.00",
                        "currency": "USD",
                        "count": 0
                    }

                row = rows[0]
                return {
                    "property_id": property_id,
                    "tenant_id": tenant_id,
                    "total": str(to_cents(row.total_revenue)),
                    "currency": row.currency,
                    "count": row.reservation_count
                }
        else:
            raise Exception("Database pool not available")
            
    except Exception as e:
        # - any DB error returned hardcoded per-property totals as real numbers, and they were cached for 5 minutes.
        # - fail loudly; the endpoint returns 503 and nothing is cached.
        # - cost: an outage shows an error, never a wrong figure
        print(f"Database error for {property_id} (tenant: {tenant_id}): {e}")
        raise RevenueUnavailableError("Revenue data is temporarily unavailable") from e
