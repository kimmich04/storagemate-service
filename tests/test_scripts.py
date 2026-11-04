"""Script dev Zalo — chạy với client giả, không gọi bot thật."""

import importlib.util
import subprocess
import sys
import uuid
from pathlib import Path
from types import ModuleType

import pytest

from app.channels.zalo_client import ZaloApiError
from tests.fakes import FakeSender

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, SCRIPTS_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakePollClient(FakeSender):
    def __init__(
        self, webhook_url: str, updates: list[dict], webhook_error: ZaloApiError | None = None
    ) -> None:
        super().__init__()
        self._webhook_url = webhook_url
        self._updates = updates
        self._webhook_error = webhook_error

    async def get_webhook_info(self) -> dict:
        if self._webhook_error:
            raise self._webhook_error
        return {"url": self._webhook_url}

    async def delete_webhook(self) -> dict:
        raise ZaloApiError("deleteWebhook", 400, "Bad request")

    async def get_updates(self, timeout: int = 30) -> dict | None:
        if not self._updates:
            raise ZaloApiError("getUpdates", 401, "Unauthorized")
        return self._updates.pop(0)


def _update(text: str) -> dict:
    message = {
        "message_id": uuid.uuid4().hex,
        "date": 1762135200000,
        "message_type": "CHAT_TEXT",
        "from": {"id": "user-1", "display_name": "NV"},
        "chat": {"id": "chat-1"},
        "text": text,
    }
    return {"ok": True, "result": {"event_name": "message.text.received", "message": message}}


def test_set_webhook_help_lists_subcommands() -> None:
    result = subprocess.run(
        [sys.executable, str(SCRIPTS_DIR / "zalo_set_webhook.py"), "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )

    assert all(command in result.stdout for command in ("set", "info", "test", "delete"))


@pytest.mark.anyio
async def test_poll_refuses_to_start_while_webhook_is_set(capsys: pytest.CaptureFixture[str]) -> None:
    zalo_poll = _load("zalo_poll")
    client = FakePollClient("https://abc.ngrok-free.app/webhooks/zalo", [])

    exit_code = await zalo_poll.run(client, Path("unused"))

    assert exit_code == 1
    assert "chạy `zalo_set_webhook.py delete` trước" in capsys.readouterr().out
    assert client.calls == []


@pytest.mark.anyio
async def test_poll_answers_updates_and_stops_on_bad_token(tmp_path: Path) -> None:
    zalo_poll = _load("zalo_poll")
    client = FakePollClient("", [_update("menu")])

    exit_code = await zalo_poll.run(client, tmp_path)

    assert exit_code == 1
    assert any("📋 Chọn nhanh" in text for text in client.messages())
    assert len(list(tmp_path.glob("*.jsonl"))) == 1


@pytest.mark.anyio
async def test_poll_treats_404_webhook_info_as_no_webhook(tmp_path: Path) -> None:
    zalo_poll = _load("zalo_poll")
    no_webhook = ZaloApiError("getWebhookInfo", 404, "Not Found")
    client = FakePollClient("", [_update("menu")], webhook_error=no_webhook)

    await zalo_poll.run(client, tmp_path)

    assert any("📋 Chọn nhanh" in text for text in client.messages())


@pytest.mark.anyio
async def test_poll_stops_cleanly_when_webhook_info_fails_otherwise(
    capsys: pytest.CaptureFixture[str],
) -> None:
    zalo_poll = _load("zalo_poll")
    client = FakePollClient("", [], webhook_error=ZaloApiError("getWebhookInfo", 401, "Unauthorized"))

    assert await zalo_poll.run(client, Path("unused")) == 1
    assert "401" in capsys.readouterr().out


@pytest.mark.anyio
@pytest.mark.parametrize("command", ["info", "delete"])
async def test_set_webhook_script_explains_when_bot_has_no_webhook(
    command: str, capsys: pytest.CaptureFixture[str]
) -> None:
    zalo_set_webhook = _load("zalo_set_webhook")
    client = FakePollClient("", [], webhook_error=ZaloApiError("getWebhookInfo", 404, "Not Found"))

    assert await zalo_set_webhook.run(command, client) == 0
    assert "chưa có webhook" in capsys.readouterr().out
