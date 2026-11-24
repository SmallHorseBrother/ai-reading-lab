"""Shared, portable configuration for the CLI and web app."""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)


def library_dir() -> Path:
    return Path(os.getenv("AI_LIBRARY_DIR", str(PROJECT_ROOT / "examples"))).expanduser().resolve()


def output_dir() -> Path:
    return Path(os.getenv("AI_OUTPUT_DIR", str(PROJECT_ROOT / "data"))).expanduser().resolve()


def model_name(model=None) -> str:
    value = model or os.getenv("OPENAI_MODEL") or os.getenv("AI_MODEL")
    if not value or value == "your-model-id":
        raise ValueError("请在 .env 或环境变量中设置 OPENAI_MODEL，填写服务商提供的实际模型 ID。")
    return value
