from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Any, List


class RevenueUnavailableError(Exception):
    """Revenue could not be read from the database."""


def to_cents(amount) -> Decimal:
    # - amounts are NUMERIC(10,3) (sub-cent) and the API sent a float, so totals drifted by cents.
    # - sum exactly in SQL, round once to cents here, half-up.
    # - cost: sub-cent detail stays in the DB only
    return Decimal(amount).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

async def calculate_monthly_revenue(property_id: str, month: int, year: int, db_session=None) -> Decimal:
    """
    Calculates revenue for a specific month.
    """

    start_date = datetime(year, month, 1)
    if month < 12:
        end_date = datetime(year, month + 1, 1)
    else:
        end_date = datetime(year + 1, 1, 1)
        
    print(f"DEBUG: Querying revenue for {property_id} from {start_date} to {end_date}")

    # SQL Simulation (This would be executed against the actual DB)
    query = """
        SELECT SUM(total_amount) as total
        FROM reservations
        WHERE property_id = $1
        AND tenant_id = $2
        AND check_in_date >= $3
        AND check_in_date < $4
    """
    
    # In production this query executes against a database session.
    # result = await db.fetch_val(query, property_id, tenant_id, start_date, end_date)
    # return result or Decimal('0')
    
    return Decimal('0') # Placeholder for now until DB connection is finalized

async def calculate_total_revenue(property_id: str, tenant_id: str) -> Dict[str, Any]:
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
                query = text("""
                    SELECT
                        currency,
                        SUM(total_amount) as total_revenue,
                        COUNT(*) as reservation_count
                    FROM reservations
                    WHERE property_id = :property_id AND tenant_id = :tenant_id
                    GROUP BY currency
                """)

                result = await session.execute(query, {
                    "property_id": property_id,
                    "tenant_id": tenant_id
                })
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
