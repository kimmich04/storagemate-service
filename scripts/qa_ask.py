"""Hỏi thử Q&A agent một câu từ dòng lệnh (Gemini thật + login qa_reader), không cần Zalo.

    python scripts/qa_ask.py --tenant 1 "kho tổng còn bao nhiêu trứng"

Cần GEMINI_API_KEY, LLM_MODEL và DATABASE_URL_READONLY. In thêm tool đã gọi (log INFO của app.qa).
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import settings
from app.database import build_readonly_sessionmaker
from app.qa.service import build_agent


async def ask(question: str, tenant_id: int, staff_name: str) -> int:
    readonly = build_readonly_sessionmaker()
    if readonly is None:
        print("Thiếu DATABASE_URL_READONLY (login qa_reader) — xem mục 2 của spec Q&A.", file=sys.stderr)
        return 1
    agent = build_agent(readonly)
    if agent is None:
        print("Thiếu GEMINI_API_KEY hoặc LLM_MODEL.", file=sys.stderr)
        return 1
    now = datetime.now(ZoneInfo(settings.TZ))
    reply = await agent.answer(question, tenant_id=tenant_id, staff_name=staff_name, now=now)
    print(reply if reply is not None else "(agent không trả lời được — xem log phía trên)")
    return 0 if reply is not None else 2


def main() -> None:
    raw = argparse.RawDescriptionHelpFormatter
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=raw)
    parser.add_argument("question")
    parser.add_argument("--tenant", type=int, default=1)
    parser.add_argument("--name", default="Quản lý", help="tên người hỏi (đưa vào system prompt)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    logging.getLogger("app.qa").setLevel(logging.INFO)
    sys.exit(asyncio.run(ask(args.question, args.tenant, args.name)))


if __name__ == "__main__":
    main()
