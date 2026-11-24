"""OpenAI-compatible API client; credentials come only from the user's environment."""

import os
import time
from typing import Optional

from openai import OpenAI, OpenAIError

from .settings import model_name


class LLMError(RuntimeError):
    """A provider failure that must not be cached or scored as learning progress."""


def chat(prompt: str, system: Optional[str] = None, model: Optional[str] = None,
         temperature: Optional[float] = None, max_tokens: int = 4096) -> dict:
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise LLMError("请在 .env 或环境变量中设置 OPENAI_API_KEY。")
    try:
        selected_model = model_name(model)
    except ValueError as exc:
        raise LLMError(str(exc)) from None
    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL") or "https://api.openai.com/v1"
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    started = time.monotonic()
    try:
        with OpenAI(api_key=api_key, base_url=base_url, timeout=60, max_retries=1) as client:
            response = client.chat.completions.create(
                model=selected_model, messages=messages,
                temperature=0.3 if temperature is None else temperature,
                max_tokens=max_tokens, stream=False,
            )
        content = response.choices[0].message.content if response.choices else None
        if not content or not content.strip():
            raise LLMError("模型返回了空内容，请重试或检查模型配置。")
    except OpenAIError as exc:
        # Provider bodies may echo credentials or private document fragments.
        status = getattr(exc, "status_code", None)
        detail = f"（HTTP {status}）" if status else ""
        raise LLMError(f"模型请求失败{detail}，请检查接口地址、密钥和模型权限。") from None
    return {"content": content, "model": selected_model,
            "elapsed_seconds": round(time.monotonic() - started, 2)}


def quick_chat(prompt: str, system: Optional[str] = None, model: Optional[str] = None,
               max_tokens: int = 4096) -> str:
    return chat(prompt, system=system, model=model, max_tokens=max_tokens)["content"]
