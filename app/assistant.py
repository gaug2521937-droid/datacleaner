"""AI-помощник по процедурам удаления данных.

Что улучшено в этой версии:
* контекст: ассистент видит сводку по вашим запросам (только счётчики и категории,
  никаких ПД) и отвечает применительно к ситуации;
* режимы: «совет» (по умолчанию), «план» (пошаговый план), «письмо» (структура
  требования без ваших данных), «жалоба» (что писать регулятору);
* потоковый ответ (SSE), чтобы текст появлялся по мере генерации;
* локальная база норм (app/knowledge.py) подмешивается в системный промт;
* кэш однотипных вопросов и защита от повторных запросов.

Жёсткие правила:
1. Никакие персональные данные не уходят в LLM: если в вопросе найден email /
   телефон / номер документа — запрос блокируется локально.
2. Все настройки только из переменных окружения: LLM_API_KEY, LLM_BASE_URL,
   LLM_MODEL. В коде ключей нет.
3. Если LLM не настроен — возвращаем подсказку, а не ошибку 500.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from typing import Any, AsyncIterator

import httpx

from .knowledge import facts_for_context

BASE_PROMPT = (
    "Ты — старший консультант сервиса DataCleaner по защите персональных данных. "
    "Помогаешь человеку удалить свои данные из брокеров данных, people-search сайтов, "
    "маркетинговых баз и поисковой выдачи, а также правильно оформить требования и жалобы.\n\n"
    "Твои темы:\n"
    "- права субъекта по 152-ФЗ (ст. 9, 14, 20, 21), GDPR (Art. 12, 15, 17, 21, 77, 79) "
    "и CCPA/CPRA (§1798.105, §1798.120, §1798.130);\n"
    "- сроки: РФ — ответ 10 рабочих дней (ст. 20), уничтожение до 30 дней (ст. 21); "
    "ЕС — один месяц (Art. 12(3)); Калифорния — 45 дней (§1798.130);\n"
    "- тактика: как давить на оператора, что делать при отказе, как подать жалобу "
    "в Роскомнадзор / DPA / CPPA, как считать ущерб;\n"
    "- цифровая гигиена: раздельные email, opt-out, удаление аккаунтов, снижение следа.\n\n"
    "Опорные нормы (используй их, не выдумывай новых):\n{facts}\n\n"
    "Жёсткие правила:\n"
    "1. НИКОГДА не проси у пользователя персональные данные: ФИО, email, телефон, адрес, "
    "номер документа, данные карты. Если они нужны — объясни, что их вписывают в шаблон "
    "письма локально, в приложении.\n"
    "2. Если пользователь сам прислал ПД — не повторяй их, попроси удалить сообщение.\n"
    "3. Отвечай по-русски, структурно: короткий вывод, затем нумерованные шаги, сроки и нормы. "
    "До 300 слов. Без воды и без «как языковая модель».\n"
    "4. Не выдумывай точные URL и email сервисов: если не уверен — скажи, что адрес надо "
    "проверить в политике конфиденциальности оператора.\n"
    "5. Ты не юрист: последней строкой добавь «Это информационная справка, а не юридическое заключение».\n"
    "6. Если в контексте есть статистика пользователя — используй её (сколько просрочено, "
    "где отказы), не переспрашивай очевидное."
)

MODE_PROMPTS = {
    "advice": "Режим: краткий практический совет. 3–6 шагов, сроки, нормы.",
    "plan": ("Режим: пошаговый план на 4 недели. Формат: Неделя 1 — …, Неделя 2 — … "
             "В каждом шаге укажи действие, срок и что считать результатом."),
    "letter": ("Режим: помочь составить требование об удалении. Дай структуру и формулировки "
               "БЕЗ персональных данных (вместо них — [ФИО], [email]). Укажи нормы и срок."),
    "complaint": ("Режим: жалоба регулятору. Объясни, какой орган (Роскомнадзор / DPA / CPPA), "
                  "что приложить, какие нормы цитировать, что просить в просительной части."),
}

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

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL = 600
_CACHE_MAX = 200


# --------------------------------------------------------------- PII-фильтр
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")),
    ("phone", re.compile(r"(?<![\w.])(?:\+\d{1,3}[\s\-().]*)?(?:\(\d{2,4}\)[\s\-]*)?\d[\d\s\-().]{7,}\d(?![\w.])")),
    ("card", re.compile(r"\b(?:\d[ \-]?){13,19}\b")),
    ("snils", re.compile(r"\b\d{3}[-\s]?\d{3}[-\s]?\d{3}[-\s]?\d{2}\b")),
    ("passport", re.compile(r"\b\d{2}\s?\d{2}\s?(?:№|N|no\.?)?\s?\d{6}\b")),
]


def detect_pii(text: str) -> list[str]:
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


def build_system_prompt(mode: str = "advice", context: dict[str, Any] | None = None) -> str:
    prompt = BASE_PROMPT.format(facts=facts_for_context())
    mode_line = MODE_PROMPTS.get((mode or "advice").lower())
    if mode_line:
        prompt += "\n\n" + mode_line
    if context:
        ctx = _context_line(context)
        if ctx:
            prompt += "\n\nКонтекст пользователя (обезличенный, без ПД): " + ctx
    return prompt


def _context_line(context: dict[str, Any]) -> str:
    """Сводка по запросам: только числа и категории."""
    if not context:
        return ""
    kpi = context.get("kpi") or {}
    parts = []
    if kpi:
        parts.append(
            f"всего запросов {kpi.get('total', 0)}, отправлено {kpi.get('sent', 0)}, "
            f"ждут ответа {kpi.get('waiting', 0)}, просрочено {kpi.get('overdue', 0)}, "
            f"удалено {kpi.get('deleted', 0)}, отказов {kpi.get('refused', 0)}, "
            f"черновиков {kpi.get('drafts', 0)}"
        )
    cats = context.get("by_category") or []
    if cats:
        parts.append("по категориям: " + ", ".join(f"{c.get('label')} — {c.get('count')}" for c in cats[:5]))
    overdue = context.get("overdue") or []
    if overdue:
        parts.append("просрочены сервисы: " + ", ".join(str(o.get("broker")) for o in overdue[:5]))
    return "; ".join(parts)


def _messages(question: str, history: list[dict[str, str]] | None,
              mode: str, context: dict[str, Any] | None) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": build_system_prompt(mode, context)}]
    for item in (history or [])[-8:]:
        role = item.get("role")
        content = (item.get("content") or "").strip()
        if role in ("user", "assistant") and content and not detect_pii(content):
            messages.append({"role": role, "content": content[:2000]})
    messages.append({"role": "user", "content": question.strip()})
    return messages


def _payload(question: str, history, mode, context, stream: bool) -> dict[str, Any]:
    cfg = llm_config()
    return {
        "model": cfg["model"],
        "messages": _messages(question, history, mode, context),
        "temperature": float(os.getenv("LLM_TEMPERATURE", "0.25")),
        "max_tokens": int(os.getenv("LLM_MAX_TOKENS", "900")),
        "stream": stream,
    }


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {llm_config()['api_key']}", "Content-Type": "application/json"}


def _cache_key(question: str, mode: str) -> str:
    return hashlib.sha256(f"{mode}|{question.strip().lower()}".encode()).hexdigest()


def _http_error(resp: httpx.Response) -> dict[str, Any]:
    if resp.status_code == 401:
        return {"error": "unauthorized", "message": "AI-провайдер отклонил ключ (401). Проверьте LLM_API_KEY."}
    if resp.status_code == 402:
        return {"error": "payment", "message": "На балансе AI-провайдера закончились средства (402)."}
    if resp.status_code == 429:
        return {"error": "rate_limit", "message": "Слишком много запросов к AI-провайдеру (429). Подождите немного."}
    detail = ""
    try:
        detail = str(resp.json().get("error", ""))[:300]
    except Exception:  # noqa: BLE001
        detail = resp.text[:300]
    return {"error": f"http_{resp.status_code}",
            "message": f"AI-провайдер вернул ошибку {resp.status_code}. {detail}"}


# --------------------------------------------------------------------- вызов
async def ask(question: str, history: list[dict[str, str]] | None = None,
              mode: str = "advice", context: dict[str, Any] | None = None) -> dict[str, Any]:
    kinds = detect_pii(question)
    if kinds:
        return {"blocked": True, "kinds": kinds, "warning": PII_WARNING.format(kinds=", ".join(kinds))}

    cfg = llm_config()
    if not (cfg["base_url"] and cfg["api_key"] and cfg["model"]):
        return {"configured": False, "hint": HINT_NOT_CONFIGURED}

    key = _cache_key(question, mode)
    cached = _CACHE.get(key)
    if cached and time.time() - cached[0] < _CACHE_TTL:
        return {**cached[1], "cached": True}

    timeout = float(os.getenv("LLM_TIMEOUT", "60"))
    url = f"{cfg['base_url']}/chat/completions"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, json=_payload(question, history, mode, context, False), headers=_headers())
    except httpx.TimeoutException:
        return {"error": "timeout", "message": "AI-провайдер не ответил за отведённое время. Попробуйте ещё раз."}
    except httpx.HTTPError as exc:
        return {"error": "network", "message": f"Не удалось связаться с AI-провайдером: {exc.__class__.__name__}."}

    if resp.status_code >= 400:
        return _http_error(resp)

    try:
        data = resp.json()
        answer = (data["choices"][0]["message"]["content"] or "").strip()
    except Exception:  # noqa: BLE001
        return {"error": "bad_response", "message": "AI-провайдер вернул неожиданный формат ответа."}

    result = {"answer": answer, "model": data.get("model") or cfg["model"], "usage": data.get("usage") or {},
              "mode": mode}
    if len(_CACHE) > _CACHE_MAX:
        _CACHE.clear()
    _CACHE[key] = (time.time(), result)
    return result


async def stream(question: str, history: list[dict[str, str]] | None = None,
                 mode: str = "advice", context: dict[str, Any] | None = None) -> AsyncIterator[dict[str, Any]]:
    """Генератор событий для SSE: {"delta": "..."} … {"done": true}."""
    kinds = detect_pii(question)
    if kinds:
        yield {"blocked": True, "warning": PII_WARNING.format(kinds=", ".join(kinds))}
        return

    cfg = llm_config()
    if not (cfg["base_url"] and cfg["api_key"] and cfg["model"]):
        yield {"not_configured": True, "hint": HINT_NOT_CONFIGURED}
        return

    key = _cache_key(question, mode)
    cached = _CACHE.get(key)
    if cached and time.time() - cached[0] < _CACHE_TTL:
        for i in range(0, len(cached[1]["answer"]), 120):
            yield {"delta": cached[1]["answer"][i:i + 120]}
        yield {"done": True, "cached": True, "model": cached[1].get("model")}
        return

    url = f"{cfg['base_url']}/chat/completions"
    collected: list[str] = []
    timeout = float(os.getenv("LLM_TIMEOUT", "90"))
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url,
                                     json=_payload(question, history, mode, context, True),
                                     headers=_headers()) as resp:
                if resp.status_code >= 400:
                    raw = await resp.aread()
                    try:
                        fake = httpx.Response(resp.status_code, content=raw, request=resp.request)
                        yield {"error_body": _http_error(fake)}
                    except Exception:  # noqa: BLE001
                        yield {"error": f"http_{resp.status_code}", "message": f"Ошибка провайдера {resp.status_code}"}
                    return
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    chunk = line[5:].strip()
                    if chunk == "[DONE]":
                        break
                    try:
                        obj = json.loads(chunk)
                        delta = obj.get("choices", [{}])[0].get("delta", {}).get("content") or ""
                    except (json.JSONDecodeError, IndexError, AttributeError):
                        continue
                    if delta:
                        collected.append(delta)
                        yield {"delta": delta}
    except httpx.TimeoutException:
        yield {"error": "timeout", "message": "AI-провайдер не ответил за отведённое время."}
        return
    except httpx.HTTPError as exc:
        yield {"error": "network", "message": f"Сеть недоступна: {exc.__class__.__name__}"}
        return

    answer = "".join(collected).strip()
    if answer:
        if len(_CACHE) > _CACHE_MAX:
            _CACHE.clear()
        _CACHE[key] = (time.time(), {"answer": answer, "model": cfg["model"], "mode": mode})
    yield {"done": True, "model": cfg["model"], "chars": len(answer)}


async def list_models() -> dict[str, Any]:
    """Список моделей провайдера — для выпадающего списка в настройках."""
    cfg = llm_config()
    if not (cfg["base_url"] and cfg["api_key"]):
        return {"ok": False, "detail": "AI не настроен", "models": []}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(f"{cfg['base_url']}/models",
                                    headers={"Authorization": f"Bearer {cfg['api_key']}"})
        if resp.status_code >= 400:
            return {"ok": False, "detail": f"Провайдер вернул {resp.status_code}", "models": []}
        data = resp.json()
        items = data.get("data") or data.get("models") or []
        models = []
        for item in items:
            mid = item.get("id") or item.get("name") if isinstance(item, dict) else str(item)
            if mid and not str(mid).startswith("tl-"):
                models.append(str(mid))
        return {"ok": True, "models": sorted(set(models)), "current": cfg["model"]}
    except httpx.HTTPError as exc:
        return {"ok": False, "detail": f"Сеть: {exc.__class__.__name__}", "models": []}
