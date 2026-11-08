"""Генерация писем об удалении персональных данных.

Правила:
* персональные данные подставляются ЛОКАЛЬНО, никуда не отправляются;
* пустые поля в текст не попадают (никаких «ФИО: », «Адрес: —»);
* русский шаблон ссылается на ст. 14 и ст. 21 152-ФЗ и срок 30 дней;
* английский шаблон ссылается на Art. 17 GDPR и CCPA §1798.105;
* письмо не содержит трекинг-пикселей — «прочитано» не отслеживается никогда.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any, Iterable

DEFAULT_DEADLINE_DAYS = 30

LEGAL_RU = [
    "ст. 14 152-ФЗ — право субъекта на доступ к своим персональным данным",
    "ст. 21 152-ФЗ — обязанность оператора прекратить обработку и уничтожить данные",
    "ст. 9 152-ФЗ — отзыв согласия на обработку",
    "ст. 20 152-ФЗ — срок ответа на запрос субъекта",
]
LEGAL_EN = [
    "Art. 15 GDPR — right of access",
    "Art. 17 GDPR — right to erasure ('right to be forgotten')",
    "Art. 21 GDPR — right to object",
    "Art. 12(3) GDPR — ответ в течение одного месяца",
    "CCPA/CPRA §1798.105 — right to delete, §1798.130 — срок 45 дней",
]


# --------------------------------------------------------------------- helpers
def _s(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _clean_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        parts: Iterable[str] = value.replace(";", ",").split(",")
    else:
        parts = value
    out: list[str] = []
    for item in parts:
        item = _s(item)
        if item and item not in out:
            out.append(item)
    return out


def _join(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " и " + items[-1]


def _date_ru(d: date) -> str:
    months = [
        "января", "февраля", "марта", "апреля", "мая", "июня",
        "июля", "августа", "сентября", "октября", "ноября", "декабря",
    ]
    return f"{d.day} {months[d.month - 1]} {d.year} г."


def _date_en(d: date) -> str:
    return d.strftime("%d %B %Y")


def _pii_rows(profile: dict, lang: str) -> list[str]:
    """Строки «поле: значение» — только для заполненных полей."""
    rows: list[str] = []
    name = _s(profile.get("full_name") or profile.get("fullName"))
    emails = _clean_list(profile.get("emails"))
    phones = _clean_list(profile.get("phones"))
    city = _s(profile.get("city"))
    birth_year = _s(profile.get("birth_year") or profile.get("birthYear"))
    address = _s(profile.get("address"))

    if lang == "ru":
        if name:
            rows.append(f"ФИО: {name}")
        if emails:
            rows.append(f"Адрес электронной почты: {', '.join(emails)}")
        if phones:
            rows.append(f"Номер телефона: {', '.join(phones)}")
        if birth_year:
            rows.append(f"Год рождения: {birth_year}")
        if city:
            rows.append(f"Город: {city}")
        if address:
            rows.append(f"Адрес: {address}")
    else:
        if name:
            rows.append(f"Full name: {name}")
        if emails:
            rows.append(f"Email address(es): {', '.join(emails)}")
        if phones:
            rows.append(f"Phone number(s): {', '.join(phones)}")
        if birth_year:
            rows.append(f"Year of birth: {birth_year}")
        if city:
            rows.append(f"City: {city}")
        if address:
            rows.append(f"Postal address: {address}")
    return rows


def _broker_name(broker: dict) -> str:
    return _s(broker.get("name")) or _s(broker.get("id")) or "сервис"


def _reply_channel(profile: dict, lang: str) -> str:
    emails = _clean_list(profile.get("emails"))
    if emails:
        return emails[0] if lang == "en" else emails[0]
    phones = _clean_list(profile.get("phones"))
    if phones:
        return phones[0]
    return ""


# ------------------------------------------------------------------- templates
def build_ru_letter(profile: dict, broker: dict, today: date | None = None) -> dict:
    today = today or date.today()
    name = _s(profile.get("full_name") or profile.get("fullName"))
    subject_name = name or "субъекта персональных данных"
    rows = _pii_rows(profile, "ru")
    reply = _reply_channel(profile, "ru")
    service = _broker_name(broker)

    subject = f"Требование об удалении персональных данных — {subject_name}"

    parts: list[str] = [
        f"Кому: {service}"
        + (f" ({_s(broker.get('email'))})" if _s(broker.get("email")) else ""),
        f"От: {subject_name}" + (f", {reply}" if reply else ""),
        f"Дата: {_date_ru(today)}",
        "",
        "Здравствуйте!",
        "",
        "Я являюсь субъектом персональных данных и обращаюсь к вам как к оператору, "
        f"осуществляющему обработку персональных данных (сервис: {service}).",
        "",
    ]

    if rows:
        parts.append("В вашем сервисе обрабатываются следующие мои персональные данные:")
        parts.append("")
        parts.extend(f"  • {r}" for r in rows)
        parts.append("")

    parts += [
        "На основании статьи 14 Федерального закона от 27.07.2006 № 152-ФЗ "
        "«О персональных данных» прошу предоставить мне сведения, предусмотренные "
        "частью 7 указанной статьи, в том числе:",
        "  1) подтверждение факта обработки моих персональных данных;",
        "  2) правовые основания и цели обработки;",
        "  3) перечень обрабатываемых персональных данных и источники их получения;",
        "  4) сроки обработки, а также порядок и условия их прекращения;",
        "  5) сведения о лицах, которым могут быть переданы мои персональные данные.",
        "",
        "Одновременно, на основании статьи 21 152-ФЗ, требую:",
        "  1) прекратить обработку моих персональных данных;",
        "  2) уничтожить (удалить) мои персональные данные, включая их копии, "
        "резервные копии, а также данные, переданные третьим лицам и партнёрам;",
        "  3) исключить мои данные из поисковой выдачи, профилей и открытых карточек;",
        "  4) прекратить использование моих данных в целях рекламы и маркетинга "
        "и отозвать переданные ранее согласия (статья 9 152-ФЗ);",
        "  5) направить мне письменное подтверждение уничтожения персональных данных.",
        "",
        "Согласно частям 1, 3 и 5 статьи 21 152-ФЗ обработка должна быть прекращена, "
        "а персональные данные уничтожены в срок, не превышающий 30 дней с даты "
        "получения настоящего требования. Ответ на запрос субъекта персональных данных "
        "предоставляется в порядке и сроки, установленные статьёй 20 152-ФЗ.",
        "",
    ]

    if reply:
        parts.append(
            f"Ответ прошу направить в письменной форме на адрес электронной почты: {reply}."
        )
    else:
        parts.append(
            "Ответ прошу направить в письменной форме по указанным выше контактным данным."
        )

    parts += [
        "",
        "В случае неисполнения требования я оставляю за собой право обратиться "
        "в Роскомнадзор с жалобой на нарушение законодательства о персональных данных, "
        "а также в суд.",
        "",
        "Прошу не использовать мои персональные данные для иных целей, кроме "
        "рассмотрения настоящего требования.",
        "",
        "С уважением,",
        subject_name,
    ]
    if reply:
        parts.append(reply)

    body = "\n".join(parts).rstrip() + "\n"
    return {
        "language": "ru",
        "subject": subject,
        "body": body,
        "legal": LEGAL_RU,
        "deadline_days": int(broker.get("deadline_days") or DEFAULT_DEADLINE_DAYS),
        "deadline_date": (today + timedelta(days=int(broker.get("deadline_days") or DEFAULT_DEADLINE_DAYS))).isoformat(),
    }


def build_en_letter(profile: dict, broker: dict, today: date | None = None) -> dict:
    today = today or date.today()
    name = _s(profile.get("full_name") or profile.get("fullName"))
    subject_name = name or "a data subject"
    rows = _pii_rows(profile, "en")
    reply = _reply_channel(profile, "en")
    service = _broker_name(broker)

    subject = f"Formal request for erasure of personal data (GDPR Art. 17 / CCPA §1798.105) — {subject_name}"

    parts: list[str] = [
        f"To: {service}" + (f" — {_s(broker.get('email'))}" if _s(broker.get("email")) else " — Privacy / DPO"),
        f"From: {subject_name}" + (f" <{reply}>" if reply else ""),
        f"Date: {_date_en(today)}",
        "",
        "Dear Sir or Madam,",
        "",
        "I am writing to exercise my rights as a data subject under the EU General Data "
        "Protection Regulation (Regulation (EU) 2016/679) and, where applicable, the "
        f"California Consumer Privacy Act as amended by the CPRA. The processing concerns "
        f"the service {service}.",
        "",
    ]

    if rows:
        parts.append("The personal data concerned:")
        parts.append("")
        parts.extend(f"  • {r}" for r in rows)
        parts.append("")

    parts += [
        "Under Article 15 GDPR I request confirmation of whether you process personal "
        "data concerning me, together with a copy of that data, the purposes of the "
        "processing, the categories of data, the recipients, the retention period and "
        "the source of the data.",
        "",
        "Under Article 17 GDPR I request the erasure of my personal data without undue "
        "delay, including any copies, backups, derived profiles, and data shared with "
        "third parties, affiliates and marketing partners. Under Article 21 GDPR I object "
        "to the processing of my personal data for direct marketing purposes.",
        "",
        "Where you are a business subject to the CCPA/CPRA, I request the deletion of my "
        "personal information pursuant to §1798.105 and confirmation that you have "
        "directed service providers and contractors to delete it as well. I do not wish "
        "my personal information to be sold or shared (§1798.120, §1798.121).",
        "",
        "Please confirm in writing, within one month as required by Article 12(3) GDPR "
        "(45 days under §1798.130 CCPA), that my personal data has been erased and that "
        "no further processing will take place.",
        "",
    ]

    if reply:
        parts.append(f"Please send your written confirmation to: {reply}.")
    else:
        parts.append("Please send your written confirmation to the contact details above.")

    parts += [
        "",
        "I am ready to provide reasonable proof of identity if required, and I ask you "
        "not to request more personal data than is necessary to verify it.",
        "",
        "If you fail to act on this request, I reserve the right to lodge a complaint with "
        "the competent supervisory authority in my country, with the California Privacy "
        "Protection Agency or the California Attorney General, and to seek a judicial remedy.",
        "",
        "Sincerely,",
        subject_name,
    ]
    if reply:
        parts.append(reply)

    body = "\n".join(parts).rstrip() + "\n"
    return {
        "language": "en",
        "subject": subject,
        "body": body,
        "legal": LEGAL_EN,
        "deadline_days": int(broker.get("deadline_days") or DEFAULT_DEADLINE_DAYS),
        "deadline_date": (today + timedelta(days=int(broker.get("deadline_days") or DEFAULT_DEADLINE_DAYS))).isoformat(),
    }


def build_letter(profile: dict, broker: dict, today: date | None = None, language: str | None = None) -> dict:
    """Выбирает язык письма: явный аргумент -> язык брокера -> язык профиля -> ru."""
    lang = _s(language) or _s(broker.get("language")) or _s(profile.get("language")) or "ru"
    if lang not in ("ru", "en"):
        lang = "ru"
    return build_ru_letter(profile, broker, today) if lang == "ru" else build_en_letter(profile, broker, today)


# ------------------------------------------------------------ напоминание
def build_followup(profile: dict, broker: dict, language: str | None = None,
                   today: date | None = None, original_date: str | None = None) -> dict:
    """Напоминание оператору, который не ответил в срок (30 дней / месяц по GDPR)."""
    lang = _s(language) or _s(broker.get("language")) or _s(profile.get("language")) or "ru"
    today = today or date.today()
    name = _s(profile.get("full_name"))
    service = _broker_name(broker)
    reply = _reply_channel(profile, lang)
    original = _s(original_date)[:10]

    if lang == "en":
        subject = f"Second request — failure to answer the erasure request (GDPR Art. 17, 12(3)) — {service}"
        parts = [
            f"To: {service}" + (f" — {_s(broker.get('email'))}" if _s(broker.get("email")) else " — Privacy / DPO"),
            f"From: {name or 'a data subject'}" + (f" <{reply}>" if reply else ""),
            f"Date: {_date_en(today)}",
            "",
            "Dear Sir or Madam,",
            "",
            f"On {original or '[date]'} I submitted a request for erasure of my personal data under "
            "Articles 15, 17 and 21 GDPR and CCPA §1798.105. The one-month period set by Article 12(3) "
            "GDPR has expired and I have not received a substantive reply.",
            "",
            "I repeat the request: erase my personal data, including copies, backups and data shared "
            "with third parties, and confirm the erasure in writing.",
            "",
            "If I do not receive a reply within 14 days, I will lodge a complaint with the supervisory "
            "authority under Article 77 GDPR and may seek a judicial remedy under Article 79 GDPR, "
            "including compensation for damage under Article 82 GDPR.",
            "",
            "Sincerely,",
            name or "A data subject",
        ]
        if reply:
            parts.append(reply)
    else:
        subject = f"Повторное требование об удалении персональных данных — {service}"
        parts = [
            f"Кому: {service}" + (f" ({_s(broker.get('email'))})" if _s(broker.get("email")) else ""),
            f"От: {name or 'субъекта персональных данных'}" + (f", {reply}" if reply else ""),
            f"Дата: {_date_ru(today)}",
            "",
            "Здравствуйте!",
            "",
            f"{_date_ru(today)} направляю повторное требование. Ранее, "
            f"{original or '[дата]'}, я уже требовал(а) удалить мои персональные данные на основании "
            "статей 14 и 21 Федерального закона № 152-ФЗ «О персональных данных».",
            "",
            "Срок, установленный статьёй 21 152-ФЗ (30 дней с даты получения требования), истёк, "
            "ответ в порядке статьи 20 152-ФЗ не получен, данные не уничтожены.",
            "",
            "Повторно требую:",
            "  1) прекратить обработку и уничтожить мои персональные данные, включая копии и "
            "резервные копии, а также данные, переданные третьим лицам;",
            "  2) направить мне письменное подтверждение уничтожения.",
            "",
            "Если в течение 14 дней ответ не поступит, я обращусь с жалобой в Роскомнадзор "
            "и в суд, а также поставлю вопрос о взыскании компенсации морального вреда.",
            "",
            "С уважением,",
            name or "субъект персональных данных",
        ]
        if reply:
            parts.append(reply)

    return {
        "language": lang,
        "kind": "followup",
        "subject": subject,
        "body": "\n".join(parts).rstrip() + "\n",
        "deadline_days": 14,
        "deadline_date": (today + timedelta(days=14)).isoformat(),
    }
