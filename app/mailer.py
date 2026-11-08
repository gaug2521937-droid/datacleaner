"""Отправка писем через SMTP.

Настройки берутся из интерфейса (таблица kv, пароль зашифрован) или из
переменных окружения. DRY_RUN=1 по умолчанию: письмо собирается полностью,
но не отправляется — так можно проверить воронку без риска.

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
    """Настройки из окружения (используется как запасной источник)."""
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


def is_smtp_configured(cfg: dict[str, Any] | None = None) -> bool:
    cfg = cfg or smtp_config()
    return bool(cfg.get("host") and (cfg.get("from_addr") or cfg.get("user")))


def dry_run_enabled() -> bool:
    return os.getenv("DRY_RUN", "1") not in ("0", "false", "False", "no")


def build_message(to_email: str, subject: str, body: str, reply_to: str | None = None,
                  cfg: dict[str, Any] | None = None) -> EmailMessage:
    cfg = cfg or smtp_config()
    from_addr = cfg.get("from_addr") or cfg.get("user") or "noreply@localhost"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((cfg.get("from_name") or "DataCleaner", from_addr))
    msg["To"] = to_email
    if reply_to:
        msg["Reply-To"] = reply_to
    domain = from_addr.split("@")[-1] if "@" in from_addr else "datacleaner.local"
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


def verify_smtp(cfg: dict[str, Any], probe_to: str | None = None) -> dict[str, Any]:
    """Проверка соединения и логина без отправки письма (EHLO + NOOP).

    Если передан probe_to — отправит одно короткое тестовое письмо на этот адрес.
    """
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
                                    "Это тестовое письмо. Если вы его видите — SMTP настроен верно, "
                                    "и запросы на удаление данных будут уходить автоматически.", cfg=cfg)
                smtp.send_message(msg)
                return {"ok": True, "detail": f"Соединение и логин в порядке. Тестовое письмо отправлено на {probe_to}."}
            return {"ok": True, "detail": "Соединение и логин в порядке. Письма можно отправлять."}
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "detail": "Сервер отклонил логин или пароль. Для Gmail/Яндекс/Mail.ru нужен "
                                       "«пароль приложения», а не пароль от почты."}
    except smtplib.SMTPException as exc:
        return {"ok": False, "detail": f"SMTP-ошибка: {exc.__class__.__name__}: {exc}"}
    except (OSError, ssl.SSLError) as exc:
        return {"ok": False, "detail": f"Не удалось подключиться к {cfg.get('host')}:{cfg.get('port')} "
                                       f"({exc.__class__.__name__}). Проверьте порт и шифрование "
                                       f"(465 = SSL, 587 = STARTTLS)."}


def send_email(
    to_email: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
    force_dry_run: bool | None = None,
    cfg: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Возвращает {ok, dry_run, detail, message_id}."""
    cfg = cfg or smtp_config()
    to_email = (to_email or "").strip()
    if not to_email or "@" not in to_email:
        return {"ok": False, "dry_run": dry_run_enabled(), "detail": "Не указан или некорректен email получателя."}

    dry = dry_run_enabled() if force_dry_run is None else force_dry_run

    try:
        msg = build_message(to_email, subject, body, reply_to, cfg=cfg)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "dry_run": dry, "detail": f"Не удалось собрать письмо: {exc}"}

    if dry:
        return {
            "ok": True,
            "dry_run": True,
            "detail": f"DRY_RUN: письмо для {to_email} собрано, но не отправлено. Выключите DRY_RUN "
                      f"и настройте SMTP, чтобы отправлять автоматически.",
            "message_id": msg["Message-ID"],
        }

    if not is_smtp_configured(cfg):
        return {
            "ok": False,
            "dry_run": False,
            "detail": "SMTP не настроен: откройте «Автопилот → Почта» и укажите сервер, логин и пароль приложения.",
        }

    try:
        with _connect(cfg) as smtp:
            if cfg.get("user"):
                smtp.login(cfg["user"], cfg.get("password", ""))
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError:
        return {"ok": False, "dry_run": False,
                "detail": "SMTP отклонил логин/пароль. Для Gmail/Яндекс нужен «пароль приложения»."}
    except (smtplib.SMTPException, OSError, ssl.SSLError) as exc:
        return {"ok": False, "dry_run": False, "detail": f"Ошибка SMTP: {exc.__class__.__name__}: {exc}"}

    return {
        "ok": True,
        "dry_run": False,
        "detail": f"Письмо отправлено на {to_email}.",
        "message_id": msg["Message-ID"],
    }
