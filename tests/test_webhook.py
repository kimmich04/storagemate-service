"""POST /webhooks/zalo: sai secret → 403; hợp lệ → 200 và bot trả lời (qua FakeSender); tin trùng → bỏ qua."""

import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.channels.router import get_samples_dir, get_webhook_secret, get_zalo_sender
from app.main import app
from tests.fakes import FakeSender

pytestmark = pytest.mark.anyio

SECRET = "test-webhook-secret"
URL = "/webhooks/zalo"


@pytest.fixture
def sender(tmp_path: Path) -> Iterator[FakeSender]:
    fake = FakeSender()
    app.dependency_overrides[get_webhook_secret] = lambda: SECRET
    app.dependency_overrides[get_zalo_sender] = lambda: fake
    app.dependency_overrides[get_samples_dir] = lambda: tmp_path
    yield fake
    app.dependency_overrides.clear()


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


@pytest.mark.parametrize("headers", [{}, {"X-Bot-Api-Secret-Token": "wrong"}])
async def test_missing_or_wrong_secret_is_rejected(
    client: AsyncClient, sender: FakeSender, tmp_path: Path, headers: dict
) -> None:
    resp = await client.post(URL, json=_text_event("menu"), headers=headers)

    assert resp.status_code == 403
    assert sender.calls == []
    assert list(tmp_path.iterdir()) == []


async def test_empty_configured_secret_rejects_everything(client: AsyncClient, sender: FakeSender) -> None:
    app.dependency_overrides[get_webhook_secret] = lambda: ""

    resp = await client.post(URL, json=_text_event("menu"), headers={"X-Bot-Api-Secret-Token": ""})

    assert resp.status_code == 403


async def test_valid_message_returns_200_and_bot_replies(
    client: AsyncClient, sender: FakeSender, tmp_path: Path
) -> None:
    resp = await client.post(URL, json=_text_event("menu"), headers={"X-Bot-Api-Secret-Token": SECRET})

    assert resp.status_code == 200
    assert resp.json() == {"message": "Success"}
    assert any("📋 Chọn nhanh" in text for text in sender.messages())
    assert len(list(tmp_path.glob("*.jsonl"))) == 1


async def test_duplicate_message_id_is_answered_once(client: AsyncClient, sender: FakeSender) -> None:
    event = _text_event("menu")
    headers = {"X-Bot-Api-Secret-Token": SECRET}

    await client.post(URL, json=event, headers=headers)
    await client.post(URL, json=event, headers=headers)

    assert len(sender.messages()) == 1


async def test_unknown_event_returns_200_without_reply(client: AsyncClient, sender: FakeSender) -> None:
    resp = await client.post(URL, json={"event_name": "x.y"}, headers={"X-Bot-Api-Secret-Token": SECRET})

    assert resp.status_code == 200
    assert sender.calls == []


async def test_health_still_ok(client: AsyncClient) -> None:
    resp = await client.get("/health")

    assert resp.status_code == 200
