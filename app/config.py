"""Settings chung, đọc từ biến môi trường / file .env (pydantic-settings).

Domain nào cần cấu hình riêng thì tạo <domain>/config.py với BaseSettings riêng.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Zalo Bot
    ZALO_BOT_TOKEN: str = ""
    ZALO_WEBHOOK_SECRET: str = ""
    PUBLIC_BASE_URL: str = "http://localhost:8000"
    ZALO_API_BASE: str = "https://bot-api.zaloplatforms.com"
    ZALO_SAMPLES_DIR: str = "data/zalo_samples"  # payload thô để tra field name (gitignored)

    # Database
    DATABASE_URL: str = "postgresql+psycopg://storagemate:storagemate@localhost:5432/storagemate"
    DATABASE_URL_READONLY: str = ""  # user qa_reader, chỉ SELECT, dùng cho Q&A agent

    # Auth
    JWT_SECRET: str = "change-me"
    JWT_EXPIRE_MINUTES: int = 60 * 12

    # LLM (Q&A + parser fallback)
    GEMINI_API_KEY: str = ""
    LLM_MODEL: str = ""  # tên model Gemini Flash-Lite, lấy trong Google AI Studio

    # NER
    HF_MODEL_REPO: str = ""
    NER_MODEL_PATH: str = "models/ner/model_quantized.onnx"

    # Khác
    TZ: str = "Asia/Ho_Chi_Minh"
    CORS_ORIGINS: str = "http://localhost:5173"  # nhiều domain: phân cách bằng dấu phẩy

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


settings = Settings()
