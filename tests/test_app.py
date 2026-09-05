import pytest

import app
import detector
import storage


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setattr(
        detector,
        "llm_signal",
        lambda _text: {
            "score": 0.5,
            "reason": "Deterministic test stub.",
        },
    )

    storage.init_db()
    app.app.config.update(TESTING=True)

    with app.app.test_client() as test_client:
        yield test_client


def submit_text(client, creator_id="creator-1"):
    response = client.post(
        "/submit",
        json={
            "text": (
                "This is a sufficiently detailed passage used to exercise "
                "the complete submission and persistence workflow."
            ),
            "creator_id": creator_id,
            "content_type": "essay",
        },
    )
    assert response.status_code == 201
    return response.get_json()


def test_submit_persists_classification(client):
    result = submit_text(client)

    stored = storage.get_classification(result["content_id"])

    assert stored is not None
    assert stored["creator_id"] == "creator-1"
    assert stored["attribution"] == result["attribution"]


def test_submit_rejects_non_json_body(client):
    response = client.post(
        "/submit",
        data="not json",
        content_type="text/plain",
    )

    assert response.status_code == 400
    assert "error" in response.get_json()


def test_duplicate_open_appeal_is_rejected(client):
    classification = submit_text(client)

    appeal = {
        "content_id": classification["content_id"],
        "creator_id": "creator-1",
        "creator_reasoning": "I wrote and revised this passage myself.",
    }

    first_response = client.post("/appeal", json=appeal)
    second_response = client.post("/appeal", json=appeal)

    assert first_response.status_code == 201
    assert second_response.status_code == 409


def test_certificate_rejects_creator_mismatch(client):
    classification = submit_text(client)

    response = client.post(
        "/certificate",
        json={
            "content_id": classification["content_id"],
            "creator_id": "different-creator",
            "verification_note": "Draft history is available.",
        },
    )

    assert response.status_code == 403
