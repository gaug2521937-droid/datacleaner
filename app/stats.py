"""Статистика воронки. Работает только с метаданными — ПД не расшифровываются.

Никакого «прочитано»: сервис принципиально не использует трекинг-пиксели,
поэтому единственные сигналы — факт отправки, ответ сервиса и подтверждение
удаления.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

CATEGORY_LABELS = {
    "people_search": "People-search",
    "data_broker": "Брокеры данных",
    "marketing": "Маркетинг",
    "search": "Поисковики",
    "custom": "Свои сервисы",
}

STAGE_ORDER = ["sent", "responded", "deleted", "refused", "draft"]
STAGE_LABELS = {
    "draft": "Черновики",
    "sent": "Отправлено",
    "responded": "Ответили",
    "deleted": "Удалено",
    "refused": "Отказ",
}

TIP_TEMPLATES = {
    "overdue": (
        "Просрочено {n}: оператор не ответил в срок. Напишите повторно (кнопка «Повторить»"
        " в карточке запроса) и через 5–10 рабочих дней жалуйтесь: в РФ — в Роскомнадзор, "
        "в ЕС — в надзорный орган вашей страны, в США (Калифорния) — в CPPA/Attorney General."
    ),
    "waiting": (
        "Ждут ответа {n}. Ответ на запрос по 152-ФЗ — 10 рабочих дней (ст. 20, продление "
        "не более чем на 5), уничтожение данных — до 30 дней (ст. 21). В GDPR срок ответа — "
        "один месяц (Art. 12(3)). Держите подтверждение отправки: скриншот формы или "
        "заголовки письма."
    ),
    "forms": (
        "Есть {n} запрос(ов) через формы и ручное удаление. По ним не будет письма-"
        "подтверждения — после отправки формы фиксируйте номер обращения в заметке "
        "к запросу, иначе нечем подтвердить срок."
    ),
    "refused": (
        "Отказов: {n}. Требуйте письменное обоснование со ссылкой на норму. "
        "Если основание «общедоступные данные» — ссылайтесь на ст. 21 152-ФЗ "
        "(отзыв согласия действует и для общедоступных источников) или Art. 17 GDPR."
    ),
    "noprofile": (
        "Профиль не заполнен: письма будут с пустыми полями. Заполните ФИО, email и "
        "телефон в разделе «Профиль» — данные хранятся только у вас."
    ),
    "drafts": "Черновиков: {n}. Проверьте текст и отправьте — пока запрос в черновике, срок не идёт.",
    "deleted": "Удалено {n}. Через 30–45 дней проверьте повторно: часть брокеров возвращает данные из резервных копий.",
}


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _days_between(a: datetime, b: datetime) -> float:
    return round((b - a).total_seconds() / 86400, 1)


def compute_stats(
    requests: Iterable[dict[str, Any]],
    today: date | None = None,
    profile_filled: bool = True,
    history_days: int = 14,
    demo: bool = False,
) -> dict[str, Any]:
    today = today or date.today()
    now = datetime.now(timezone.utc)
    rows = [r for r in requests]

    sent = [r for r in rows if r.get("sent_at")]
    waiting, overdue, deadlines = [], [], []
    response_times: list[float] = []
    per_day: Counter[str] = Counter()
    per_category: Counter[str] = Counter()
    stage_counts: Counter[str] = Counter()

    for r in rows:
        stage_counts[r.get("status", "draft")] += 1
        cat = r.get("broker_category") or "custom"
        if r.get("status") != "draft":
            per_category[cat] += 1

        sent_at = _parse(r.get("sent_at"))
        responded_at = _parse(r.get("responded_at"))
        deleted_at = _parse(r.get("deleted_at"))
        deadline = _parse(r.get("deadline_at")) or (
            sent_at + timedelta(days=int(r.get("deadline_days") or 30)) if sent_at else None
        )

        if sent_at:
            per_day[sent_at.date().isoformat()] += 1
        if responded_at and sent_at:
            response_times.append(_days_between(sent_at, responded_at))
        elif deleted_at and sent_at and r.get("status") == "deleted":
            response_times.append(_days_between(sent_at, deleted_at))

        status = r.get("status")
        if status in ("sent", "responded", "refused") and deadline:
            days_left = (deadline.date() - today).days
            item = {
                "id": r.get("id"),
                "broker": r.get("broker_name"),
                "category": cat,
                "status": status,
                "deadline": deadline.date().isoformat(),
                "days_left": days_left,
            }
            deadlines.append(item)
            if status == "sent":
                if days_left < 0:
                    overdue.append(item)
                else:
                    waiting.append(item)

    deadlines.sort(key=lambda x: x["days_left"])
    per_day_series = []
    for i in range(history_days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        per_day_series.append({"date": d, "count": per_day.get(d, 0)})

    total_non_draft = sum(1 for r in rows if r.get("status") != "draft")
    deleted_count = stage_counts.get("deleted", 0)
    deletion_rate = round(deleted_count / total_non_draft * 100, 1) if total_non_draft else 0.0
    answered = deleted_count + stage_counts.get("responded", 0) + stage_counts.get("refused", 0)
    response_rate = round(answered / len(sent) * 100, 1) if sent else 0.0

    funnel = []
    for stage in ("draft", "sent", "responded", "deleted"):
        funnel.append({
            "stage": stage,
            "label": STAGE_LABELS[stage],
            "count": stage_counts.get(stage, 0),
            "percent": round(stage_counts.get(stage, 0) / len(rows) * 100, 1) if rows else 0.0,
        })

    by_category = [
        {
            "category": cat,
            "label": CATEGORY_LABELS.get(cat, cat),
            "count": count,
            "percent": round(count / total_non_draft * 100, 1) if total_non_draft else 0.0,
        }
        for cat, count in sorted(per_category.items(), key=lambda kv: -kv[1])
    ]

    tips: list[str] = []
    if not profile_filled:
        tips.append(TIP_TEMPLATES["noprofile"].format())
    if overdue:
        tips.append(TIP_TEMPLATES["overdue"].format(n=len(overdue)))
    if waiting:
        tips.append(TIP_TEMPLATES["waiting"].format(n=len(waiting)))
    forms = sum(1 for r in rows if r.get("method") in ("form", "manual") and r.get("status") != "draft")
    if forms:
        tips.append(TIP_TEMPLATES["forms"].format(n=forms))
    if stage_counts.get("refused"):
        tips.append(TIP_TEMPLATES["refused"].format(n=stage_counts["refused"]))
    if stage_counts.get("draft"):
        tips.append(TIP_TEMPLATES["drafts"].format(n=stage_counts["draft"]))
    if deleted_count:
        tips.append(TIP_TEMPLATES["deleted"].format(n=deleted_count))
    if not tips:
        tips.append("Добавьте первые запросы: выберите сервис в каталоге и сгенерируйте письмо.")

    avg_response = round(sum(response_times) / len(response_times), 1) if response_times else None
    oldest_overdue = max((abs(d["days_left"]) for d in overdue), default=0)

    return {
        "demo": demo,
        "generated_at": now.replace(microsecond=0).isoformat(),
        "kpi": {
            "total": len(rows),
            "sent": len(sent),
            "waiting": len(waiting),
            "overdue": len(overdue),
            "deleted": deleted_count,
            "responded": stage_counts.get("responded", 0),
            "refused": stage_counts.get("refused", 0),
            "drafts": stage_counts.get("draft", 0),
            "deletion_rate": deletion_rate,
            "response_rate": response_rate,
            "avg_response_days": avg_response,
            "oldest_overdue_days": oldest_overdue,
        },
        "funnel": funnel,
        "activity": per_day_series,
        "by_category": by_category,
        "deadlines": deadlines,
        "tips": tips,
        "note": (
            "«Прочитано» не отслеживается: сервис не использует трекинг-пиксели и "
            "внешние картинки в письмах — это защищает приватность получателя. "
            "Учитываются только ответы сервисов и подтверждения удаления."
        ),
    }
