"""
Dashboard revenue tests against the seeded database (database/seed.sql).
Run inside the backend container: docker compose exec backend pytest
"""
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.reservations import to_cents

SUNSET = ("sunset@propertyflow.com", "client_a_2024")  # tenant-a
OCEAN = ("ocean@propertyflow.com", "client_b_2024")  # tenant-b


@pytest.fixture(scope="module")
def client():
    # - one client for the module: the DB pool is bound to the client's event loop
    with TestClient(app) as c:
        yield c


def login(client, creds):
    email, password = creds
    res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 200, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def summary(client, headers, **params):
    return client.get("/api/v1/dashboard/summary", params=params, headers=headers)


# --- money ---

def test_to_cents_rounds_half_up_once():
    assert to_cents(Decimal("0.005")) == Decimal("0.01")
    assert to_cents(Decimal("333.333") * 2 + Decimal("333.334")) == Decimal("1000.00")


def test_total_is_exact_cents_string(client):
    body = summary(client, login(client, SUNSET), property_id="prop-001").json()
    assert body["total_revenue"] == "2250.00"
    assert body["currency"] == "USD"
    assert body["reservations_count"] == 4


# --- tenant isolation ---

def test_same_property_id_is_isolated_per_tenant(client):
    # prop-001 exists in both tenants; only tenant-a has reservations on it
    assert summary(client, login(client, SUNSET), property_id="prop-001").json()["total_revenue"] == "2250.00"
    assert summary(client, login(client, OCEAN), property_id="prop-001").json()["total_revenue"] == "0.00"


def test_tenant_cannot_read_other_tenants_property(client):
    body = summary(client, login(client, SUNSET), property_id="prop-005").json()
    assert body["total_revenue"] == "0.00"
    assert body["reservations_count"] == 0


def test_properties_are_listed_per_tenant(client):
    a = client.get("/api/v1/dashboard/properties", headers=login(client, SUNSET)).json()["items"]
    b = client.get("/api/v1/dashboard/properties", headers=login(client, OCEAN)).json()["items"]
    assert {p["name"] for p in a} == {"Beach House Alpha", "City Apartment Downtown", "Country Villa Estate"}
    assert {p["name"] for p in b} == {"Mountain Lodge Beta", "Lakeside Cottage", "Urban Loft Modern"}


# --- time zones ---

def test_month_is_cut_in_property_time_zone(client):
    # res-tz-1 checks in 2024-02-29 23:30 UTC, which is 1 March in Europe/Paris
    headers = login(client, SUNSET)
    march = summary(client, headers, property_id="prop-001", month=3, year=2024).json()
    february = summary(client, headers, property_id="prop-001", month=2, year=2024).json()
    assert march["total_revenue"] == "2250.00"
    assert march["reservations_count"] == 4
    assert february["total_revenue"] == "0.00"


def test_month_without_year_is_rejected(client):
    res = summary(client, login(client, SUNSET), property_id="prop-001", month=3)
    assert res.status_code == 422


# --- auth ---

@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer mock-token-123"}])
def test_missing_or_forged_token_is_rejected(client, headers):
    assert summary(client, headers, property_id="prop-001").status_code == 401


@pytest.mark.parametrize("email,password", [
    ("sunset@propertyflow.com", "wrong"),
    ("candidate@propertyflow.com", "anything"),
])
def test_bad_credentials_are_rejected(client, email, password):
    res = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert res.status_code == 401


def test_circuit_breaker_reset_requires_admin(client):
    res = client.post("/api/v1/circuit-breaker/reset", headers=login(client, SUNSET))
    assert res.status_code == 403
