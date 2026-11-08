"""Настройки приложения, которые можно менять из интерфейса.

Хранятся в таблице kv (значение — Fernet-шифротекст в base64), чтобы пароль SMTP
не лежал в открытом виде ни в базе, ни в логи.

Приоритет источников:
1. значения из интерфейса (база);
2. переменные окружения (.env / Render Environment).
Так пользователь может либо вписать SMTP в приложении за минуту, либо
пробросить секреты через окружение хостинга.
"""

from __future__ import annotations

import base64
import os
import sqlite3
from typing import Any

from .crypto import Vault

KV_KEY = "settings.v1"

DEFAULT_AUTOPILOT = {
    "auto_send": False,          # отправлять новые черновики сами
    "followup_enabled": False,   # автоматические напоминания просроченным
    "followup_days": 30,         # через сколько дней после отправки напоминать
    "interval_minutes": 15,      # как часто работает автопилот
}

DEFAULT_SMTP = {
    "host": "",
    "port": 587,
    "user": "",
    "password": "",
    "from_addr": "",
    "from_name": "DataCleaner",
    "use_ssl": False,
    "use_starttls": True,
}

SMTP_PRESETS = [
    {"id": "gmail", "label": "Gmail", "host": "smtp.gmail.com", "port": 587, "ssl": False, "starttls": True,
     "hint": "Нужен «пароль приложения» (Google Account → Security → App passwords), обычный пароль не подойдёт."},
    {"id": "yandex", "label": "Яндекс.Почта", "host": "smtp.yandex.ru", "port": 465, "ssl": True, "starttls": False,
     "hint": "Включите «Пароли приложений» в настройках почты и используйте его вместо пароля аккаунта."},
    {"id": "mailru", "label": "Mail.ru", "host": "smtp.mail.ru", "port": 465, "ssl": True, "starttls": False,
     "hint": "Нужен пароль для внешнего приложения из настроек почты."},
    {"id": "outlook", "label": "Outlook / Hotmail", "host": "smtp-mail.outlook.com", "port": 587, "ssl": False, "starttls": True,
     "hint": "Сначала включите двухфакторную аутентификацию и создайте пароль приложения."},
    {"id": "custom", "label": "Другой сервер", "host": "", "port": 587, "ssl": False, "starttls": True,
     "hint": "Адрес, порт и способ шифрования — из справки вашего почтового провайдера."},
]


def _defaults() -> dict[str, Any]:
    return {"smtp": dict(DEFAULT_SMTP), "autopilot": dict(DEFAULT_AUTOPILOT)}


def load(conn: sqlite3.Connection, vault: Vault) -> dict[str, Any]:
    """Возвращает настройки: база поверх значений по умолчанию."""
    data = _defaults()
    row = conn.execute("SELECT value FROM kv WHERE key = ?", (KV_KEY,)).fetchone()
    if row and row[0]:
        try:
            raw = vault._fernet.decrypt(base64.b64decode(row[0].encode())).decode("utf-8")  # noqa: SLF001
            import json

            stored = json.loads(raw)
            data["smtp"].update({k: v for k, v in (stored.get("smtp") or {}).items() if k in DEFAULT_SMTP})
            data["autopilot"].update({k: v for k, v in (stored.get("autopilot") or {}).items() if k in DEFAULT_AUTOPILOT})
        except Exception:  # noqa: BLE001 — повреждённые настройки не должны ломать приложение
            pass
    return data


def save(conn: sqlite3.Connection, vault: Vault, data: dict[str, Any]) -> dict[str, Any]:
    current = load(conn, vault)
    current["smtp"].update({k: v for k, v in (data.get("smtp") or {}).items() if k in DEFAULT_SMTP})
    current["autopilot"].update({k: v for k, v in (data.get("autopilot") or {}).items() if k in DEFAULT_AUTOPILOT})
    import json

    blob = vault._fernet.encrypt(json.dumps(current, ensure_ascii=False).encode("utf-8"))  # noqa: SLF001
    value = base64.b64encode(blob).decode()
    conn.execute(
        "INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (KV_KEY, value),
    )
    return current


def effective_smtp(conn: sqlite3.Connection, vault: Vault) -> dict[str, Any]:
    """SMTP: настройки из интерфейса, а если поле пустое — переменная окружения."""
    cfg = dict(load(conn, vault)["smtp"])
    env_map = {
        "host": "SMTP_HOST", "user": "SMTP_USER", "password": "SMTP_PASS",
        "from_addr": "SMTP_FROM", "from_name": "SMTP_FROM_NAME",
    }
    for field, env_name in env_map.items():
        if not cfg.get(field):
            cfg[field] = os.getenv(env_name, "").strip()
    if not cfg.get("from_addr"):
        cfg["from_addr"] = cfg.get("user", "")
    if not os.getenv("SMTP_PORT") and not cfg.get("port"):
        cfg["port"] = DEFAULT_SMTP["port"]
    elif os.getenv("SMTP_PORT") and cfg.get("port") in (None, "", DEFAULT_SMTP["port"]):
        try:
            cfg["port"] = int(os.getenv("SMTP_PORT", "587"))
        except ValueError:
            cfg["port"] = 587
    if os.getenv("SMTP_SSL") in ("1", "true", "True"):
        cfg["use_ssl"], cfg["use_starttls"] = True, False
    if os.getenv("SMTP_STARTTLS") in ("0", "false", "False"):
        cfg["use_starttls"] = False
    try:
        cfg["port"] = int(cfg.get("port") or 587)
    except (TypeError, ValueError):
        cfg["port"] = 587
    return cfg


def smtp_ready(cfg: dict[str, Any]) -> bool:
    return bool(cfg.get("host") and cfg.get("from_addr"))


def public_view(settings: dict[str, Any], smtp_effective: dict[str, Any], dry_run: bool,
                transport: dict[str, Any] | None = None) -> dict[str, Any]:
    """То, что можно отдавать в браузер: без пароля.

    transport — сводка из mailer.transport_info(): какой транспорт реально будет
    использован (smtp / brevo / resend / none) и почему. Без секретов.
    """
    smtp = dict(settings["smtp"])
    smtp["has_password"] = bool(smtp.pop("password", ""))
    return {
        "smtp": smtp,
        "autopilot": settings["autopilot"],
        "resolved": {
            "host": smtp_effective.get("host", ""),
            "port": smtp_effective.get("port", 587),
            "from_addr": smtp_effective.get("from_addr", ""),
            "user": smtp_effective.get("user", ""),
            "ready": bool((transport or {}).get("kind", "none") != "none"),
            "smtp_ready": smtp_ready(smtp_effective),
            "use_ssl": bool(smtp_effective.get("use_ssl")),
        },
        "dry_run": dry_run,
        "presets": SMTP_PRESETS,
        "transport": transport or {"kind": "none", "label": "не настроено", "notes": []},
    }
