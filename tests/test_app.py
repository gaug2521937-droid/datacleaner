"""Тесты серверной части DataCleaner.

Запуск:
    pip install -r requirements.txt
    pytest -q

Тесты поднимают временную базу (DATACLEANER_DB) и временный ключ (DATA_KEY),
реальный SMTP не используется: DRY_RUN=1.
"""

from __future__ import annotations

import os
import sqlite3
import tempfile
from datetime import date, timedelta
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

TMP_DIR = Path(tempfile.mkdtemp(prefix="datacleaner-test-"))
os.environ["DATACLEANER_DB"] = str(TMP_DIR / "test.db")
os.environ["DATA_KEY"] = Fernet.generate_key().decode()
os.environ["DRY_RUN"] = "1"
os.environ.pop("SMTP_HOST", None)
os.environ.pop("LLM_API_KEY", None)
os.environ.pop("LLM_BASE_URL", None)
os.environ.pop("LLM_MODEL", None)

from fastapi.testclient import TestClient  # noqa: E402

from app import assistant, db, letters, stats  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app)

PROFILE = {
    "full_name": "Иван Иванов",
    "emails": ["ivan@example.com"],
    "phones": ["+7 900 000-00-00"],
    "city": "Петрозаводск",
    "birth_year": "1990",
    "address": "",
    "language": "ru",
}


@pytest.fixture(autouse=True)
def clean_db():
    db.init_db()
    with db.get_conn() as conn:
        db.wipe_all(conn)
    yield


# ------------------------------------------------------------------ базовое
def test_health_shape():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["dry_run"] is True  # DRY_RUN=1 по умолчанию
    assert body["data_key_from_env"] is True


def test_profile_is_encrypted_at_rest():
    r = client.put("/api/profile", json=PROFILE)
    assert r.status_code == 200
    raw = sqlite3.connect(os.environ["DATACLEANER_DB"]).execute("SELECT data_enc FROM profile").fetchone()[0]
    assert isinstance(raw, bytes)
    assert "Иван Иванов".encode("utf-8") not in raw
    assert b"ivan@example.com" not in raw

    back = client.get("/api/profile").json()
    assert back["filled"] is True
    assert back["profile"]["full_name"] == "Иван Иванов"


def test_profile_validation_rejects_bad_year():
    bad = dict(PROFILE, birth_year="19x0")
    assert client.put("/api/profile", json=bad).status_code == 422


# ------------------------------------------------------------------- письма
def test_ru_letter_has_152fz_references():
    letter = letters.build_letter(PROFILE, {"name": "ООО Пример", "language": "ru", "deadline_days": 30})
    assert "статьи 14" in letter["body"]
    assert "статьи 21" in letter["body"]
    assert "30 дней" in letter["body"]
    assert letter["language"] == "ru"


def test_en_letter_has_gdpr_and_ccpa():
    letter = letters.build_letter(PROFILE, {"name": "Spokeo", "language": "en", "deadline_days": 45})
    assert "Article 17 GDPR" in letter["body"]
    assert "CCPA" in letter["body"]
    assert "§1798.105" in letter["body"]
    assert letter["language"] == "en"


def test_empty_fields_are_not_in_the_letter():
    letter = letters.build_letter({"full_name": "", "emails": [], "phones": []}, {"name": "X", "language": "ru"})
    for marker in ("Адрес:", "Город:", "Телефон:", "undefined", "None"):
        assert marker not in letter["body"]


# ---------------------------------------------------------------- брокеры
def test_brokers_catalog_contains_required_services():
    items = client.get("/api/brokers").json()["items"]
    ids = {b["id"] for b in items}
    for required in ("spokeo", "whitepages", "truepeoplesearch", "radaris", "intelius",
                     "google-search", "ru-152-template", "eu-gdpr-template"):
        assert required in ids
    for b in items:
        assert {"id", "name", "category", "method", "language", "notes"} <= set(b)
        assert b["method"] in ("email", "form", "manual")
        assert b["category"] in ("people_search", "data_broker", "marketing", "search", "custom")


