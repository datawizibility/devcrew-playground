from app.config import Settings


def test_settings_defaults():
    s = Settings(_env_file=None)
    assert s.jwt_algorithm == "HS256"
    assert s.jwt_expire_minutes == 720
    assert s.environment == "dev"
    assert "asyncpg" in s.database_url


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "override-secret")
    s = Settings(_env_file=None)
    assert s.jwt_secret == "override-secret"