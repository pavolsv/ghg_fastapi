"""LLM 輔助生成報告書章節敘述文字。

沿用專案現有環境變數設定：
  - LLM_PROVIDER=gemini|openai
  - GEMINI_API_KEY / GOOGLE_API_KEY
  - GEMINI_BASE_URL（預設為 Gemini OpenAI-compatible endpoint）
  - GEMINI_MODEL（預設 gemini-2.5-flash）
  - OPENAI_API_KEY
  - OPENAI_MODEL（預設 gpt-4o-mini）
"""

import json
import os
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

LOCAL_ENV_PATH = Path("env.local.txt")


def _load_local_env_settings() -> dict[str, str]:
    """讀取 env.local.txt 中的環境變數（支援 export / $env: 前綴）。"""
    if not LOCAL_ENV_PATH.exists():
        return {}

    try:
        raw_text = LOCAL_ENV_PATH.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raw_text = LOCAL_ENV_PATH.read_text(encoding="utf-8-sig")

    settings: dict[str, str] = {}
    for raw_line in raw_text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.lower().startswith("export "):
            line = line[7:].strip()
        if line.startswith("$env:"):
            line = line[5:].strip()

        if "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue

        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]

        settings[key] = value

    return settings


def _get_env_value(*keys: str, default: str | None = None) -> str | None:
    """依序從系統環境變數與 env.local.txt 讀取設定。"""
    for key in keys:
        env_value = os.getenv(key)
        if env_value and env_value.strip():
            return env_value.strip()

    local_settings = _load_local_env_settings()
    for key in keys:
        local_value = local_settings.get(key)
        if local_value and local_value.strip():
            return local_value.strip()

    return default


def _resolve_llm_config() -> dict[str, str]:
    """解析 LLM 設定。"""
    provider = (
        _get_env_value("LLM_PROVIDER", default="gemini") or "gemini"
    ).strip().lower()

    if provider == "gemini":
        api_key = _get_env_value("GEMINI_API_KEY", "GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("未設定 GEMINI_API_KEY（或 GOOGLE_API_KEY）。")

        return {
            "provider": provider,
            "api_key": api_key,
            "base_url": _get_env_value(
                "GEMINI_BASE_URL",
                default="https://generativelanguage.googleapis.com/v1beta/openai/",
            )
            or "https://generativelanguage.googleapis.com/v1beta/openai/",
            "model": _get_env_value("GEMINI_MODEL", default="gemini-2.5-flash")
            or "gemini-2.5-flash",
        }

    if provider == "openai":
        api_key = _get_env_value("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("未設定 OPENAI_API_KEY。")

        return {
            "provider": provider,
            "api_key": api_key,
            "model": _get_env_value("OPENAI_MODEL", default="gpt-4o-mini")
            or "gpt-4o-mini",
        }

    raise RuntimeError("不支援的 LLM_PROVIDER，請使用 openai 或 gemini。")


_CHAPTER_PROMPTS: dict[int, str] = {
    1: (
        "你是一名溫室氣體盤查顧問，正在撰寫盤查報告書第1章「公司簡介與政策聲明」。"
        "請根據提供的公司資料，以繁體中文、正式報告語氣撰寫前言、預期用途與公司簡介。"
        "請勿捏造數字或事實。若資料不足，請明確寫出資料缺口。"
    ),
    3: (
        "你是一名溫室氣體盤查顧問，正在撰寫盤查報告書第3章「報告溫室氣體排放量」。"
        "請根據提供的排放數據，以繁體中文、正式報告語氣撰寫排放類型說明與排放量分析。"
        "請勿捏造數字，只能使用提供的數據。"
    ),
    5: (
        "你是一名溫室氣體盤查顧問，正在撰寫盤查報告書第5章「基準年」。"
        "請根據提供的基準年數據，以繁體中文、正式報告語氣撰寫基準年設定說明。"
        "請勿捏造數字，只能使用提供的數據。"
    ),
}


async def generate_chapter(chapter_no: int, data: dict[str, Any]) -> str:
    """使用 LLM 生成單一章節的敘述文字。"""
    if chapter_no not in _CHAPTER_PROMPTS:
        raise ValueError(f"不支援由 LLM 生成的章節編號：{chapter_no}")

    config = _resolve_llm_config()

    if config["provider"] == "gemini":
        client = AsyncOpenAI(
            api_key=config["api_key"],
            base_url=config["base_url"],
        )
    elif config["provider"] == "openai":
        client = AsyncOpenAI(api_key=config["api_key"])
    else:
        raise RuntimeError("不支援的 LLM_PROVIDER。")

    response = await client.chat.completions.create(
        model=config["model"],
        temperature=0.2,
        messages=[
            {"role": "system", "content": _CHAPTER_PROMPTS[chapter_no]},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
        ],
    )

    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise RuntimeError("LLM 沒有回傳內容。")

    return content