def test_custom_broker_add_and_delete():
    payload = {"name": "Мой сервис", "category": "marketing", "method": "email",
               "email": "privacy@example.ru", "language": "ru", "deadline_days": 30}
    r = client.post("/api/brokers", json=payload)
    assert r.status_code == 201
    broker_id = r.json()["broker"]["id"]
    assert any(b["id"] == broker_id for b in client.get("/api/brokers").json()["items"])
    assert client.delete(f"/api/brokers/{broker_id}").status_code == 200
    # сервис из brokers.json удалять нельзя
    assert client.delete("/api/brokers/spokeo").status_code == 400


def test_email_method_requires_address():
    r = client.post("/api/brokers", json={"name": "Без адреса", "method": "email", "language": "ru"})
    assert r.status_code == 422


# --------------------------------------------------------------- запросы
def _create(broker_id="spokeo"):
    client.put("/api/profile", json=PROFILE)
    r = client.post("/api/requests", json={"broker_id": broker_id})
    assert r.status_code == 201
    return r.json()["request"]["id"]


def test_request_lifecycle_sent_responded_deleted():
    rid = _create()
    detail = client.get(f"/api/requests/{rid}").json()
    assert detail["request"]["status"] == "draft"
    assert "Spokeo" in detail["letter"]["body"] or "Spokeo" in detail["letter"]["subject"]
    assert detail["events"][0]["type"] == "created"

    sent = client.post(f"/api/requests/{rid}/send", json={})
    assert sent.status_code == 200
    assert sent.json()["dry_run"] is True  # DRY_RUN=1: письмо не ушло
    assert sent.json()["request"]["status"] == "sent"

    assert client.patch(f"/api/requests/{rid}", json={"status": "responded"}).status_code == 200
    assert client.patch(f"/api/requests/{rid}", json={"status": "deleted"}).status_code == 200
    events = client.get(f"/api/requests/{rid}").json()["events"]
    assert [e["to_status"] for e in events][-1] == "deleted"


def test_illegal_transition_returns_409():
    rid = _create()
    client.post(f"/api/requests/{rid}/send", json={})
    client.patch(f"/api/requests/{rid}", json={"status": "deleted"})
    assert client.patch(f"/api/requests/{rid}", json={"status": "sent"}).status_code == 409


def test_repeat_returns_request_to_draft_and_clears_dates():
    rid = _create()
    client.post(f"/api/requests/{rid}/send", json={})
    r = client.patch(f"/api/requests/{rid}", json={"status": "draft"})
    assert r.status_code == 200
    body = r.json()["request"]
    assert body["status"] == "draft" and body["sent_at"] is None and body["deadline_at"] is None
    types = [e["type"] for e in client.get(f"/api/requests/{rid}").json()["events"]]
    assert "repeat" in types


def test_cannot_send_twice():
    rid = _create()
    client.post(f"/api/requests/{rid}/send", json={})
    assert client.post(f"/api/requests/{rid}/send", json={}).status_code == 409


def test_note_is_stored():
    rid = _create()
    assert client.patch(f"/api/requests/{rid}", json={"note": "номер обращения 42"}).status_code == 200
    assert client.get("/api/requests").json()["items"][0]["note"] == "номер обращения 42"


def test_unknown_broker_404():
    assert client.post("/api/requests", json={"broker_id": "nope"}).status_code == 404


# ------------------------------------------------------------- статистика
def test_stats_are_empty_but_valid():
    body = client.get("/api/stats").json()
    assert body["kpi"]["total"] == 0
    assert body["kpi"]["deletion_rate"] == 0
    assert len(body["activity"]) == 14


def test_stats_counts_after_lifecycle():
    rid = _create()
    client.post(f"/api/requests/{rid}/send", json={})
    client.patch(f"/api/requests/{rid}", json={"status": "responded"})
    client.patch(f"/api/requests/{rid}", json={"status": "deleted"})
    kpi = client.get("/api/stats").json()["kpi"]
    assert kpi["sent"] == 1 and kpi["deleted"] == 1
    assert kpi["deletion_rate"] == 100.0


