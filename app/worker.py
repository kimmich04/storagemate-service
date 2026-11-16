"""Process 2 (container worker), cùng codebase với API — ĐÚNG 1 tiến trình.

Vòng lặp lấy tin từ inbound_messages (FOR UPDATE SKIP LOCKED) → messaging/queue.py.
Q&A cho manager (app/qa) chạy trên kết nối riêng bằng login qa_reader.
Chưa có: APScheduler báo cáo (reports/jobs.py), nạp model NER (Phase 2).

Chạy: python -m app.worker
"""

import asyncio
import logging

from app.channels.zalo_client import ZaloClient
from app.config import settings
from app.database import SessionLocal, build_readonly_sessionmaker
from app.messaging.pending import PendingStore
from app.messaging.queue import process_next
from app.parser.llm import build_parser
from app.qa.service import QaAgent, build_agent

logger = logging.getLogger("worker")


def _build_qa() -> QaAgent | None:
    """Q&A cần cả Gemini lẫn login qa_reader; thiếu thì tắt, không bao giờ dùng DATABASE_URL thay."""
    readonly = build_readonly_sessionmaker()
    qa = build_agent(readonly) if readonly else None
    if qa:
        logger.info("Hỏi đáp (Q&A): bật")
    elif readonly is None:
        logger.info("Hỏi đáp (Q&A): tắt (thiếu DATABASE_URL_READONLY)")
    else:
        logger.info("Hỏi đáp (Q&A): tắt (thiếu GEMINI_API_KEY hoặc LLM_MODEL)")
    return qa


async def run() -> None:
    # ponytail: DB sync gọi thẳng trên event loop — ổn vì chỉ 1 worker và không có việc nào khác trên loop.
    client = ZaloClient(settings.ZALO_BOT_TOKEN, settings.ZALO_API_BASE)
    pending = PendingStore()
    llm = build_parser()
    logger.info("Tầng LLM: %s", "bật" if llm else "tắt (thiếu GEMINI_API_KEY hoặc LLM_MODEL)")
    qa = _build_qa()
    if settings.INVITE_REUSABLE:
        logger.warning("INVITE_REUSABLE bật: mã mời dùng lại được — chỉ cho máy dev, KHÔNG bật ở production")
    logger.info("Worker khởi động, đang chờ tin trong inbound_messages.")
    try:
        while True:
            try:
                processed = await process_next(SessionLocal, client, pending, llm=llm, qa=qa)
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
