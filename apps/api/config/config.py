"""Environment-driven configuration for the ECHO backend."""

from __future__ import annotations

import os
import urllib.parse

from dotenv import load_dotenv

load_dotenv()


def _as_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _as_csv(name: str, default: str) -> list[str]:
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


class AppConfig:
    APP_NAME = os.getenv("APP_NAME", "ECHO")
    APP_VERSION = os.getenv("APP_VERSION", "0.1.0")
    APP_DESCRIPTION = "多智能体个性化技能训练平台"

    HOST = os.getenv("APP_HOST", "0.0.0.0")
    PORT = int(os.getenv("APP_PORT", "8000"))
    DEBUG = _as_bool("APP_DEBUG", False)
    RELOAD = _as_bool("APP_RELOAD", False)

    CORS_ORIGINS = _as_csv("CORS_ORIGINS", "http://localhost:8000")
    CORS_ALLOW_CREDENTIALS = "*" not in CORS_ORIGINS
    CORS_ALLOW_METHODS = ["*"]
    CORS_ALLOW_HEADERS = ["*"]


class DatabaseConfig:
    DB_TYPE = os.getenv("DB_TYPE", "sqlite").strip().lower()

    MYSQL_USER = os.getenv("MYSQL_USER", "echo")
    MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
    MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost")
    MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
    MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "echo")

    SQLITE_PATH = os.getenv("SQLITE_PATH", "./echo.db")
    POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
    MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "3600"))
    POOL_PRE_PING = True

    @classmethod
    def get_database_url(cls) -> str:
        if cls.DB_TYPE == "mysql":
            password = urllib.parse.quote_plus(cls.MYSQL_PASSWORD)
            return (
                f"mysql+pymysql://{cls.MYSQL_USER}:{password}"
                f"@{cls.MYSQL_HOST}:{cls.MYSQL_PORT}/{cls.MYSQL_DATABASE}"
                "?charset=utf8mb4"
            )
        if cls.DB_TYPE == "sqlite":
            return f"sqlite:///{cls.SQLITE_PATH}"
        raise ValueError("DB_TYPE must be either 'sqlite' or 'mysql'.")


class AIConfig:
    API_KEY = os.getenv("OPENAI_API_KEY", "")
    BASE_URL = (
        os.getenv("OPENAI_BASE_URL")
        or os.getenv("OPENA_BASE_URL")
        or "https://api.openai.com/v1"
    )
    MODEL_NAME = os.getenv("OPENAI_MODEL") or os.getenv("OPENA_MODEL") or ""

    VISION_API_KEY = os.getenv("VISION_API_KEY", API_KEY)
    VISION_BASE_URL = os.getenv("VISION_BASE_URL", BASE_URL)
    VISION_MODEL = os.getenv("VISION_MODEL", MODEL_NAME)

    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    AGENT_TEMPERATURE = float(os.getenv("AGENT_TEMPERATURE", "0.3"))
    AGENT_MAX_TOKENS = int(os.getenv("AGENT_MAX_TOKENS", "2000"))
    AGENT_TOP_P = float(os.getenv("AGENT_TOP_P", "0.9"))


class UploadConfig:
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", "./uploads")
    MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE", str(100 * 1024 * 1024)))
    ALLOWED_EXTENSIONS = {
        ".txt",
        ".md",
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".jpg",
        ".jpeg",
        ".png",
        ".gif",
        ".webp",
    }


class SecurityConfig:
    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "local-development-only-change-this-key",
    )
    ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE", "60"))
    PWD_SCHEMES = ["bcrypt"]
    PWD_DEPRECATED = "auto"
    RESET_CODE_LENGTH = int(os.getenv("RESET_CODE_LENGTH", "6"))
    RESET_CODE_EXPIRE_MINUTES = int(os.getenv("RESET_CODE_EXPIRE", "10"))
    MICRO_CALLBACK_SECRET = os.getenv("MICRO_CALLBACK_SECRET", "")


class LogConfig:
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "./logs/echo.log")
    LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(10 * 1024 * 1024)))
    LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))


class CacheConfig:
    CACHE_DIR = os.getenv("CACHE_DIR", "./data/cache")
    ENABLE_CACHE = _as_bool("ENABLE_CACHE", True)
    CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))


class EchoConfig:
    MAX_CONVERSATION_TURNS = int(os.getenv("MAX_CONVERSATION_TURNS", "50"))
    ENABLE_FSM = _as_bool("ENABLE_FSM", True)
    PROMPT_TEMPLATE_DIR = os.getenv("PROMPT_TEMPLATE_DIR", "./prompts")


def validate_config(require_ai: bool = True) -> tuple[bool, list[str]]:
    """Return configuration validity and human-readable problems."""
    problems: list[str] = []
    if DatabaseConfig.DB_TYPE not in {"sqlite", "mysql"}:
        problems.append("DB_TYPE must be sqlite or mysql.")
    if require_ai and not AIConfig.API_KEY:
        problems.append("OPENAI_API_KEY is required for agent requests.")
    if require_ai and not AIConfig.MODEL_NAME:
        problems.append("OPENAI_MODEL is required for agent requests.")
    if AppConfig.PORT < 1 or AppConfig.PORT > 65535:
        problems.append("APP_PORT must be between 1 and 65535.")
    return not problems, problems


class Config:
    app = AppConfig
    database = DatabaseConfig
    ai = AIConfig
    upload = UploadConfig
    security = SecurityConfig
    log = LogConfig
    cache = CacheConfig
    echo = EchoConfig
