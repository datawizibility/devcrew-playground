import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.security import create_access_token, hash_password, verify_password


def test_password_hash_roundtrip():
    h = hash_password("secret123")
    assert h != "secret123"
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)


def test_token_roundtrip():
    import uuid

    token = create_access_token(
        tenant_id=uuid.uuid4(), user_id=uuid.uuid4(), role="admin"
    )
    from app.security import decode_token

    claims = decode_token(token)
    assert claims["role"] == "admin"
    assert "tenant_id" in claims and "user_id" in claims


def test_bootstrap_and_login_flow(test_database):
    client = TestClient(app)

    r = client.post(
        "/tenants/bootstrap",
        json={
            "name": "Acme Manufacturing",
            "admin_email": "admin@acme.test",
            "admin_password": "supersecret",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    tenant_id = body["tenant_id"]
    assert body["access_token"]

    r2 = client.post(
        "/auth/login",
        json={
            "tenant_id": tenant_id,
            "email": "admin@acme.test",
            "password": "supersecret",
        },
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["role"] == "admin"

    # Wrong password rejected
    r3 = client.post(
        "/auth/login",
        json={
            "tenant_id": tenant_id,
            "email": "admin@acme.test",
            "password": "nope",
        },
    )
    assert r3.status_code == 401