"""
MCP-сервер стайлгайда
=====================
Простой FastAPI-сервис, который раздаёт содержимое стайлгайда и список
запрещённых слов. Используется LLM review-агентом как основной источник;
при недоступности агент переключается на локальные файлы.

Эндпоинты:
    GET /health                     — проверка работоспособности
    GET /tools/get_style_guide      — полный текст стайлгайда (или раздел)
    GET /tools/get_forbidden_words  — YAML-правила Russian/ стилей

Переменные окружения:
    MCP_API_KEY  — Bearer-токен для авторизации (опционально).
                   Если задан, все запросы к /tools/* должны его содержать.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# ── Пути ──────────────────────────────────────────────────────────────────────
# Сервер находится в mcp_server/, стайлгайд — в style_guide/ на уровень выше.
BASE_DIR        = Path(__file__).parent.parent
STYLE_GUIDE_DIR = BASE_DIR / "style_guide"
RUSSIAN_DIR     = BASE_DIR / "styles" / "Russian"

# ── Приложение ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Docs Style Guide MCP Server",
    description="Раздаёт стайлгайд и правила Vale для LLM review-агента.",
    version="1.0.0",
)

security = HTTPBearer(auto_error=False)
_API_KEY = os.environ.get("MCP_API_KEY", "")


def verify_api_key(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
) -> None:
    """Проверяет Bearer-токен, если MCP_API_KEY задан в окружении."""
    if not _API_KEY:
        return  # ключ не настроен → авторизация отключена
    if credentials is None or credentials.credentials != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")


# ── Эндпоинты ─────────────────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
def health() -> dict:
    """Проверка работоспособности сервера."""
    style_ok   = STYLE_GUIDE_DIR.exists()
    russian_ok = RUSSIAN_DIR.exists()
    return {
        "status": "ok",
        "style_guide_dir": str(STYLE_GUIDE_DIR),
        "style_guide_available": style_ok,
        "russian_rules_available": russian_ok,
    }


@app.get("/tools/get_style_guide", tags=["tools"])
def get_style_guide(
    section: Optional[str] = None,
    _auth: None = Depends(verify_api_key),
) -> dict:
    """
    Возвращает стайлгайд.

    Параметры:
        section — часть имени файла для фильтрации (например, "word_choice").
                  Если не задан — возвращается полный стайлгайд.
    """
    if not STYLE_GUIDE_DIR.exists():
        raise HTTPException(status_code=503, detail="Style guide directory not found.")

    files = sorted(STYLE_GUIDE_DIR.glob("0*.md"))
    if section:
        files = [f for f in files if section.lower() in f.stem.lower()]
        if not files:
            raise HTTPException(
                status_code=404,
                detail=f"Section matching '{section}' not found.",
            )

    sections: dict[str, str] = {}
    for f in files:
        sections[f.stem] = f.read_text(encoding="utf-8")

    content = "\n\n---\n\n".join(sections.values())
    return {"content": content, "sections": sections}


@app.get("/tools/get_forbidden_words", tags=["tools"])
def get_forbidden_words(
    _auth: None = Depends(verify_api_key),
) -> dict:
    """
    Возвращает содержимое YAML-правил из styles/Russian/.
    Удобно для передачи LLM в сыром виде.
    """
    if not RUSSIAN_DIR.exists():
        raise HTTPException(status_code=503, detail="Russian rules directory not found.")

    rules: dict[str, str] = {}
    for yml in sorted(RUSSIAN_DIR.glob("*.yml")):
        rules[yml.stem] = yml.read_text(encoding="utf-8")

    if not rules:
        raise HTTPException(status_code=404, detail="No Russian rule files found.")

    return {"rules": rules}


# ── Запуск для локальной отладки ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
