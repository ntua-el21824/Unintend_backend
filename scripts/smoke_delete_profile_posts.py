import sys
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app


def main() -> None:
    client = TestClient(app)

    login = client.post(
        "/auth/login",
        json={"username_or_email": "eleni", "password": "pass1234"},
    )
    assert login.status_code == 200, login.text

    access_token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {access_token}"}

    created = client.post(
        "/profile-posts",
        json={"title": "Temp post", "description": "Will delete", "category": "Test"},
        headers=headers,
    )
    assert created.status_code == 200, created.text

    post_id = created.json()["id"]

    deleted = client.delete(f"/profile-posts/{post_id}", headers=headers)
    print("DELETE status:", deleted.status_code)

    mine = client.get("/profile-posts/me", headers=headers)
    assert mine.status_code == 200, mine.text

    ids = [p["id"] for p in mine.json()]
    print("Still present?", post_id in ids)


if __name__ == "__main__":
    main()
