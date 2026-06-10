from fastapi.testclient import TestClient

from api.app import app


def test_logout_removes_access_token_cookie():
    client = TestClient(app)
    client.cookies.set("access_token", "test-token")

    response = client.post("/logout")

    assert response.status_code == 200
    assert response.json() == {"success": True}
    assert "access_token" not in client.cookies
