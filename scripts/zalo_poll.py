"""Chế độ dev không cần webhook: long-poll getUpdates rồi gọi đúng process() mà webhook dùng.

Chạy: python scripts/zalo_poll.py   (Ctrl+C để dừng). Polling và webhook loại trừ nhau.
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Protocol

from app.channels.zalo import parse_update, save_sample
from app.channels.zalo_client import ZaloApiError, ZaloClient
from app.config import settings
from app.messaging.queue import Sender, process

POLL_TIMEOUT_SECONDS = 30
ERROR_PAUSE_SECONDS = 5
TOKEN_ERROR_CODE = 401
NO_WEBHOOK_CODE = 404  # thực tế 03/11: getWebhookInfo trả 404 (không phải url rỗng) khi bot chưa đặt webhook


class PollClient(Sender, Protocol):
    async def get_webhook_info(self) -> dict: ...

    async def get_updates(self, timeout: int = POLL_TIMEOUT_SECONDS) -> dict | None: ...


async def run(client: PollClient, samples_dir: Path) -> int:
    """Trả exit code: 1 khi webhook đang bật hoặc token hỏng."""
    try:
        webhook = await client.get_webhook_info()
    except ZaloApiError as error:
        if error.code != NO_WEBHOOK_CODE:
            print(error)
            return 1
        webhook = {}
    if (webhook or {}).get("url"):
        print("Webhook đang bật → chạy `zalo_set_webhook.py delete` trước rồi mới poll.")
        return 1
    print("Đang poll Zalo… (Ctrl+C để dừng)")
    while True:
        try:
            update = await client.get_updates(timeout=POLL_TIMEOUT_SECONDS)
        except ZaloApiError as error:
            print(error)
            if error.code == TOKEN_ERROR_CODE:
                return 1
            await asyncio.sleep(ERROR_PAUSE_SECONDS)
            continue
        if not update:
            continue
        save_sample(update, samples_dir)
        msg = parse_update(update)
        if msg is None:
            print("Bỏ qua sự kiện không đọc được (đã lưu mẫu).")
            continue
        await process(msg, client)


async def main() -> int:
    if not settings.ZALO_BOT_TOKEN:
        print("Thiếu ZALO_BOT_TOKEN trong .env")
        return 1
    client = ZaloClient(settings.ZALO_BOT_TOKEN, settings.ZALO_API_BASE)
    try:
        return await run(client, Path(settings.ZALO_SAMPLES_DIR))
    finally:
        await client.aclose()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # console Windows mặc định cp1252, không in được tiếng Việt
    logging.basicConfig(level=logging.INFO)
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("Đã dừng.")
