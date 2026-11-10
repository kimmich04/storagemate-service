"""Quản lý webhook Zalo: set (PUBLIC_BASE_URL + /webhooks/zalo, ZALO_WEBHOOK_SECRET) · info · test · delete.

Chạy lại `set` mỗi lần đổi domain (ngrok). Muốn poll thì `delete` trước.
"""

import argparse
import asyncio
import json
import sys

from app.channels.zalo_client import ZaloApiError, ZaloClient
from app.config import settings

WEBHOOK_PATH = "/webhooks/zalo"
HIDDEN_KEY_PARTS = ("secret", "token")
# Thực tế 03/11 (token đúng, getMe OK): bot chưa đặt webhook → getWebhookInfo 404, deleteWebhook 400.
NO_WEBHOOK_ERRORS = {("info", 404), ("delete", 400)}


def _printable(result: object) -> str:
    """Không in lại secret/token nếu Zalo trả kèm trong kết quả."""
    if isinstance(result, dict):
        result = {k: v for k, v in result.items() if not any(part in k.lower() for part in HIDDEN_KEY_PARTS)}
    return json.dumps(result, ensure_ascii=False, indent=2)


async def run(command: str, client: ZaloClient) -> int:
    try:
        if command == "set":
            if not settings.ZALO_WEBHOOK_SECRET:
                print("Thiếu ZALO_WEBHOOK_SECRET trong .env")
                return 1
            url = settings.PUBLIC_BASE_URL.rstrip("/") + WEBHOOK_PATH
            print(f"Đặt webhook: {url}")
            result = await client.set_webhook(url, settings.ZALO_WEBHOOK_SECRET)
        elif command == "info":
            result = await client.get_webhook_info()
        elif command == "test":
            result = await client.test_webhook()
        else:
            result = await client.delete_webhook()
    except ZaloApiError as error:
        if (command, error.code) in NO_WEBHOOK_ERRORS:
            print(f"Bot chưa có webhook nào (Zalo trả {error.code}) → có thể chạy zalo_poll.py.")
            return 0
        print(error)
        return 1
    print(_printable(result))
    return 0


async def main(command: str) -> int:
    if not settings.ZALO_BOT_TOKEN:
        print("Thiếu ZALO_BOT_TOKEN trong .env")
        return 1
    client = ZaloClient(settings.ZALO_BOT_TOKEN, settings.ZALO_API_BASE)
    try:
        return await run(command, client)
    finally:
        await client.aclose()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")  # console Windows mặc định cp1252, không in được tiếng Việt
    parser = argparse.ArgumentParser(description="Quản lý webhook Zalo Bot")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("set", help="đặt webhook = PUBLIC_BASE_URL + /webhooks/zalo")
    commands.add_parser("info", help="xem webhook đang đặt")
    commands.add_parser("test", help="nhờ Zalo gửi thử một sự kiện (có hạn mức mỗi ngày)")
    commands.add_parser("delete", help="xoá webhook (bắt buộc trước khi chạy zalo_poll.py)")
    sys.exit(asyncio.run(main(parser.parse_args().command)))
