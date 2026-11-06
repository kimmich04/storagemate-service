import json

import httpx
import pytest

from app.channels.zalo_client import ZaloApiError, ZaloClient

TOKEN = "123456789:secret-token-abc"
BASE_URL = "https://bot-api.test"

pytestmark = pytest.mark.anyio


def _error(code: int) -> httpx.Response:
    return httpx.Response(code, json={"ok": False, "error_code": code, "description": f"lỗi {code}"})


def _client(responses: list[httpx.Response], requests: list[httpx.Request]) -> ZaloClient:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return responses[min(len(requests), len(responses)) - 1]

    async def no_sleep(_: float) -> None:
        return None

    return ZaloClient(TOKEN, BASE_URL, transport=httpx.MockTransport(handler), sleep=no_sleep)


async def test_send_message_posts_json_to_token_path() -> None:
    requests: list[httpx.Request] = []
    client = _client([httpx.Response(200, json={"ok": True, "result": {"message_id": "m1"}})], requests)

    await client.send_message("chat-1", "Xin chào", parse_mode="markdown")

    assert requests[0].method == "POST"
    assert requests[0].url.path == f"/bot{TOKEN}/sendMessage"
    assert json.loads(requests[0].content) == {
        "chat_id": "chat-1",
        "text": "Xin chào",
        "parse_mode": "markdown",
    }


async def test_429_is_retried_until_success() -> None:
    requests: list[httpx.Request] = []
    ok = httpx.Response(200, json={"ok": True, "result": {}})
    client = _client([_error(429), _error(429), ok], requests)

    await client.send_message("chat-1", "hi")

    assert len(requests) == 3


async def test_401_fails_immediately_with_hint() -> None:
    requests: list[httpx.Request] = []
    client = _client([_error(401)], requests)

    with pytest.raises(ZaloApiError) as error:
        await client.send_message("chat-1", "hi")

    assert len(requests) == 1
    assert error.value.code == 401
    assert "token sai hoặc đã reset" in str(error.value)


async def test_error_message_never_contains_token() -> None:
    requests: list[httpx.Request] = []
    leaky = httpx.Response(400, json={"ok": False, "error_code": 400, "description": f"bad /bot{TOKEN}/x"})
    client = _client([leaky], requests)

    with pytest.raises(ZaloApiError) as error:
        await client.send_message("chat-1", "hi")

    assert TOKEN not in str(error.value)


async def test_get_updates_returns_none_on_408_without_retry() -> None:
    requests: list[httpx.Request] = []
    client = _client([_error(408)], requests)

    assert await client.get_updates(timeout=30) is None
    assert len(requests) == 1


async def test_network_error_is_wrapped_without_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"cannot reach {request.url}", request=request)

    client = ZaloClient(TOKEN, BASE_URL, transport=httpx.MockTransport(handler))

    with pytest.raises(ZaloApiError) as error:
        await client.get_me()

    assert TOKEN not in str(error.value)
    assert error.value.__cause__ is None
