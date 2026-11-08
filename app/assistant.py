"""AI-помощник по процедурам удаления данных.

Жёсткие правила:
1. Никакие персональные данные пользователя не уходят в LLM: если в вопросе
   найден email / телефон / номер карты / СНИЛС — запрос блокируется локально.
2. Все настройки только из переменных окружения: LLM_API_KEY, LLM_BASE_URL,
   LLM_MODEL. В коде ключей нет и быть не должно.
3. Если LLM не настроен — возвращаем подсказку, а не ошибку 500.
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

SYSTEM_PROMPT = (
    "Ты — консультант сервиса DataCleaner. Ты помогаешь пользователю удалять свои "
    "персональные данные из интернета: из брокеров данных, people-search сайтов, "
    "маркетинговых баз и поисковой выдачи.\n\n"
    "Твои темы:\n"
    "- права субъекта персональных данных по 152-ФЗ (ст. 14, 20, 21), GDPR "
    "(Art. 15, 17, 21, 12) и CCPA/CPRA (§1798.105, §1798.130);\n"
    "- как составить и куда отправить запрос на удаление, какие сроки у оператора, "
    "что делать при отказе или молчании (жалоба в Роскомнадзор, регулятор ЕС, "
    "CPPA/Attorney General);\n"
    "- как снизить цифровой след: opt-out, скрытие адреса, раздельные email, "
    "удаление старых аккаунтов.\n\n"
    "Жёсткие правила:\n"
    "1. НИКОГДА не проси у пользователя персональные данные: ФИО, email, телефон, "
    "адрес, номер документа, данные карты. Если они нужны для процедуры — опиши, "
    "что их надо вписать самостоятельно в шаблон письма.\n"
    "2. Если пользователь сам прислал персональные данные — не повторяй их в ответе, "
    "попроси удалить и объясни, что письмо генерируется локально в приложении.\n"
    "3. Отвечай по-русски, кратко и структурно: нумерованные шаги, конкретные сроки, "
    "ссылки на нормы. Максимум 250 слов.\n"
    "4. Ты не юрист: в конце ответа одной строкой напомни, что это информационная "
    "справка, а не юридическое заключение.\n"
    "5. Не выдумывай точные URL и email сервисов — если не уверен, скажи, что адрес "
    "нужно проверить в политике конфиденциальности сервиса."
)

# --------------------------------------------------------------- PII-фильтр
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("phone", re.compile(r"(?<![\w.])(?:\+\d{1,3}[\s\-().]*)?(?:\(\d{2,4}\)[\s\-]*)?\d[\d\s\-().]{7,}\d(?![\w.])")),
    ("card", re.compile(r"\b(?:\d[ \-]?){13,19}\b")),
    ("snils", re.compile(r"\b\d{3}[-\s]?\d{3}[-\s]?\d{3}[-\s]?\d{2}\b")),
    ("passport", re.compile(r"\b\d{2}\s?\d{2}\s?(?:№|N|no\.?)?\s?\d{6}\b")),
]

PII_WARNING = (
    "Похоже, в вопросе есть персональные данные ({kinds}). Я не отправляю такие "
    "запросы в AI-модель: переписка с внешним провайдером не должна содержать ПД. "
    "Уберите email/телефон/номер документа из вопроса — ФИО, контакты и адреса "
    "подставляются в письма локально, на вашем устройстве. Если нужно проверить "
    "текст письма — используйте раздел «Запросы»: там письмо собирается без "
    "участия AI."
)

HINT_NOT_CONFIGURED = (
    "AI-помощник не настроен. Укажите переменные окружения LLM_API_KEY, "
    "LLM_BASE_URL и LLM_MODEL (например: LLM_BASE_URL=https://tokenlavka.com/v1, "
    "LLM_MODEL=gpt-6-luna) и перезапустите сервер. Всё остальное — письма, "
    "статусы, статистика — работает и без AI."
)


def detect_pii(text: str) -> list[str]:
    """Возвращает список типов найденных ПД (email, phone, card, ...)."""
    found: list[str] = []
    src = text or ""
    for kind, pattern in _PATTERNS:
        if pattern.search(src):
            found.append(kind)
    return found


# ------------------------------------------------------------------ настройки
def llm_config() -> dict[str, str]:
    return {
        "base_url": (os.getenv("LLM_BASE_URL") or "").rstrip("/"),
        "api_key": os.getenv("LLM_API_KEY") or "",
        "model": os.getenv("LLM_MODEL") or "",
    }


def is_configured() -> bool:
    cfg = llm_config()
    return bool(cfg["base_url"] and cfg["api_key"] and cfg["model"])


# --------------------------------------------------------------------- вызов
async def ask(question: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Возвращает dict: {blocked, warning} | {configured: False, hint} | {answer, model, usage}."""
    kinds = detect_pii(question)
    if kinds:
        return {
            "blocked": True,
            "kinds": kinds,
            "warning": PII_WARNING.format(kinds=", ".join(kinds)),
        }

    cfg = llm_config()
    if not (cfg["base_url"] and cfg["api_key"] and cfg["model"]):
        return {"configured": False, "hint": HINT_NOT_CONFIGURED}

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in (history or [])[-6:]:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role in ("user", "assistant") and content and not detect_pii(content):
            messages.append({"role": role, "content": content[:2000]})
    messages.append({"role": "user", "content": question.strip()})

    timeout = float(os.getenv("LLM_TIMEOUT", "60"))
    max_tokens = int(os.getenv("LLM_MAX_TOKENS", "800"))
    payload = {"model": cfg["model"], "messages": messages, "temperature": 0.3, "max_tokens": max_tokens}

    url = f"{cfg['base_url']}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {cfg['api_key']}",
                    "Content-Type": "application/json",
                },
            )
    except httpx.TimeoutException:
        return {"error": "timeout", "message": "AI-провайдер не ответил за отведённое время. Попробуйте ещё раз."}
    except httpx.HTTPError as exc:
        return {"error": "network", "message": f"Не удалось связаться с AI-провайдером: {exc.__class__.__name__}."}

    if resp.status_code == 401:
        return {"error": "unauthorized", "message": "AI-провайдер отклонил ключ (401). Проверьте LLM_API_KEY."}
    if resp.status_code == 402:
        return {"error": "payment", "message": "На балансе AI-провайдера закончились средства (402)."}
    if resp.status_code == 429:
        return {"error": "rate_limit", "message": "Слишком много запросов к AI-провайдеру (429). Подождите немного."}
    if resp.status_code >= 400:
        detail = ""
        try:
            detail = str(resp.json().get("error", ""))[:300]
        except Exception:  # noqa: BLE001
            detail = resp.text[:300]
        return {"error": f"http_{resp.status_code}", "message": f"AI-провайдер вернул ошибку {resp.status_code}. {detail}"}

    try:
        data = resp.json()
        choice = data["choices"][0]["message"]["content"]
    except Exception:  # noqa: BLE001
        return {"error": "bad_response", "message": "AI-провайдер вернул неожиданный формат ответа."}

    return {
        "answer": (choice or "").strip(),
        "model": data.get("model") or cfg["model"],
        "usage": data.get("usage") or {},
    }
