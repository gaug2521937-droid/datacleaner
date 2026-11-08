"""Правовая база и генератор жалоб (без AI, без интернета).

Здесь только проверяемые нормы и шаблоны. Персональные данные подставляются
локально, в промт LLM они не уходят.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from .letters import _clean_list, _date_en, _date_ru, _pii_rows, _s

# ---------------------------------------------------------------- база знаний
# Используется как контекст для AI-помощника и как локальные шпаргалки,
# если AI не настроен.
FACTS: list[dict[str, str]] = [
    {
        "id": "152fz-14",
        "topic": "РФ · доступ",
        "text": "Ст. 14 152-ФЗ: субъект вправе получить сведения об обработке своих ПД — "
                "подтверждение факта обработки, правовые основания и цели, перечень данных и "
                "источники, сроки, порядок прекращения, получателей. Ответ — по ст. 20.",
    },
    {
        "id": "152fz-20",
        "topic": "РФ · сроки",
        "text": "Ст. 20 152-ФЗ: оператор отвечает на запрос субъекта в течение 10 рабочих дней "
                "с даты получения; срок может быть продлён не более чем на 5 рабочих дней "
                "с уведомлением субъекта. Отказ должен быть мотивирован письменно.",
    },
    {
        "id": "152fz-21",
        "topic": "РФ · удаление",
        "text": "Ст. 21 152-ФЗ: при достижении целей, отзыве согласия или выявлении неправомерной "
                "обработки оператор обязан прекратить обработку и уничтожить ПД в срок, не "
                "превышающий 30 дней с даты получения требования (если иное не предусмотрено "
                "законом или договором).",
    },
    {
        "id": "152fz-9",
        "topic": "РФ · согласие",
        "text": "Ст. 9 152-ФЗ: согласие можно отозвать в любой момент; после отзыва оператор "
                "обязан прекратить обработку и уничтожить данные, если нет иных законных оснований.",
    },
    {
        "id": "152fz-rkn",
        "topic": "РФ · жалоба",
        "text": "Жалоба на оператора подаётся в Роскомнадзор (через сайт ведомства или "
                "территориальное управление). Приложите копию требования, подтверждение "
                "отправки/получения и переписку. Параллельно возможен иск в суд.",
    },
    {
        "id": "gdpr-12",
        "topic": "ЕС · сроки",
        "text": "Art. 12(3) GDPR: контролёр отвечает без необоснованной задержки и в любом случае "
                "в течение месяца; срок можно продлить ещё на два месяца при сложности запроса "
                "с уведомлением заявителя.",
    },
    {
        "id": "gdpr-17",
        "topic": "ЕС · удаление",
        "text": "Art. 17 GDPR: право на удаление («право быть забытым») — данные удаляются без "
                "необоснованной задержки, включая копии, резервные копии и данные, переданные "
                "третьим лицам; контролёр обязан уведомить получателей данных.",
    },
    {
        "id": "gdpr-21",
        "topic": "ЕС · возражение",
        "text": "Art. 21 GDPR: право возразить против обработки, включая прямой маркетинг; после "
                "возражения обработка в целях маркетинга прекращается немедленно.",
    },
    {
        "id": "gdpr-77",
        "topic": "ЕС · жалоба",
        "text": "Art. 77 GDPR: жалоба в надзорный орган (DPA) страны проживания, работы или места "
                "предполагаемого нарушения. Art. 79 — право на судебную защиту, Art. 82 — "
                "компенсация вреда.",
    },
    {
        "id": "ccpa-105",
        "topic": "США/Калифорния · удаление",
        "text": "CCPA/CPRA §1798.105: право требовать удаления персональной информации; бизнес "
                "обязан направить указание провайдерам и подрядчикам. §1798.130 — ответ в течение "
                "45 дней с возможностью продления ещё на 45.",
    },
    {
        "id": "ccpa-optout",
        "topic": "США/Калифорния · продажа",
        "text": "CCPA/CPRA §1798.120: право отказаться от «продажи» и «передачи» (sharing) "
                "персональной информации; ссылка «Do Not Sell or Share My Personal Information» "
                "обязательна на сайте бизнеса.",
    },
    {
        "id": "people-search",
        "topic": "брокеры данных",
        "text": "People-search сайты (Spokeo, Whitepages, Radaris и др.) не всегда субъекты GDPR/"
                "CCPA, но у них есть собственные opt-out формы. Требуйте не только исключения "
                "карточки, а удаления данных из базы и из партнёрских фидов.",
    },
    {
        "id": "refusal",
        "topic": "если отказали",
        "text": "Типичные отказы: «данные из общедоступных источников», «мы не оператор», "
                "«нет подтверждения личности», «First Amendment» (США). Ответ: отзыв согласия "
                "действует и для общедоступных источников (ст. 21 152-ФЗ), вы — оператор, так как "
                "определяете цели обработки (Art. 4(7) GDPR); личность подтверждается минимально "
                "необходимыми данными (Art. 12(6) GDPR).",
    },
]


def facts_for_context(limit: int = 6) -> str:
    return "\n".join(f"- {f['topic']}: {f['text']}" for f in FACTS[:limit])


# ------------------------------------------------------------------- жалобы
def build_complaint_ru(profile: dict[str, Any], broker: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    today = date.today()
    name = _s(profile.get("full_name")) or "субъект персональных данных"
    emails = _clean_list(profile.get("emails"))
    reply = emails[0] if emails else ""
    broker_name = _s(broker.get("name")) or "оператор"
    sent_at = _s(request.get("sent_at"))[:10]
    deadline = _s(request.get("deadline_at"))[:10]

    subject = f"Жалоба на нарушение законодательства о персональных данных — {broker_name}"
    lines = [
        "В Федеральную службу по надзору в сфере связи,",
        "информационных технологий и массовых коммуникаций (Роскомнадзор)",
        "",
        f"Заявитель: {name}" + (f", {reply}" if reply else ""),
        f"Дата: {_date_ru(today)}",
        "",
        f"Жалоба на оператора: {broker_name}"
        + (f" ({_s(broker.get('url'))})" if _s(broker.get("url")) else ""),
        "",
        f"{_date_ru(today)} я направил(а) оператору требование об удалении моих персональных "
        "данных на основании статей 14 и 21 Федерального закона от 27.07.2006 № 152-ФЗ "
        "«О персональных данных».",
        "",
        "Сведения о требовании:",
        f"  • дата направления: {sent_at or 'указана в приложении'}",
        f"  • срок на уничтожение данных: {deadline or '30 дней с даты получения'}",
        "  • подтверждение отправки прилагается",
        "",
    ]
    rows = _pii_rows(profile, "ru")
    if rows:
        lines.append("Персональные данные, подлежащие удалению:")
        lines.extend(f"  • {r}" for r in rows)
        lines.append("")
    lines += [
        "На настоящее время оператор:",
        "  1) не предоставил ответ в порядке статьи 20 152-ФЗ;",
        "  2) не уничтожил персональные данные в срок, установленный статьёй 21 152-ФЗ;",
        "  3) не направил мотивированный отказ в письменной форме.",
        "",
        "На основании изложенного прошу:",
        "  1) провести проверку изложенных обстоятельств;",
        "  2) при выявлении нарушения выдать оператору предписание об устранении;",
        "  3) привлечь оператора к административной ответственности по статье 13.11 КоАП РФ;",
        "  4) уведомить меня о результатах рассмотрения обращения.",
        "",
        "Приложения: копия требования, подтверждение его направления, переписка с оператором "
        "(при наличии), скриншоты страниц с моими данными.",
        "",
        "С уважением,",
        name,
    ]
    if reply:
        lines.append(reply)
    return {"language": "ru", "kind": "complaint_rkn", "subject": subject, "body": "\n".join(lines).rstrip() + "\n"}


def build_complaint_en(profile: dict[str, Any], broker: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    today = date.today()
    name = _s(profile.get("full_name")) or "a data subject"
    emails = _clean_list(profile.get("emails"))
    reply = emails[0] if emails else ""
    broker_name = _s(broker.get("name")) or "the controller"
    sent_at = _s(request.get("sent_at"))[:10]
    deadline = _s(request.get("deadline_at"))[:10]

    subject = f"Complaint under Article 77 GDPR against {broker_name}"
    lines = [
        "To: the competent supervisory authority (Data Protection Authority)",
        "",
        f"Complainant: {name}" + (f" <{reply}>" if reply else ""),
        f"Date: {_date_en(today)}",
        "",
        f"Controller concerned: {broker_name}" + (f" — {_s(broker.get('url'))}" if _s(broker.get('url')) else ""),
        "",
        f"On {sent_at or '[date]'} I submitted an erasure request based on Articles 15, 17 and 21 GDPR "
        "and, where applicable, CCPA §1798.105. The controller failed to answer within the one-month "
        f"period of Article 12(3) GDPR (deadline: {deadline or '[date]'}) and did not erase my data.",
        "",
        "Summary of the facts:",
        "  1) the erasure request was delivered and acknowledged (proof attached);",
        "  2) no substantive reply was received within the statutory period;",
        "  3) my personal data remains publicly available and processed for marketing purposes.",
        "",
        "I therefore request that the supervisory authority:",
        "  1) investigate the controller's processing operations;",
        "  2) order the controller to comply with Articles 17 and 21 GDPR;",
        "  3) consider an administrative fine under Article 83 GDPR;",
        "  4) inform me of the outcome of the investigation.",
        "",
        "Attachments: copy of the erasure request, delivery confirmation, correspondence with the controller.",
        "",
        "Sincerely,",
        name,
    ]
    if reply:
        lines.append(reply)
    return {"language": "en", "kind": "complaint_dpa", "subject": subject, "body": "\n".join(lines).rstrip() + "\n"}


def build_complaint(profile: dict[str, Any], broker: dict[str, Any], request: dict[str, Any], language: str | None = None) -> dict[str, Any]:
    lang = _s(language) or _s(request.get("language")) or "ru"
    return build_complaint_ru(profile, broker, request) if lang == "ru" else build_complaint_en(profile, broker, request)
