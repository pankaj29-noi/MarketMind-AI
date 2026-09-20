"""Upload size / safety regressions."""
from fastapi.testclient import TestClient

from backend.config import MAX_UPLOAD_BYTES
from backend.main import app


client = TestClient(app)


def test_upload_rejects_non_csv():
    res = client.post(
        "/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert res.status_code == 400


def test_upload_rejects_oversized_payload(monkeypatch):
    monkeypatch.setattr("backend.main.MAX_UPLOAD_BYTES", 64)
    huge = b"a,b\n" + (b"1,2\n" * 40)
    assert len(huge) > 64
    res = client.post(
        "/upload",
        files={"file": ("big.csv", huge, "text/csv")},
    )
    assert res.status_code == 413
    assert "maximum upload size" in res.json()["detail"].lower()