def test_stats_kpi_has_all_fields_the_ui_expects():
    """Фронтенд читает k.responded, k.drafts и др. — контракт должен совпадать."""
    fields = {"total", "sent", "waiting", "overdue", "deleted", "responded",
              "refused", "drafts", "deletion_rate", "response_rate",
              "avg_response_days", "oldest_overdue_days"}
    for body in (client.get("/api/stats").json(), client.post("/api/stats/demo").json()):
        missing = fields - set(body["kpi"])
        assert not missing, f"в KPI нет полей: {sorted(missing)}"


def test_demo_stats_and_no_read_tracking_note():
    body = client.post("/api/stats/demo").json()
    assert body["demo"] is True
    assert body["kpi"]["total"] == 12
    assert body["kpi"]["responded"] == 2  # в демо два запроса со статусом «Ответили»
    assert "Прочитано" in body["note"] or "прочитано" in body["note"]
    assert body["tips"]


def test_stats_module_overdue_detection():
    today = date(2026, 11, 8)
    rows = [{
        "id": 1, "broker_name": "A", "broker_category": "search", "method": "email",
        "status": "sent", "sent_at": "2026-09-01T10:00:00+00:00",
        "deadline_at": "2026-10-01T10:00:00+00:00", "deadline_days": 30,
    }]
    kpi = stats.compute_stats(rows, today=today)["kpi"]
    assert kpi["overdue"] == 1 and kpi["waiting"] == 0
    assert kpi["oldest_overdue_days"] == 38


# ------------------------------------------------------------ AI-помощник
def test_pii_filter_detects_email_and_phone():
    assert "email" in assistant.detect_pii("пишите на ivan@example.com")
    assert "phone" in assistant.detect_pii("тел +7 900 123-45-67")
    assert assistant.detect_pii("Как сослаться на ст. 21 152-ФЗ?") == []


def test_assistant_blocks_pii_before_any_request():
    r = client.post("/api/assistant", json={"question": "мой телефон +7 900 123-45-67, как удалить?"})
    assert r.status_code == 422
    assert r.json()["blocked"] is True


