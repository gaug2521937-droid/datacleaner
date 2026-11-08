"""Отправка писем через SMTP.

DRY_RUN=1 по умолчанию: письма НЕ уходят, но полностью проходят через тот же
код (шифрование, сборка MIME, проверка получателя). Так можно тестировать
воронку без риска отправить что-то лишнее.

Письма — только text/plain. Никаких HTML, пикселей, внешних картинок и
заголовков вида X-Tracking: получатель — не объект слежки.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Any


def smtp_config() -> dict[str, Any]:
    return {
        "host": os.getenv("SMTP_HOST", "").strip(),
        "port": int(os.getenv("SMTP_PORT", "587") or 587),
        "user": os.getenv("SMTP_USER", "").strip(),
        "password": os.getenv("SMTP_PASS", ""),
        "from_addr": (os.getenv("SMTP_FROM") or os.getenv("SMTP_ FROM") or os.getenv("SMTP_USER") or "").strip(),
        "from_name": os.getenv("SMTP_FROM_NAME", "DataCleaner").strip(),
        "use_ssl": os.getenv("SMTP_SSL", "0") in ("1", "true", "True"),
        "use_starttls": os.getenv("SMTP_STARTTLS", "1") in ("1", "true", "True"),
    }


def is_smtp_configured() -> bool:
    cfg = smtp_config()
    return bool(cfg["host"] and cfg["from_addr"])


def dry_run_enabled() -> bool:
    return os.getenv("DRY_RUN", "1") not in ("0", "false", "False", "no")


def build_message(to_email: str, subject: str, body: str, reply_to: str | None = None) -> EmailMessage:
    cfg = smtp_config()
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((cfg["from_name"], cfg["from_addr"] or "noreply@localhost"))
    msg["To"] = to_email
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Message-ID"] = make_msgid(domain=(cfg["from_addr"].split("@")[-1] if "@" in cfg["from_addr"] else "datacleaner.local"))
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(body, subtype="plain", charset="utf-8")
    return msg


def send_email(
    to_email: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
    force_dry_run: bool | None = None,
) -> dict[str, Any]:
    """Возвращает {ok, dry_run, detail, message_id}."""
    to_email = (to_email or "").strip()
    if not to_email or "@" not in to_email:
        return {"ok": False, "dry_run": dry_run_enabled(), "detail": "Не указан или некорректен email получателя."}

    dry = dry_run_enabled() if force_dry_run is None else force_dry_run
    cfg = smtp_config()

    try:
        msg = build_message(to_email, subject, body, reply_to)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "dry_run": dry, "detail": f"Не удалось собрать письмо: {exc}"}

    if dry:
        return {
            "ok": True,
            "dry_run": True,
            "detail": f"DRY_RUN=1: письмо для {to_email} собрано, но не отправлено. "
                      f"Размер: {len(body)} символов. Для реальной отправки задайте DRY_RUN=0 "
                      f"и настройки SMTP.",
            "message_id": msg["Message-ID"],
        }

    if not is_smtp_configured():
        return {
            "ok": False,
            "dry_run": False,
            "detail": "SMTP не настроен: задайте SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM.",
        }

    try:
        if cfg["use_ssl"]:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=25, context=context) as smtp:
                _login_and_send(smtp, cfg, msg)
        else:
            with smtplib.SMTP(cfg["host"], cfg["port"], timeout=25) as smtp:
                if cfg["use_starttls"]:
                    smtp.starttls(context=ssl.create_default_context())
                _login_and_send(smtp, cfg, msg)
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "dry_run": False,
                "detail": "SMTP отклонил логин/пароль. Для Gmail/Яндекс нужен «пароль приложения», а не пароль аккаунта."}
    except (smtplib.SMTPException, OSError) as exc:
        return {"ok": False, "dry_run": False, "detail": f"Ошибка SMTP: {exc.__class__.__name__}: {exc}"}

    return {
        "ok": True,
        "dry_run": False,
        "detail": f"Письмо отправлено на {to_email}.",
        "message_id": msg["Message-ID"],
    }


def _login_and_send(smtp: smtplib.SMTP, cfg: dict[str, Any], msg: EmailMessage) -> None:
    if cfg["user"]:
        smtp.login(cfg["user"], cfg["password"])
    smtp.send_message(msg)
