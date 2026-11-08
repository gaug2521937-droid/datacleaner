"""Отправка писем: SMTP **или** HTTPS-API почтового провайдера.

Зачем два транспорта. Бесплатные инстансы на многих хостингах (в том числе
Render Free) блокируют исходящие соединения на порты 25, 465 и 587 — то есть
обычный SMTP «из сервера» там физически не подключается. HTTPS (443) при этом
работает всегда, поэтому для таких хостингов есть второй транспорт: Brevo API
и Resend API (оба бесплатны на старте).

Порядок выбора транспорта (`transport()`):
1. `MAIL_PROVIDER=brevo|resend|smtp` — если задан явно;
2. `BREVO_API_KEY` → brevo, `RESEND_API_KEY` → resend;
3. SMTP из интерфейса (таблица kv) или переменных `SMTP_*`;
4. иначе `none` — отправлять нечем, письма остаются на сервере.

DRY_RUN=1 по умолчанию: письмо собирается полностью, но не отправляется.

Письма — только text/plain. Никаких HTML, пикселей и внешних картинок:
получатель — не объект слежки.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Any

import httpx

from . import google_oauth

# Порты, которые обычно закрыты на бесплатных PaaS (Render Free и подобных).
BLOCKED_SMTP_PORTS = (25, 465, 587)

HTTP_PROVIDERS: dict[str, dict[str, str]] = {
    "brevo": {
        "label": "Brevo API (HTTPS, 300 писем в день бесплатно)",
        "env_key": "BREVO_API_KEY",
        "url": "https://api.brevo.com/v3/smtp/email",
        "probe_url": "https://api.brevo.com/v3/account",
        "docs": "https://app.brevo.com/settings/keys/api",
    },
    "resend": {
        "label": "Resend API (HTTPS, тестовый тариф без домена — только на свой адрес)",
        "env_key": "RESEND_API_KEY",
        "url": "https://api.resend.com/emails",
        "probe_url": "https://api.resend.com/domains",
        "docs": "https://resend.com/api-keys",
    },
}


# --------------------------------------------------------------- конфигурация
def smtp_config() -> dict[str, Any]:
    """SMTP из окружения (запасной источник, если в интерфейсе пусто)."""
    return {
        "host": os.getenv("SMTP_HOST", "").strip(),
        "port": int(os.getenv("SMTP_PORT", "587") or 587),
        "user": os.getenv("SMTP_USER", "").strip(),
        "password": os.getenv("SMTP_PASS", ""),
        "from_addr": (os.getenv("SMTP_FROM") or os.getenv("EMAIL_FROM") or os.getenv("SMTP_USER") or "").strip(),
        "from_name": (os.getenv("SMTP_FROM_NAME") or os.getenv("EMAIL_FROM_NAME") or "DataCleaner").strip(),
        "use_ssl": os.getenv("SMTP_SSL", "0") in ("1", "true", "True"),
        "use_starttls": os.getenv("SMTP_STARTTLS", "1") in ("1", "true", "True"),
    }


def dry_run_enabled() -> bool:
    return os.getenv("DRY_RUN", "1") not in ("0", "false", "False", "no")


def _flag(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def http_provider() -> str | None:
    """Явный MAIL_PROVIDER, иначе автоопределение по ключам."""
    explicit = (os.getenv("MAIL_PROVIDER") or "").strip().lower()
    if explicit in HTTP_PROVIDERS:
        return explicit
    if explicit == "smtp":
        return None
    for name, meta in HTTP_PROVIDERS.items():
        if (os.getenv(meta["env_key"]) or "").strip():
            return name
    return None


def http_api_key(provider: str | None = None) -> str:
    provider = provider or http_provider()
    if not provider:
        return ""
    return (os.getenv(HTTP_PROVIDERS[provider]["env_key"]) or "").strip()


def email_from(cfg: dict[str, Any] | None = None) -> str:
    """Адрес отправителя: EMAIL_FROM → SMTP_FROM → настройки из интерфейса."""
    for key in ("EMAIL_FROM", "SMTP_FROM", "BREVO_FROM", "RESEND_FROM"):
        value = (os.getenv(key) or "").strip()
        if value and "@" in value:
            return value
    cfg = cfg or {}
    return (cfg.get("from_addr") or cfg.get("user") or "").strip()


def from_name(cfg: dict[str, Any] | None = None) -> str:
    return ((os.getenv("EMAIL_FROM_NAME") or os.getenv("SMTP_FROM_NAME") or "").strip()
            or (cfg or {}).get("from_name") or "DataCleaner")


def is_smtp_configured(cfg: dict[str, Any] | None = None) -> bool:
    cfg = cfg or smtp_config()
    return bool(cfg.get("host") and email_from(cfg))


def transport(cfg: dict[str, Any] | None = None) -> str:
    """Какой транспорт будет использован: google | brevo | resend | smtp | none."""
    if (cfg or {}).get("google_access"):
        return "google"
    provider = http_provider()
    if provider and email_from(cfg):
        return provider
    if is_smtp_configured(cfg):
        return "smtp"
    return "none"


def mail_ready(cfg: dict[str, Any] | None = None) -> bool:
    """Можно ли отправлять письма (без учёта DRY_RUN)."""
    return transport(cfg) != "none"


def transport_info(cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    """Короткая сводка для /api/health и интерфейса (без секретов)."""
    kind = transport(cfg)
    provider = http_provider()
    notes = []
    port = int((cfg or {}).get("port") or 587)
    if kind == "smtp" and port in BLOCKED_SMTP_PORTS:
        notes.append(
            f"Порт {port} часто закрыт на бесплатных хостингах (Render Free блокирует 25/465/587). "
            "Если отправка не идёт — укажите порт 2525 (поддерживают Brevo/SendGrid) "
            "или подключите HTTPS-API: BREVO_API_KEY / RESEND_API_KEY."
        )
    if kind == "none":
        notes.append(
            "Почта не подключена. Проще всего — «Войти через Google» в «Автопилоте» (без паролей приложений). "
            "Альтернативы: SMTP с паролем приложения или BREVO_API_KEY / RESEND_API_KEY + EMAIL_FROM."
        )
    return {
        "kind": kind,
        "http_provider": provider,
        "google": bool((cfg or {}).get("google_access")),
        "label": ("Вход через Google (Gmail API, HTTPS)" if kind == "google" else
                  HTTP_PROVIDERS[provider]["label"] if provider and kind == provider else
                  ("SMTP" if kind == "smtp" else "не настроено")),
        "from_addr": email_from(cfg) or "",
        "notes": notes,
    }


# ------------------------------------------------------------------- письмо
def build_message(to_email: str, subject: str, body: str, reply_to: str | None = None,
                  cfg: dict[str, Any] | None = None) -> EmailMessage:
    cfg = cfg or smtp_config()
    addr = email_from(cfg) or "noreply@localhost"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((from_name(cfg), addr))
    msg["To"] = to_email
    if reply_to:
        msg["Reply-To"] = reply_to
    domain = addr.split("@")[-1] if "@" in addr else "datacleaner.local"
    msg["Message-ID"] = make_msgid(domain=domain)
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(body, subtype="plain", charset="utf-8")
    return msg


def _connect(cfg: dict[str, Any], timeout: int = 25):
    if cfg.get("use_ssl"):
        ctx = ssl.create_default_context()
        return smtplib.SMTP_SSL(cfg["host"], int(cfg.get("port") or 465), timeout=timeout, context=ctx)
    smtp = smtplib.SMTP(cfg["host"], int(cfg.get("port") or 587), timeout=timeout)
    if cfg.get("use_starttls"):
        smtp.starttls(context=ssl.create_default_context())
    return smtp


# --------------------------------------------------------------- HTTPS-API
def _http_post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> httpx.Response:
    with httpx.Client(timeout=25) as client:
        return client.post(url, json=payload, headers=headers)


def _http_get(url: str, headers: dict[str, str]) -> httpx.Response:
    with httpx.Client(timeout=20) as client:
        return client.get(url, headers=headers)


def _http_payload(provider: str, to_email: str, subject: str, body: str,
                  reply_to: str | None, cfg: dict[str, Any] | None) -> dict[str, Any]:
    sender = email_from(cfg)
    name = from_name(cfg)
    if provider == "brevo":
        payload: dict[str, Any] = {
            "sender": {"email": sender, "name": name},
            "to": [{"email": to_email}],
            "subject": subject,
            "textContent": body,
        }
        if reply_to:
            payload["replyTo"] = {"email": reply_to}
        return payload
    payload = {
        "from": f"{name} <{sender}>",
        "to": [to_email],
        "subject": subject,
        "text": body,
    }
    if reply_to:
        payload["reply_to"] = reply_to
    return payload


def _http_headers(provider: str) -> dict[str, str]:
    key = http_api_key(provider)
    if provider == "brevo":
        return {"api-key": key, "Content-Type": "application/json", "Accept": "application/json"}
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _http_error_detail(provider: str, response: httpx.Response) -> str:
    try:
        data = response.json()
    except Exception:  # noqa: BLE001
        data = {}
    message = ""
    if isinstance(data, dict):
        message = str(data.get("message") or data.get("error") or data.get("detail") or "")
        if isinstance(data.get("error"), dict):
            message = str(data["error"].get("message") or message)
    if response.status_code in (401, 403):
        return (f"{provider}: ключ не принят ({response.status_code}). Проверьте "
                f"{HTTP_PROVIDERS[provider]['env_key']} и что адрес отправителя "
                f"({email_from() or 'EMAIL_FROM'}) подтверждён в кабинете провайдера.{(' ' + message) if message else ''}")
    if response.status_code == 429:
        return f"{provider}: превышен лимит писем (429). Подождите или перейдите на другой тариф."
    if response.status_code >= 500:
        return f"{provider}: временная ошибка сервиса ({response.status_code}). Повторите позже."
    return f"{provider}: ошибка {response.status_code}. {message[:200]}"


def send_via_http(provider: str, to_email: str, subject: str, body: str,
                  reply_to: str | None = None, cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    meta = HTTP_PROVIDERS[provider]
    if not http_api_key(provider):
        return {"ok": False, "dry_run": False,
                "detail": f"Не задан {meta['env_key']} — HTTPS-отправка через {provider} недоступна."}
    if not email_from(cfg):
        return {"ok": False, "dry_run": False,
                "detail": "Не задан адрес отправителя: укажите EMAIL_FROM (адрес, подтверждённый у провайдера)."}
    payload = _http_payload(provider, to_email, subject, body, reply_to, cfg)
    try:
        response = _http_post_json(meta["url"], payload, _http_headers(provider))
    except httpx.HTTPError as exc:
        return {"ok": False, "dry_run": False, "transport": provider,
                "detail": f"{provider}: сеть недоступна ({exc.__class__.__name__})."}
    if response.status_code >= 400:
        return {"ok": False, "dry_run": False, "transport": provider,
                "detail": _http_error_detail(provider, response)}
    try:
        data = response.json()
    except Exception:  # noqa: BLE001
        data = {}
    message_id = str(data.get("messageId") or data.get("id") or "")
    return {"ok": True, "dry_run": False, "transport": provider,
            "detail": f"Письмо отправлено на {to_email} через {meta['label']}.",
            "message_id": message_id}


# ------------------------------------------------------------------ проверка
def verify_smtp(cfg: dict[str, Any], probe_to: str | None = None) -> dict[str, Any]:
    """Проверка соединения и логина без отправки письма (EHLO + NOOP)."""
    if not cfg.get("host"):
        return {"ok": False, "detail": "Не задан SMTP-сервер (host)."}
    try:
        with _connect(cfg) as smtp:
            smtp.ehlo()
            if cfg.get("user"):
                smtp.login(cfg["user"], cfg.get("password", ""))
            smtp.noop()
            if probe_to:
                msg = build_message(probe_to, "DataCleaner: проверка отправки",
                                    "Это тестовое письмо. Если вы его видите — почта настроена верно, "
                                    "и запросы на удаление данных будут уходить автоматически.", cfg=cfg)
                smtp.send_message(msg)
                return {"ok": True, "transport": "smtp",
                        "detail": f"Соединение и логин в порядке. Тестовое письмо отправлено на {probe_to}."}
            return {"ok": True, "transport": "smtp",
                    "detail": "Соединение и логин в порядке. Письма можно отправлять."}
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "transport": "smtp",
                "detail": "Сервер отклонил логин или пароль. Для Gmail/Яндекс/Mail.ru нужен "
                          "«пароль приложения», а не пароль от почты."}
    except smtplib.SMTPException as exc:
        return {"ok": False, "transport": "smtp", "detail": f"SMTP-ошибка: {exc.__class__.__name__}: {exc}"}
    except (OSError, ssl.SSLError) as exc:
        port = int(cfg.get("port") or 587)
        extra = ""
        if port in BLOCKED_SMTP_PORTS:
            extra = (" Похоже, хостинг блокирует исходящий SMTP на этом порту (Render Free закрывает 25/465/587): "
                     "попробуйте порт 2525 у провайдера или HTTPS-API (BREVO_API_KEY / RESEND_API_KEY).")
        return {"ok": False, "transport": "smtp",
                "detail": f"Не удалось подключиться к {cfg.get('host')}:{port} "
                          f"({exc.__class__.__name__}).{extra}"}


def verify_http(provider: str, probe_to: str | None = None) -> dict[str, Any]:
    """Проверка ключа провайдера; при probe_to — тестовое письмо."""
    meta = HTTP_PROVIDERS[provider]
    if not http_api_key(provider):
        return {"ok": False, "transport": provider, "detail": f"Не задан {meta['env_key']}."}
    try:
        response = _http_get(meta["probe_url"], _http_headers(provider))
        if response.status_code in (401, 403):
            return {"ok": False, "transport": provider,
                    "detail": f"{provider}: ключ не принят ({response.status_code}). Проверьте {meta['env_key']}."}
        if response.status_code >= 400:
            return {"ok": False, "transport": provider,
                    "detail": f"{provider}: проверка ключа вернула {response.status_code}."}
    except httpx.HTTPError as exc:
        return {"ok": False, "transport": provider,
                "detail": f"{provider}: сеть недоступна ({exc.__class__.__name__})."}
    if probe_to:
        result = send_via_http(provider, probe_to, "DataCleaner: проверка отправки",
                               "Это тестовое письмо через HTTPS-API провайдера. Если вы его видите — "
                               "всё настроено верно, и требования об удалении данных будут уходить сами.", cfg=None)
        return {**result, "detail": ("Ключ в порядке. " + result["detail"]) if result["ok"] else result["detail"]}
    return {"ok": True, "transport": provider,
            "detail": f"{provider}: ключ принят. Письма будут отправляться через HTTPS-API."}


def verify_mail(cfg: dict[str, Any] | None = None, probe_to: str | None = None) -> dict[str, Any]:
    """Единая проверка: HTTPS-API, если он выбран, иначе SMTP."""
    kind = transport(cfg)
    if kind in HTTP_PROVIDERS:
        return verify_http(kind, probe_to)
    if kind == "smtp":
        return verify_smtp(cfg or smtp_config(), probe_to)
    return {"ok": False, "transport": "none",
            "detail": "Почта не настроена: заполните SMTP в «Автопилоте» или задайте "
                      "BREVO_API_KEY / RESEND_API_KEY и EMAIL_FROM в переменных окружения."}


# ------------------------------------------------------------------ отправка
def send_email(
    to_email: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
    force_dry_run: bool | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Возвращает {ok, dry_run, detail, message_id, transport}."""
    cfg = cfg or smtp_config()
    to_email = (to_email or "").strip()
    dry = dry_run_enabled() if force_dry_run is None else force_dry_run
    if not to_email or "@" not in to_email:
        return {"ok": False, "dry_run": dry, "detail": "Не указан или некорректен email получателя."}

    try:
        msg = build_message(to_email, subject, body, reply_to, cfg=cfg)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "dry_run": dry, "detail": f"Не удалось собрать письмо: {exc}"}

    kind = transport(cfg)

    if dry:
        return {
            "ok": True,
            "dry_run": True,
            "transport": kind,
            "detail": f"DRY_RUN: письмо для {to_email} собрано, но не отправлено. Выключите DRY_RUN "
                      f"(переменная окружения) — и письма начнут уходить сами.",
            "message_id": msg["Message-ID"],
        }

    if kind == "none":
        return {
            "ok": False,
            "dry_run": False,
            "transport": "none",
            "detail": "Почта не настроена: в «Автопилоте» нажмите «Войти через Google» (пароли приложений "
                      "не нужны) либо укажите SMTP, либо задайте BREVO_API_KEY / RESEND_API_KEY и EMAIL_FROM.",
        }

    if kind == "google":
        google_result = google_oauth.send(
            (cfg or {}).get("google_access", ""), to_email, subject, body,
            reply_to=reply_to,
            sender=(cfg or {}).get("google_sender") or email_from(cfg) or "",
            sender_name=from_name(cfg),
        )
        return google_result

    if kind in HTTP_PROVIDERS:
        return send_via_http(kind, to_email, subject, body, reply_to=reply_to, cfg=cfg)

    try:
        with _connect(cfg) as smtp:
            if cfg.get("user"):
                smtp.login(cfg["user"], cfg.get("password", ""))
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "dry_run": False, "transport": "smtp",
                "detail": "SMTP отклонил логин/пароль. Для Gmail/Яндекс нужен «пароль приложения»."}
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        port = int(cfg.get("port") or 587)
        extra = ""
        if port in BLOCKED_SMTP_PORTS:
            extra = (" Вероятная причина: хостинг блокирует исходящий SMTP (Render Free закрывает 25/465/587). "
                     "Решения: порт 2525 у провайдера либо HTTPS-API — BREVO_API_KEY или RESEND_API_KEY.")
        return {"ok": False, "dry_run": False, "transport": "smtp",
                "detail": f"Ошибка SMTP: {exc.__class__.__name__}: {exc}.{extra}"}

    return {
        "ok": True,
        "dry_run": False,
        "transport": "smtp",
        "detail": f"Письмо отправлено на {to_email}.",
        "message_id": msg["Message-ID"],
    }
