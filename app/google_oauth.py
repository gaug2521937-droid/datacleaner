"""Вход через Google (OAuth 2.0): отправка писем с вашего Gmail без пароля приложения.

Зачем. Gmail не принимает обычный пароль по SMTP (с 2022 года), а «пароль
приложения» — лишний ритуал. Вместо этого пользователь один раз нажимает
«Войти через Google», вводит свой обычный пароль **на странице Google** —
приложение его не видит и не хранит. Google выдаёт refresh-токен, мы храним его
зашифрованным (Fernet, ключ DATA_KEY) и отправляем письма через Gmail API по
HTTPS (порт 443). Это работает и на бесплатном Render, где исходящий SMTP
(25/465/587) заблокирован платформой.

Что нужно один раз настроить (владелец сервиса):
    1. console.cloud.google.com → создать проект;
    2. APIs & Services → Library → включить Gmail API;
    3. OAuth consent screen → External, добавить себя в Test users,
       scopes: https://www.googleapis.com/auth/gmail.send;
    4. Credentials → Create credentials → OAuth client ID → Web application,
       Authorized redirect URI: <ваш домен>/api/mail/google/callback;
    5. в окружение положить GOOGLE_CLIENT_ID и GOOGLE_CLIENT_SECRET.

Пока приложение в режиме Testing, токен живёт 7 дней — затем достаточно снова
нажать «Войти через Google». Публикация приложения снимает это ограничение
(Google проверяет приложение, использующее scope gmail.send).
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import sqlite3
import time
from email.message import EmailMessage
from typing import Any
from urllib.parse import urlencode

import httpx

from . import db
from .crypto import Vault

TOKENS_KEY = "mail.google.tokens.v1"
STATE_KEY = "mail.google.state.v1"
SCOPE = "https://www.googleapis.com/auth/gmail.send"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
PROFILE_URL = "https://gmail.googleapis.com/gmail/v1/users/me/profile"


# --------------------------------------------------------------- сеть (тонкий слой)
def _post_form(url: str, data: dict[str, str]) -> httpx.Response:
    with httpx.Client(timeout=25) as client:
        return client.post(url, data=data)


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> httpx.Response:
    with httpx.Client(timeout=30) as client:
        return client.post(url, json=payload, headers=headers)


def _get(url: str, headers: dict[str, str]) -> httpx.Response:
    with httpx.Client(timeout=20) as client:
        return client.get(url, headers=headers)


# ------------------------------------------------------------------- настройка
def client_id() -> str:
    return (os.getenv("GOOGLE_CLIENT_ID") or "").strip()


def client_secret() -> str:
    return (os.getenv("GOOGLE_CLIENT_SECRET") or "").strip()


def configured() -> bool:
    """Заданы ли ключи OAuth-приложения (иначе кнопка входа не показывается)."""
    return bool(client_id() and client_secret())


def redirect_uri(base_url: str) -> str:
    """Адрес возврата: PUBLIC_BASE_URL (если задан) иначе адрес запроса."""
    explicit = (os.getenv("PUBLIC_BASE_URL") or "").strip()
    if explicit:
        return explicit.rstrip("/") + "/api/mail/google/callback"
    return base_url.rstrip("/") + "/api/mail/google/callback"


# --------------------------------------------------------------------- токены
def _encrypt(vault: Vault, data: dict[str, Any]) -> str:
    return base64.b64encode(vault._fernet.encrypt(  # noqa: SLF001 — свой модуль, ключ тот же
        json.dumps(data, ensure_ascii=False).encode("utf-8"))).decode()


def _decrypt(vault: Vault, blob: str) -> dict[str, Any]:
    return json.loads(vault._fernet.decrypt(base64.b64decode(blob.encode())).decode("utf-8"))  # noqa: SLF001


def load_tokens(conn: sqlite3.Connection, vault: Vault) -> dict[str, Any]:
    blob = db.kv_get(conn, TOKENS_KEY)
    if not blob:
        return {}
    try:
        return _decrypt(vault, blob)
    except Exception:  # noqa: BLE001 — повреждённый токен не должен ломать приложение
        return {}


def save_tokens(conn: sqlite3.Connection, vault: Vault, tokens: dict[str, Any]) -> None:
    db.kv_set(conn, TOKENS_KEY, _encrypt(vault, tokens))


def clear_tokens(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM kv WHERE key = ?", (TOKENS_KEY,))


def connected_email(conn: sqlite3.Connection, vault: Vault) -> str | None:
    return load_tokens(conn, vault).get("email")


def status(conn: sqlite3.Connection, vault: Vault, base_url: str = "https://example.com") -> dict[str, Any]:
    tokens = load_tokens(conn, vault)
    return {
        "configured": configured(),
        "connected": bool(tokens.get("refresh_token") or tokens.get("access_token")),
        "email": tokens.get("email"),
        "connected_at": tokens.get("connected_at"),
        "redirect_uri": redirect_uri(base_url),
        "client_id_hint": (client_id()[:12] + "…") if client_id() else "",
        "mode": "testing" if configured() else "off",
        "docs": "https://console.cloud.google.com/apis/credentials",
    }


# ---------------------------------------------------------------------- OAuth
def start(conn: sqlite3.Connection, base_url: str) -> dict[str, Any]:
    """Готовит ссылку «Войти через Google» и сохраняет state для проверки."""
    if not configured():
        return {"ok": False, "detail": "GOOGLE_CLIENT_ID и GOOGLE_CLIENT_SECRET не заданы на сервере."}
    state = secrets.token_urlsafe(24)
    db.kv_set(conn, STATE_KEY, state)
    params = {
        "client_id": client_id(),
        "redirect_uri": redirect_uri(base_url),
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",     # нужен refresh_token
        "prompt": "consent",          # гарантированно выдаёт refresh_token
        "include_granted_scopes": "true",
        "state": state,
    }
    return {"ok": True, "auth_url": AUTH_URL + "?" + urlencode(params), "redirect_uri": redirect_uri(base_url)}


def exchange_code(conn: sqlite3.Connection, vault: Vault, code: str, state: str,
                  base_url: str) -> dict[str, Any]:
    """Меняет код на токены и сохраняет их зашифрованными."""
    expected = db.kv_get(conn, STATE_KEY)
    if not expected or state != expected:
        return {"ok": False, "detail": "Проверка state не пройдена — начните вход заново."}
    data = {
        "code": code,
        "client_id": client_id(),
        "client_secret": client_secret(),
        "redirect_uri": redirect_uri(base_url),
        "grant_type": "authorization_code",
    }
    try:
        resp = _post_form(TOKEN_URL, data)
    except httpx.HTTPError as exc:
        return {"ok": False, "detail": f"Сеть: {exc.__class__.__name__}"}
    if resp.status_code >= 400:
        message = ""
        try:
            message = resp.json().get("error_description") or resp.json().get("error") or ""
        except Exception:  # noqa: BLE001
            pass
        return {"ok": False, "detail": f"Google отклонил вход ({resp.status_code}). {message}"}
    payload = resp.json()
    tokens = {
        "access_token": payload.get("access_token", ""),
        "refresh_token": payload.get("refresh_token", ""),
        "expires_at": int(time.time()) + int(payload.get("expires_in") or 3500),
        "scope": payload.get("scope", SCOPE),
        "connected_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    access = tokens["access_token"]
    try:
        prof = _get(PROFILE_URL, {"Authorization": f"Bearer {access}"})
        if prof.status_code == 200:
            tokens["email"] = prof.json().get("emailAddress", "")
    except httpx.HTTPError:
        pass
    save_tokens(conn, vault, tokens)
    db.kv_set(conn, STATE_KEY, "")
    return {"ok": True, "email": tokens.get("email") or "", "detail": "Google подключён: письма уходят с вашего ящика."}


def _refresh(conn: sqlite3.Connection, vault: Vault, tokens: dict[str, Any]) -> dict[str, Any] | None:
    refresh_token = tokens.get("refresh_token") or (os.getenv("GOOGLE_REFRESH_TOKEN") or "").strip()
    if not refresh_token or not configured():
        return None
    data = {
        "client_id": client_id(),
        "client_secret": client_secret(),
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    try:
        resp = _post_form(TOKEN_URL, data)
    except httpx.HTTPError:
        return None
    if resp.status_code >= 400:
        return None
    payload = resp.json()
    tokens = {
        **tokens,
        "access_token": payload.get("access_token", ""),
        "expires_at": int(time.time()) + int(payload.get("expires_in") or 3500),
        "refresh_token": refresh_token,
    }
    if tokens.get("email"):
        save_tokens(conn, vault, tokens)
    return tokens


def access_token(conn: sqlite3.Connection | None, vault: Vault | None) -> str:
    """Действующий access token (обновляет по refresh_token при необходимости)."""
    env_token = (os.getenv("GOOGLE_ACCESS_TOKEN") or "").strip()
    tokens: dict[str, Any] = {}
    if conn is not None and vault is not None:
        tokens = load_tokens(conn, vault)
    token = tokens.get("access_token") or env_token
    expires_at = int(tokens.get("expires_at") or 0)
    if token and (not expires_at or expires_at - 60 > time.time()):
        return token
    if conn is not None and vault is not None:
        refreshed = _refresh(conn, vault, tokens)
        if refreshed and refreshed.get("access_token"):
            return refreshed["access_token"]
    return env_token if not expires_at else ""


# ------------------------------------------------------------------- отправка
def send(access: str, to_email: str, subject: str, body: str,
         reply_to: str | None = None, sender: str = "me", sender_name: str = "DataCleaner") -> dict[str, Any]:
    """Отправляет письмо через Gmail API. Только text/plain, без трекинга."""
    if not access:
        return {"ok": False, "dry_run": False, "transport": "google",
                "detail": "Google не подключён: нажмите «Войти через Google» в разделе «Автопилот»."}
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{sender_name} <{sender}>" if sender and "@" in sender else sender_name
    msg["To"] = to_email
    if reply_to:
        msg["Reply-To"] = reply_to
    msg["Auto-Submitted"] = "auto-generated"
    msg.set_content(body, subtype="plain", charset="utf-8")
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    try:
        resp = _post_json(SEND_URL, {"raw": raw}, {"Authorization": f"Bearer {access}"})
    except httpx.HTTPError as exc:
        return {"ok": False, "dry_run": False, "transport": "google",
                "detail": f"Google: сеть недоступна ({exc.__class__.__name__})."}
    if resp.status_code >= 400:
        message = ""
        try:
            message = (resp.json().get("error") or {}).get("message", "")
        except Exception:  # noqa: BLE001
            pass
        hint = ""
        if resp.status_code == 401:
            hint = " Токен истёк — нажмите «Войти через Google» заново."
        if resp.status_code == 403:
            hint = (" Проверьте, что Gmail API включён и ваш адрес добавлен в Test users "
                    "OAuth consent screen, а scope gmail.send разрешён.")
        return {"ok": False, "dry_run": False, "transport": "google",
                "detail": f"Google API: ошибка {resp.status_code}. {message}{hint}"}
    try:
        msg_id = resp.json().get("id", "")
    except Exception:  # noqa: BLE001
        msg_id = ""
    return {"ok": True, "dry_run": False, "transport": "google",
            "detail": f"Письмо отправлено на {to_email} через Gmail API.", "message_id": msg_id}


def verify(conn: sqlite3.Connection, vault: Vault, probe_to: str | None = None) -> dict[str, Any]:
    """Проверка подключения: профиль Gmail (+ тестовое письмо, если просят)."""
    access = access_token(conn, vault)
    if not access:
        return {"ok": False, "transport": "google",
                "detail": "Google не подключён: нажмите «Войти через Google»."}
    try:
        resp = _get(PROFILE_URL, {"Authorization": f"Bearer {access}"})
    except httpx.HTTPError as exc:
        return {"ok": False, "transport": "google", "detail": f"Сеть: {exc.__class__.__name__}"}
    if resp.status_code >= 400:
        return {"ok": False, "transport": "google",
                "detail": f"Google вернул {resp.status_code}. Возможно, Gmail API не включён в проекте."}
    email = ""
    try:
        email = resp.json().get("emailAddress", "")
    except Exception:  # noqa: BLE001
        pass
    if probe_to:
        result = send(access, probe_to, "DataCleaner: проверка отправки",
                      "Это тестовое письмо через Gmail API. Если вы его видите — всё настроено верно, "
                      "и требования об удалении данных будут уходить сами.",
                      sender=email or "me")
        return {**result, "detail": ("Подключено как " + email + ". " + result["detail"]) if result["ok"] else result["detail"]}
    return {"ok": True, "transport": "google",
            "detail": f"Google подключён: {email or 'аккаунт'} — письма будут уходить с вашего ящика."}
