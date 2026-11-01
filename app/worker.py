"""Process 2 (container worker), cùng codebase với API.

Việc cần làm (Pha 1):
1. Vòng lặp lấy tin từ bảng inbound_messages (SELECT ... FOR UPDATE SKIP LOCKED) → messaging/queue.py
2. Phân loại tin → messaging/dispatcher.py → parser/ (nhập/xuất) hoặc qa/ (câu hỏi manager)
3. Chạy APScheduler cho báo cáo ngày/tháng → reports/jobs.py
4. Nạp model NER (ONNX) một lần lúc khởi động → parser/ner.py

Chạy: python -m app.worker
"""
import logging
import time

logger = logging.getLogger("worker")


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    logger.info("Worker khởi động. TODO: hiện thực vòng lặp hàng đợi (Pha 1).")
    while True:
        time.sleep(10)


if __name__ == "__main__":
    main()
