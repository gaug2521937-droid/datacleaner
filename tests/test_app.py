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
