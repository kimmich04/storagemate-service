"""POST /webhooks/zalo: sai secret → 403; hợp lệ → 200 + 1 dòng inbound_messages; trùng → vẫn 1 dòng."""

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.channels.router import get_samples_dir, get_webhook_secret
from app.database import get_db
from app.main import app
from app.messaging.models import InboundMessage as InboundRow

pytestmark = pytest.mark.anyio

SECRET = "test-webhook-secret"
URL = "/webhooks/zalo"
HEADERS = {"X-Bot-Api-Secret-Token": SECRET}


@pytest.fixture
def overrides(tmp_path: Path) -> Iterator[None]:
    app.dependency_overrides[get_webhook_secret] = lambda: SECRET
    app.dependency_overrides[get_samples_dir] = lambda: tmp_path
    yield
    app.dependency_overrides.clear()


@pytest.fixture
def db(overrides: None, db_session: Session) -> Session:
    app.dependency_overrides[get_db] = lambda: db_session
    return db_session


def _text_event(text: str) -> dict:
    return {
        "event_name": "message.text.received",
        "message": {
            "message_id": uuid.uuid4().hex,
            "date": 1762135200000,
            "message_type": "CHAT_TEXT",
            "from": {"id": "user-1", "display_name": "NV", "is_bot": False},
            "chat": {"id": "chat-1", "chat_type": "PRIVATE"},
            "text": text,
        },
    }


def _count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(InboundRow))


@pytest.mark.parametrize("headers", [{}, {"X-Bot-Api-Secret-Token": "wrong"}])
async def test_missing_or_wrong_secret_is_rejected(
    client: AsyncClient, overrides: None, tmp_path: Path, headers: dict
) -> None:
    resp = await client.post(URL, json=_text_event("menu"), headers=headers)

    assert resp.status_code == 403
    assert list(tmp_path.iterdir()) == []


async def test_empty_configured_secret_rejects_everything(client: AsyncClient, overrides: None) -> None:
    app.dependency_overrides[get_webhook_secret] = lambda: ""

    resp = await client.post(URL, json=_text_event("menu"), headers={"X-Bot-Api-Secret-Token": ""})

    assert resp.status_code == 403


async def test_valid_message_returns_200_and_is_queued(
    client: AsyncClient, db: Session, tmp_path: Path
) -> None:
    resp = await client.post(URL, json=_text_event("menu"), headers=HEADERS)

    assert resp.status_code == 200
    assert resp.json() == {"message": "Success"}
    row = db.scalars(select(InboundRow)).one()
    assert (row.status, row.text, row.chat_id) == ("pending", "menu", "chat-1")
    assert len(list(tmp_path.glob("*.jsonl"))) == 1


async def test_duplicate_message_id_is_queued_once(client: AsyncClient, db: Session) -> None:
    event = _text_event("menu")

    await client.post(URL, json=event, headers=HEADERS)
    resp = await client.post(URL, json=event, headers=HEADERS)

    assert resp.status_code == 200
    assert _count(db) == 1


async def test_unknown_event_returns_200_without_queueing(client: AsyncClient, db: Session) -> None:
    resp = await client.post(URL, json={"event_name": "x.y"}, headers=HEADERS)

    assert resp.status_code == 200
    assert _count(db) == 0


async def test_set_webhook_verification_event_returns_200_without_queueing(
    client: AsyncClient, db: Session, tmp_path: Path
) -> None:
    # Body thật Zalo gửi khi setWebhook (integrations.md 2026-11-04): không có chat/from.
    message = {"date": 1762135200000, "message_id": "t1", "text": "test"}
    event = {"event_name": "webhook.test", "message": message}

    resp = await client.post(URL, json=event, headers=HEADERS)

    assert resp.status_code == 200
    assert _count(db) == 0
    assert len(list(tmp_path.glob("*.jsonl"))) == 1


async def test_non_object_body_is_rejected_without_queueing(client: AsyncClient, db: Session) -> None:
    resp = await client.post(URL, json=[_text_event("menu")], headers=HEADERS)

    assert resp.status_code == 422
    assert _count(db) == 0


async def test_health_still_ok(client: AsyncClient) -> None:
    resp = await client.get("/health")

    assert resp.status_code == 200