def test_assistant_returns_hint_when_not_configured():
    r = client.post("/api/assistant", json={"question": "Как удалить данные из Spokeo?"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["configured"] is False
    assert "LLM_API_KEY" in body["hint"]


def test_assistant_status_endpoint():
    body = client.get("/api/assistant/status").json()
    assert body["configured"] is False
    assert body["hint"]


# --------------------------------------------------------- экспорт/очистка
def test_export_contains_profile_and_requests():
    rid = _create()
    body = client.get("/api/export").json()
    assert body["profile"]["full_name"] == "Иван Иванов"
    assert body["requests"][0]["id"] == rid
    assert "конфиденциальный" in body["warning"]


def test_wipe_requires_confirmation_and_deletes_everything():
    _create()
    assert client.post("/api/wipe", json={"confirm": "no"}).status_code == 422
    r = client.post("/api/wipe", json={"confirm": "DELETE"})
    assert r.status_code == 200
    assert client.get("/api/stats").json()["kpi"]["total"] == 0
    assert client.get("/api/profile").json()["profile"] == {}


def test_index_page_is_served():
    r = client.get("/")
    assert r.status_code == 200
    assert "DataCleaner" in r.text
    assert "<script" in r.text


# ------------------------------------------------- настройки: SMTP и автопилот
def test_settings_never_leak_password():
    r = client.put("/api/settings", json={"smtp": {
        "host": "smtp.example.com", "port": 587, "user": "me@example.com",
        "password": "super-secret", "from_addr": "me@example.com",
        "from_name": "DataCleaner", "use_ssl": False, "use_starttls": True,
    }})
    assert r.status_code == 200
    body = r.json()
    assert body["smtp"]["has_password"] is True
    assert "password" not in body["smtp"]
    assert "super-secret" not in r.text
    # пароль лежит в базе только в шифрованном виде
    with db.get_conn() as conn:
        raw = conn.execute("SELECT value FROM kv WHERE key = 'settings.v1'").fetchone()[0]
    assert "super-secret" not in raw


def test_settings_keep_password_when_field_is_empty():
    client.put("/api/settings", json={"smtp": {"host": "smtp.example.com", "from_addr": "me@example.com",
                                               "password": "keep-me"}})
    client.put("/api/settings", json={"smtp": {"host": "smtp.example.com", "from_addr": "me@example.com"}})
    body = client.get("/api/settings").json()
    assert body["smtp"]["has_password"] is True
    assert body["resolved"]["ready"] is True


def test_settings_autopilot_defaults_and_update():
    body = client.get("/api/settings").json()
    assert body["autopilot"]["auto_send"] is False
    assert body["autopilot"]["followup_days"] == 30
    assert body["presets"]  # подсказки для Gmail/Яндекса/…
    updated = client.put("/api/settings", json={"autopilot": {"auto_send": True, "followup_days": 21}}).json()
    assert updated["autopilot"]["auto_send"] is True and updated["autopilot"]["followup_days"] == 21
    # значения из env не подменяются мусором
    assert updated["autopilot"]["interval_minutes"] == 15


def test_smtp_test_endpoint_reports_missing_host():
    client.put("/api/settings", json={"smtp": {"host": "", "user": "", "from_addr": ""}})
    r = client.post("/api/settings/smtp/test", json={})
    assert r.status_code == 200
    assert r.json()["ok"] is False and r.json()["detail"]


def test_knowledge_base_is_available_without_llm():
    body = client.get("/api/knowledge").json()
    assert body["ok"] is True and len(body["facts"]) >= 10
    text = " ".join(f["text"] for f in body["facts"])
    assert "152-ФЗ" in text and "GDPR" in text


def test_models_endpoint_without_config_is_graceful():
    body = client.get("/api/models").json()
    assert body["ok"] is False and body["models"] == []


# ------------------------------------------------------------------ автопилот
def test_autopilot_marks_form_requests_as_manual():
    rid = client.post("/api/requests", json={"broker_id": "spokeo"}).json()["request"]["id"]
    report = client.post("/api/autopilot/run").json()["report"]
    assert [m["id"] for m in report["manual"]] == [rid]
    assert report["sent"] == [] and report["errors"] == []
    assert report["started_at"] and report["finished_at"]


def test_autopilot_sends_drafts_when_forced():
    client.put("/api/profile", json=PROFILE)
    rid = client.post("/api/requests", json={"broker_id": "ru-152-template"}).json()["request"]["id"]
    report = client.post("/api/autopilot/run").json()["report"]
    assert [s["id"] for s in report["sent"]] == [rid]
    row = client.get(f"/api/requests/{rid}").json()["request"]
    assert row["status"] == "sent" and row["sent_at"]


def test_autosend_endpoint_sends_all_drafts():
    client.put("/api/profile", json=PROFILE)
    client.post("/api/requests", json={"broker_id": "ru-152-template"})
    client.post("/api/requests", json={"broker_id": "eu-gdpr-template"})
    body = client.post("/api/requests/autosend").json()
    assert body["ok"] is True and len(body["sent"]) == 2 and body["dry_run"] is True


def test_followup_requires_sent_status():
    rid = client.post("/api/requests", json={"broker_id": "ru-152-template"}).json()["request"]["id"]
    assert client.post(f"/api/requests/{rid}/followup").json()["ok"] is False
    client.post(f"/api/requests/{rid}/send", json={})
    body = client.post(f"/api/requests/{rid}/followup").json()
    assert body["ok"] is True and body["letter"]["kind"] == "followup"
    assert "Повторное" in body["letter"]["subject"]
    types = [e["type"] for e in client.get(f"/api/requests/{rid}").json()["events"]]
    assert "followup" in types


def test_complaint_letter_is_built_locally():
    client.put("/api/profile", json=PROFILE)
    # российский брокер → жалоба в Роскомнадзор
    ru = client.post("/api/requests", json={"broker_id": "ru-152-template"}).json()["request"]["id"]
    client.post(f"/api/requests/{ru}/send", json={})
    ru_letter = client.post(f"/api/requests/{ru}/complaint").json()["letter"]
    assert ru_letter["kind"] == "complaint_rkn" and "Роскомнадзор" in ru_letter["body"]
    assert "13.11" in ru_letter["body"] and "Иван Иванов" in ru_letter["body"]
    # американский сервис → жалоба в надзорный орган по GDPR
    us = client.post("/api/requests", json={"broker_id": "spokeo"}).json()["request"]["id"]
    client.post(f"/api/requests/{us}/send", json={})
    us_letter = client.post(f"/api/requests/{us}/complaint").json()["letter"]
    assert us_letter["kind"] == "complaint_dpa"
    assert "Article 77 GDPR" in us_letter["subject"] and "Article 12(3) GDPR" in us_letter["body"]


def test_assistant_stream_reports_not_configured():
    with client.stream("POST", "/api/assistant/stream", json={"question": "Как удалить данные?", "mode": "advice"}) as r:
        assert r.status_code == 200
        payload = "".join(chunk for chunk in r.iter_text())
    assert "not_configured" in payload


def test_assistant_stream_blocks_pii():
    with client.stream("POST", "/api/assistant/stream",
                       json={"question": "мой телефон +7 900 123-45-67, как удалить?", "mode": "advice"}) as r:
        payload = "".join(chunk for chunk in r.iter_text())
    assert "blocked" in payload and "phone" in payload


def test_health_reports_autopilot_and_version():
    body = client.get("/api/health").json()
    assert body["version"].startswith("1.")
    assert body["autopilot"]["followup_days"] == 30
    assert body["dry_run"] is True


# ------------------------------------------- транспорт почты: HTTPS-API провайдеров
class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def test_mail_transport_detection(monkeypatch):
    from app import mailer

    for name in ("BREVO_API_KEY", "RESEND_API_KEY", "MAIL_PROVIDER", "EMAIL_FROM", "SMTP_FROM"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "me@example.com")
    assert mailer.transport() == "smtp"

    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("EMAIL_FROM", "me@example.com")
    assert mailer.transport() == "brevo"
    assert mailer.mail_ready() is True
    assert mailer.transport_info()["kind"] == "brevo"

    monkeypatch.setenv("MAIL_PROVIDER", "smtp")  # явный выбор важнее автоопределения
    assert mailer.transport() == "smtp"

    monkeypatch.delenv("SMTP_HOST")
    monkeypatch.setenv("MAIL_PROVIDER", "smtp")
    assert mailer.transport() == "none"
    assert mailer.mail_ready() is False
    assert mailer.transport_info()["notes"]  # подсказка, что именно не настроено


def test_brevo_http_send_payload(monkeypatch):
    from app import mailer

    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("EMAIL_FROM", "ivan@example.com")
    monkeypatch.setenv("EMAIL_FROM_NAME", "DataCleaner")
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    captured = {}

    def fake_post(url, payload, headers):
        captured.update({"url": url, "json": payload, "headers": headers})
        return _FakeResponse(201, {"messageId": "<abc@brevo>"})

    monkeypatch.setattr("app.mailer._http_post_json", fake_post)
    result = mailer.send_email("dpo@spokeo.com", "Erasure request", "Text", reply_to="ivan@example.com",
                               force_dry_run=False)
    assert result["ok"] is True and result["transport"] == "brevo"
    assert captured["url"].endswith("/v3/smtp/email")
    assert captured["headers"]["api-key"] == "xkeysib-test"
    assert captured["json"]["sender"]["email"] == "ivan@example.com"
    assert captured["json"]["to"] == [{"email": "dpo@spokeo.com"}]
    assert captured["json"]["textContent"] == "Text"  # только plain-text, без HTML
    assert captured["json"]["replyTo"] == {"email": "ivan@example.com"}


def test_resend_http_send_and_errors(monkeypatch):
    from app import mailer

    monkeypatch.delenv("BREVO_API_KEY", raising=False)
    monkeypatch.setenv("RESEND_API_KEY", "re_test")
    monkeypatch.setenv("EMAIL_FROM", "ivan@example.com")
    seen = {}

    def fake_post(url, payload, headers):
        seen.update({"url": url, "headers": headers, "json": payload})
        return _FakeResponse(200, {"id": "msg-1"})

    monkeypatch.setattr("app.mailer._http_post_json", fake_post)
    ok = mailer.send_email("dpo@example.com", "Subject", "Body", force_dry_run=False)
    assert ok["ok"] is True and ok["message_id"] == "msg-1"
    assert seen["headers"]["Authorization"] == "Bearer re_test"
    assert "text" in seen["json"]

    def unauthorized(url, payload, headers):
        return _FakeResponse(401, {"message": "Key not valid"})

    monkeypatch.setattr("app.mailer._http_post_json", unauthorized)
    bad = mailer.send_email("dpo@example.com", "Subject", "Body", force_dry_run=False)
    assert bad["ok"] is False and "401" in bad["detail"]


def test_dry_run_never_touches_network(monkeypatch):
    from app import mailer

    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-test")
    monkeypatch.setenv("EMAIL_FROM", "ivan@example.com")
    monkeypatch.setenv("DRY_RUN", "1")

    def boom(*args, **kwargs):
        raise AssertionError("в DRY_RUN сеть трогать нельзя")

    monkeypatch.setattr("app.mailer._http_post_json", boom)
    result = mailer.send_email("dpo@example.com", "S", "B")
    assert result["ok"] is True and result["dry_run"] is True


def test_smtp_blocked_port_hint_in_error(monkeypatch):
    from app import mailer

    cfg = {"host": "smtp.gmail.com", "port": 587, "user": "me@example.com", "password": "x",
           "from_addr": "me@example.com", "from_name": "DataCleaner",
           "use_ssl": False, "use_starttls": True}
    for name in ("BREVO_API_KEY", "RESEND_API_KEY", "MAIL_PROVIDER"):
        monkeypatch.delenv(name, raising=False)

    import smtplib

    def refuse(*args, **kwargs):
        raise OSError("Connection refused")

    monkeypatch.setattr(smtplib, "SMTP", refuse)
    result = mailer.send_email("dpo@example.com", "S", "B", force_dry_run=False, cfg=cfg)
    assert result["ok"] is False
    assert "2525" in result["detail"] and "BREVO_API_KEY" in result["detail"]


def test_health_reports_mail_transport(monkeypatch):
    body = client.get("/api/health").json()
    assert body["mail_transport"] in ("smtp", "brevo", "resend", "none")
    assert "mail_ready" in body


def test_settings_expose_transport_without_secrets(monkeypatch):
    monkeypatch.setenv("BREVO_API_KEY", "xkeysib-secret")
    monkeypatch.setenv("EMAIL_FROM", "ivan@example.com")
    body = client.get("/api/settings").json()
    assert body["transport"]["kind"] == "brevo"
    assert body["resolved"]["ready"] is True
    assert "xkeysib-secret" not in str(body)


# --------------------------------------------- вход через Google (OAuth, без паролей приложений)
def _oauth_env(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "1234.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "GOCSPX-test")


def test_google_status_not_configured(monkeypatch):
    for name in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"):
        monkeypatch.delenv(name, raising=False)
    body = client.get("/api/mail/google/status").json()
    assert body["ok"] is True and body["configured"] is False and body["connected"] is False


def test_google_start_returns_auth_url(monkeypatch):
    _oauth_env(monkeypatch)
    body = client.post("/api/mail/google/start").json()
    assert body["ok"] is True
    url = body["auth_url"]
    assert url.startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "gmail.send" in url and "access_type=offline" in url and "state=" in url
    assert "client_secret" not in url  # секрет не должен утечь в браузер


def test_google_callback_stores_encrypted_tokens(monkeypatch):
    from app import db, google_oauth

    _oauth_env(monkeypatch)
    started = client.post("/api/mail/google/start").json()
    state = started["auth_url"].split("state=")[1].split("&")[0]

    def fake_post(url, data):
        assert url == "https://oauth2.googleapis.com/token"
        assert data["grant_type"] == "authorization_code"
        assert data["code"] == "test-code"
        return _FakeResponse(200, {"access_token": "ya29.access", "refresh_token": "1//refresh",
                                   "expires_in": 3599, "scope": "https://www.googleapis.com/auth/gmail.send"})

    def fake_get(url, headers):
        return _FakeResponse(200, {"emailAddress": "ivan@gmail.com"})

    monkeypatch.setattr("app.google_oauth._post_form", fake_post)
    monkeypatch.setattr("app.google_oauth._get", fake_get)

    resp = client.get(f"/api/mail/google/callback?code=test-code&state={state}", follow_redirects=False)
    assert resp.status_code == 303
    assert "mail=google_ok" in resp.headers["location"]

    status = client.get("/api/mail/google/status").json()
    assert status["connected"] is True and status["email"] == "ivan@gmail.com"

    # токены лежат только в зашифрованном виде
    with db.get_conn() as conn:
        raw = conn.execute("SELECT value FROM kv WHERE key = ?", (google_oauth.TOKENS_KEY,)).fetchone()[0]
    assert "1//refresh" not in raw and "ya29.access" not in raw

    # и почта считается подключённой через Google
    settings = client.get("/api/settings").json()
    assert settings["transport"]["kind"] == "google"
    assert settings["resolved"]["ready"] is True


def test_google_callback_rejects_wrong_state(monkeypatch):
    _oauth_env(monkeypatch)
    client.post("/api/mail/google/start")
    resp = client.get("/api/mail/google/callback?code=x&state=broken", follow_redirects=False)
    assert resp.status_code == 303 and "mail=google_failed" in resp.headers["location"]
    assert client.get("/api/mail/google/status").json()["connected"] is False


def test_google_send_uses_gmail_api(monkeypatch):
    from app import google_oauth

    sent = {}

    def fake_post(url, payload, headers):
        sent.update({"url": url, "json": payload, "headers": headers})
        return _FakeResponse(200, {"id": "msg-42"})

    monkeypatch.setattr("app.google_oauth._post_json", fake_post)
    result = google_oauth.send("ya29.token", "dpo@spokeo.com", "Erasure request", "Text body",
                              reply_to="ivan@gmail.com", sender="ivan@gmail.com")
    assert result["ok"] is True and result["message_id"] == "msg-42"
    assert sent["url"].endswith("/gmail/v1/users/me/messages/send")
    assert sent["headers"]["Authorization"] == "Bearer ya29.token"
    import base64
    raw = base64.urlsafe_b64decode(sent["json"]["raw"]).decode()
    assert "Subject: Erasure request" in raw and "To: dpo@spokeo.com" in raw
    assert "text/plain" in raw  # только текст, без HTML и пикселей


def test_mailer_prefers_google_over_smtp():
    from app import mailer
    cfg = {"host": "smtp.gmail.com", "port": 587, "from_addr": "a@b.co", "google_access": "ya29.token"}
    assert mailer.transport(cfg) == "google"
    assert mailer.transport_info(cfg)["label"].startswith("Вход через Google")


def test_google_disconnect(monkeypatch):
    _oauth_env(monkeypatch)
    body = client.post("/api/mail/google/disconnect").json()
    assert body["ok"] is True
    assert client.get("/api/mail/google/status").json()["connected"] is False
