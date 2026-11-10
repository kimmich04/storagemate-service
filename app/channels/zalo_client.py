"""Gọi Zalo Bot API (bot-api.zaloplatforms.com/bot<TOKEN>/<method>).

Token nằm trong URL → không bao giờ log URL, không để URL lọt vào message lỗi.
"""

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import Any

import httpx

logger = logging.getLogger(__name__)
# httpx/httpcore log URL ở mức INFO/DEBUG — URL chứa token.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

RETRYABLE_CODES = frozenset({403, 408, 429})  # bảng mã lỗi Zalo: 403 = lỗi server, 408 timeout, 429 quota
MAX_ATTEMPTS = 3
BACKOFF_BASE_SECONDS = 0.5
REQUEST_TIMEOUT_SECONDS = 10.0
POLL_TIMEOUT_CODE = 408
ERROR_HINTS = {401: "token sai hoặc đã reset"}
REDACTED = "***"

Sleep = Callable[[float], Awaitable[None]]


class ZaloApiError(Exception):
    def __init__(self, method: str, code: int | None, description: str) -> None:
        self.method = method
        self.code = code
        hint = ERROR_HINTS.get(code or 0)
        super().__init__(f"Zalo {method} lỗi {code}: {description}" + (f" ({hint})" if hint else ""))


class ZaloClient:
    """Một AsyncClient dùng chung cho cả process (tạo trong lifespan, đóng bằng aclose)."""

    def __init__(
        self,
        token: str,
        base_url: str,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        sleep: Sleep = asyncio.sleep,
    ) -> None:
        self._token = token
        self._sleep = sleep
        self._http = httpx.AsyncClient(
            base_url=base_url, timeout=REQUEST_TIMEOUT_SECONDS, transport=transport
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def get_me(self) -> dict:
        return await self._call("getMe")

    async def get_updates(self, timeout: int = 30) -> dict | None:
        """Long polling; None khi hết thời gian chờ mà không có tin mới."""
        try:
            return await self._call(
                "getUpdates",
                {"timeout": str(timeout)},
                timeout=timeout + REQUEST_TIMEOUT_SECONDS,
                retryable=RETRYABLE_CODES - {POLL_TIMEOUT_CODE},
            )
        except ZaloApiError as error:
            if error.code == POLL_TIMEOUT_CODE:
                return None
            raise

    async def set_webhook(self, url: str, secret_token: str) -> dict:
        return await self._call("setWebhook", {"url": url, "secret_token": secret_token})

    async def delete_webhook(self) -> dict:
        return await self._call("deleteWebhook")

    async def get_webhook_info(self) -> dict:
        return await self._call("getWebhookInfo")

    async def test_webhook(self) -> dict:
        return await self._call("testWebhook")

    async def send_message(self, chat_id: str, text: str, parse_mode: str | None = None) -> dict:
        payload = {"chat_id": chat_id, "text": text}
        if parse_mode:
            payload["parse_mode"] = parse_mode
        return await self._call("sendMessage", payload)

    async def send_chat_action(self, chat_id: str, action: str = "typing") -> dict:
        return await self._call("sendChatAction", {"chat_id": chat_id, "action": action})

    async def _call(
        self,
        method: str,
        payload: dict | None = None,
        *,
        timeout: float = REQUEST_TIMEOUT_SECONDS,
        retryable: frozenset[int] = RETRYABLE_CODES,
    ) -> Any:
        """Gọi một method; thử lại tối đa MAX_ATTEMPTS với backoff mũ + jitter cho mã lỗi tạm thời."""
        for attempt in range(MAX_ATTEMPTS):
            body, status = await self._post(method, payload, timeout)
            if body.get("ok"):
                return body.get("result")
            code = body.get("error_code") or status
            error = ZaloApiError(method, code, self._redact(str(body.get("description", ""))))
            if code not in retryable or attempt == MAX_ATTEMPTS - 1:
                raise error
            logger.warning("%s — thử lại lần %d", error, attempt + 2)
            await self._sleep(BACKOFF_BASE_SECONDS * 2**attempt + random.uniform(0, BACKOFF_BASE_SECONDS))

    async def _post(self, method: str, payload: dict | None, timeout: float) -> tuple[dict, int]:
        try:
            response = await self._http.post(
                f"/bot{self._token}/{method}", json=payload or {}, timeout=timeout
            )
        except httpx.HTTPError as error:
            # Không giữ exception gốc (from None): nó mang request.url có token.
            raise ZaloApiError(method, None, self._redact(f"{type(error).__name__}: {error}")) from None
        try:
            body = response.json()
        except ValueError:
            body = {}
        return (body if isinstance(body, dict) else {}), response.status_code

    def _redact(self, text: str) -> str:
        return text.replace(self._token, REDACTED) if self._token else text
