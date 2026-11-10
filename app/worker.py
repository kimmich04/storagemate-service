"""Process 2 (container worker), cùng codebase với API — ĐÚNG 1 tiến trình.

Vòng lặp lấy tin từ inbound_messages (FOR UPDATE SKIP LOCKED) → messaging/queue.py.
Chưa có: APScheduler báo cáo (reports/jobs.py), nạp model NER (Phase 2).

Chạy: python -m app.worker
"""

import asyncio
import logging

from app.channels.zalo_client import ZaloClient
from app.config import settings
from app.database import SessionLocal
from app.messaging.pending import PendingStore
from app.messaging.queue import process_next
from app.parser.llm import build_parser

logger = logging.getLogger("worker")


async def run() -> None:
    # ponytail: DB sync gọi thẳng trên event loop — ổn vì chỉ 1 worker và không có việc nào khác trên loop.
    client = ZaloClient(settings.ZALO_BOT_TOKEN, settings.ZALO_API_BASE)
    pending = PendingStore()
    llm = build_parser()
    logger.info("Tầng LLM: %s", "bật" if llm else "tắt (thiếu GEMINI_API_KEY hoặc LLM_MODEL)")
    logger.info("Worker khởi động, đang chờ tin trong inbound_messages.")
    try:
        while True:
            try:
                processed = await process_next(SessionLocal, client, pending, llm=llm)
            except Exception:
                logger.exception("Vòng lặp worker lỗi (DB?) — thử lại sau")
                processed = False
            if not processed:
                await asyncio.sleep(settings.WORKER_POLL_SECONDS)
    finally:
        await client.aclose()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == "__main__":
    main()
