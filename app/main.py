"""DataCleaner — серверная версия (FastAPI + SQLite + Fernet).

Запуск:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

Переменные окружения — см. .env.example. Ключей в коде нет.
"""

from __future__ import annotations

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import assistant, db, letters, mailer, stats as stats_mod
from .crypto import Vault, VaultError
from .schemas import BrokerIn, ChatIn, ProfileIn, RequestCreate, RequestPatch, SendIn

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
BROKERS_FILE = BASE_DIR / "brokers.json"

# .env в корне проекта (необязательно: переменные можно задать и в окружении)
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR.parent / ".env")
except ImportError:  # python-dotenv не установлен — работаем на чистом окружении
    pass

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("datacleaner")

DEMO_DENY = "Демо-статистика не сохраняется в базу: это витрина для проверки интерфейса."


# --------------------------------------------------------------------- lifespans
@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    try:
        vault = Vault()
        if vault.used_dev_key:
            log.warning(
                "DATA_KEY не задан — используется локальный файл .datacleaner.key. "
                "Для сервера обязательно задайте DATA_KEY в переменных окружения."
            )
    except VaultError as exc:
        log.error("Проблема с DATA_KEY: %s", exc)
    log.info("DRY_RUN=%s, LLM configured=%s, SMTP configured=%s",
             mailer.dry_run_enabled(), assistant.is_configured(), mailer.is_smtp_configured())
    yield


app = FastAPI(
    title="DataCleaner API",
    version="1.0.0",
    description="Удаление персональных данных из интернета: 152-ФЗ, GDPR, CCPA.",
    lifespan=lifespan,
)

# Схема создаётся при импорте: приложение остаётся рабочим даже если lifespan
# не выполняется (например, в тестах через TestClient без контекст-менеджера).
db.init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Код доступа. Если ACCESS_TOKEN задан, все /api/* (кроме /api/health) требуют заголовок
# X-Access-Token или ?access_token=. Это защита для публичного деплоя: без неё любой,
# кто узнал адрес, мог бы жечь ваш SMTP и баланс LLM.
ACCESS_TOKEN = (os.getenv("ACCESS_TOKEN") or "").strip()


@app.middleware("http")
async def access_guard(request: Request, call_next):
    if ACCESS_TOKEN and request.url.path.startswith("/api") and request.url.path != "/api/health":
        token = request.headers.get("X-Access-Token") or request.query_params.get("access_token") or ""
        if token != ACCESS_TOKEN:
            return JSONResponse(
                status_code=401,
                content={"detail": "Требуется код доступа", "auth_required": True},
            )
    return await call_next(request)


# ------------------------------------------------------------------- dependencies
def get_db():
    with db.get_conn() as conn:
        yield conn


def get_vault() -> Vault:
    try:
        return Vault()
    except VaultError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------- brokers
def load_base_brokers() -> list[dict[str, Any]]:
    try:
        with BROKERS_FILE.open(encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            raise ValueError("brokers.json должен содержать массив")
        for b in data:
            b.setdefault("deadline_days", 30)
            b.setdefault("verify", True)
            b.setdefault("custom", False)
        return data
    except Exception as exc:  # noqa: BLE001
        log.error("Не удалось прочитать brokers.json: %s", exc)
        return []


def all_brokers(conn) -> list[dict[str, Any]]:
    base = load_base_brokers()
    custom = []
    for row in db.list_custom_brokers(conn):
        row = dict(row)
        row["custom"] = True
        row["verify"] = False
        custom.append(row)
    return base + custom


def find_broker(conn, broker_id: str) -> dict[str, Any]:
    for b in all_brokers(conn):
        if b.get("id") == broker_id:
            return b
    raise HTTPException(status_code=404, detail=f"Сервис {broker_id} не найден")


# ---------------------------------------------------------------------- helpers
def profile_from_blob(vault: Vault, blob: bytes | None) -> dict[str, Any]:
    if not blob:
        return {}
    try:
        return vault.decrypt_json(blob) or {}
    except VaultError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def profile_filled(profile: dict[str, Any]) -> bool:
    return bool(profile.get("full_name") and profile.get("emails"))


def request_public(row: dict[str, Any]) -> dict[str, Any]:
    """Метаданные запроса без ПД (расшифровка не нужна)."""
    return {
        "id": row["id"],
        "broker_id": row["broker_id"],
        "broker_name": row["broker_name"],
        "broker_category": row["broker_category"],
        "language": row["language"],
        "method": row["method"],
        "to_email": row["to_email"],
        "status": row["status"],
        "status_label": db.STATUS_LABELS.get(row["status"], row["status"]),
        "deadline_days": row["deadline_days"],
        "created_at": row["created_at"],
        "sent_at": row["sent_at"],
        "responded_at": row["responded_at"],
        "deleted_at": row["deleted_at"],
        "deadline_at": row["deadline_at"],
        "last_action_at": row["last_action_at"],
        "note": row["note"],
        "error": row["error"],
    }


ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"sent"},
    "sent": {"responded", "deleted", "refused", "draft"},
    "responded": {"deleted", "refused", "draft"},
    "refused": {"deleted", "draft"},
    "deleted": {"draft"},
}


# ------------------------------------------------------------------------- API
@app.get("/api/health")
def health(conn=Depends(get_db)) -> dict[str, Any]:
    blob, _ = db.load_profile_blob(conn)
    return {
        "ok": True,
        "dry_run": mailer.dry_run_enabled(),
        "smtp_configured": mailer.is_smtp_configured(),
        "llm_configured": assistant.is_configured(),
        "profile_saved": blob is not None,
        "data_key_from_env": bool(os.getenv("DATA_KEY")),
        "requests": len(db.list_requests(conn)),
        "auth_required": bool(ACCESS_TOKEN),
        "today": date.today().isoformat(),
    }


# --- профиль ---------------------------------------------------------------
@app.get("/api/profile")
def read_profile(conn=Depends(get_db), vault: Vault = Depends(get_vault)) -> dict[str, Any]:
    blob, updated = db.load_profile_blob(conn)
    profile = profile_from_blob(vault, blob)
    return {"profile": profile, "updated_at": updated, "filled": profile_filled(profile)}


@app.put("/api/profile")
def write_profile(payload: ProfileIn, conn=Depends(get_db), vault: Vault = Depends(get_vault)) -> dict[str, Any]:
    data = payload.model_dump()
    db.save_profile(conn, vault.encrypt_json(data))
    return {"ok": True, "detail": "Профиль сохранён в зашифрованном виде (Fernet).", "filled": profile_filled(data)}


@app.delete("/api/profile")
def drop_profile(conn=Depends(get_db)) -> dict[str, Any]:
    conn.execute("DELETE FROM profile WHERE id = 1")
    return {"ok": True, "detail": "Профиль удалён."}


# --- брокеры ---------------------------------------------------------------
@app.get("/api/brokers")
def list_brokers(conn=Depends(get_db)) -> dict[str, Any]:
    items = all_brokers(conn)
    return {"items": items, "count": len(items)}


@app.post("/api/brokers", status_code=201)
def add_broker(payload: BrokerIn, conn=Depends(get_db)) -> dict[str, Any]:
    broker_id = payload.id.strip() or ("custom-" + str(int(datetime.now().timestamp())))
    if any(b.get("id") == broker_id for b in all_brokers(conn)):
        raise HTTPException(status_code=409, detail=f"Сервис с id={broker_id} уже есть")
    if payload.method == "email" and not payload.email:
        raise HTTPException(status_code=422, detail="Для способа «email» нужен адрес email")
    if payload.method == "form" and not payload.url:
        raise HTTPException(status_code=422, detail="Для способа «form» нужен URL формы")
    data = payload.model_dump()
    data["id"] = broker_id
    db.add_custom_broker(conn, data)
    return {"ok": True, "broker": {**data, "custom": True}}


@app.delete("/api/brokers/{broker_id}")
def remove_broker(broker_id: str, conn=Depends(get_db)) -> dict[str, Any]:
    if not db.delete_custom_broker(conn, broker_id):
        raise HTTPException(
            status_code=400,
            detail="Удалять можно только добавленные вами сервисы: файл brokers.json — часть поставки.",
        )
    return {"ok": True, "detail": "Сервис удалён."}


# --- запросы ---------------------------------------------------------------
@app.get("/api/requests")
def list_requests(status_filter: str | None = None, conn=Depends(get_db)) -> dict[str, Any]:
    rows = db.list_requests(conn, status_filter)
    return {"items": [request_public(r) for r in rows], "count": len(rows)}


@app.post("/api/requests", status_code=201)
def create_request(payload: RequestCreate, conn=Depends(get_db), vault: Vault = Depends(get_vault)) -> dict[str, Any]:
    broker = find_broker(conn, payload.broker_id)
    blob, _ = db.load_profile_blob(conn)
    profile = profile_from_blob(vault, blob)
    letter = letters.build_letter(profile, broker, language=payload.language)
    deadline_at = (datetime.now(timezone.utc) + timedelta(days=letter["deadline_days"])).replace(microsecond=0).isoformat()
    req_id = db.create_request(conn, {
        "broker_id": broker["id"],
        "broker_name": broker["name"],
        "broker_category": broker.get("category", "data_broker"),
        "language": letter["language"],
        "method": broker.get("method", "email"),
        "to_email": broker.get("email", ""),
        "subject_enc": vault.encrypt_text(letter["subject"]),
        "body_enc": vault.encrypt_text(letter["body"]),
        "status": "draft",
        "deadline_days": letter["deadline_days"],
        "deadline_at": deadline_at,
        "note": "",
    })
    row = db.get_request(conn, req_id)
    return {"ok": True, "request": request_public(row or {}), "letter": letter}


@app.get("/api/requests/{request_id}")
def read_request(request_id: int, conn=Depends(get_db), vault: Vault = Depends(get_vault)) -> dict[str, Any]:
    row = db.get_request(conn, request_id)
    if not row:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    return {
        "request": request_public(row),
        "letter": {
            "language": row["language"],
            "subject": vault.decrypt_text(row["subject_enc"]),
            "body": vault.decrypt_text(row["body_enc"]),
        },
        "events": db.list_events(conn, request_id),
    }


@app.get("/api/requests/{request_id}/letter")
def rebuild_letter(request_id: int, language: str | None = None, conn=Depends(get_db), vault: Vault = Depends(get_vault)) -> dict[str, Any]:
    row = db.get_request(conn, request_id)
    if not row:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    broker = find_broker(conn, row["broker_id"])
    blob, _ = db.load_profile_blob(conn)
    profile = profile_from_blob(vault, blob)
    return {"ok": True, "letter": letters.build_letter(profile, broker, language=language)}


@app.patch("/api/requests/{request_id}")
def change_status(request_id: int, payload: RequestPatch, conn=Depends(get_db)) -> dict[str, Any]:
    row = db.get_request(conn, request_id)
    if not row:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    current = row["status"]
    target = payload.status

    if target is None and payload.note is None:
        raise HTTPException(status_code=422, detail="Нечего менять: укажите status и/или note")

    if payload.note is not None:
        db.update_request(conn, request_id, note=payload.note)
        db.add_event(conn, request_id, "note", current, current, "Заметка обновлена")

    if target and target != current:
        if target not in ALLOWED_TRANSITIONS.get(current, set()):
            raise HTTPException(
                status_code=409,
                detail=f"Переход {current} → {target} недопустим. Разрешено: {sorted(ALLOWED_TRANSITIONS.get(current, set()))}",
            )
        ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        fields: dict[str, Any] = {"status": target}
        if target == "sent" and not row["sent_at"]:
            fields["sent_at"] = ts
            fields["deadline_at"] = (
                datetime.now(timezone.utc) + timedelta(days=int(row["deadline_days"] or 30))
            ).replace(microsecond=0).isoformat()
        if target == "responded" and not row["responded_at"]:
            fields["responded_at"] = ts
        if target == "deleted":
            fields["deleted_at"] = ts
        if target == "draft":  # «Повторить»: срок 30 дней стартует заново при новой отправке
            fields.update({
                "sent_at": None, "responded_at": None, "deleted_at": None,
                "deadline_at": None, "error": "",
            })
        db.update_request(conn, request_id, **fields)
        db.add_event(
            conn, request_id, "repeat" if target == "draft" else "status",
            current, target, payload.note or "",
        )
    return {"ok": True, "request": request_public(db.get_request(conn, request_id) or {})}


@app.post("/api/requests/{request_id}/send")
def send_request(request_id: int, payload: SendIn | None = None, conn=Depends(get_db), vault: Vault = Depends(get_vault)) -> dict[str, Any]:
    row = db.get_request(conn, request_id)
    if not row:
        raise HTTPException(status_code=404, detail="Запрос не найден")
    if row["status"] != "draft":
        raise HTTPException(status_code=409, detail="Отправить можно только черновик. Используйте «Повторить», чтобы вернуть в черновик.")

    body = vault.decrypt_text(row["body_enc"])
    subject = vault.decrypt_text(row["subject_enc"])
    blob, _ = db.load_profile_blob(conn)
    profile = profile_from_blob(vault, blob)
    reply_to = (profile.get("emails") or [None])[0]

    to_email = row["to_email"]
    if row["method"] != "email" or not to_email:
        db.update_request(conn, request_id, status="sent", sent_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                          deadline_at=(datetime.now(timezone.utc) + timedelta(days=int(row["deadline_days"] or 30))).replace(microsecond=0).isoformat(),
                          error="")
        db.add_event(conn, request_id, "status", "draft", "sent", "Отправлено вручную (форма/ручной способ)")
        return {"ok": True, "dry_run": True, "detail": "Запрос отмечен отправленным: у сервиса нет email, действуйте через форму по ссылке из карточки.",
                "request": request_public(db.get_request(conn, request_id) or {})}

    result = mailer.send_email(
        to_email, subject, body, reply_to=reply_to,
        force_dry_run=(payload.force_dry_run if payload else None),
    )
    if result["ok"]:
        ts = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        db.update_request(conn, request_id, status="sent", sent_at=ts, error="",
                          deadline_at=(datetime.now(timezone.utc) + timedelta(days=int(row["deadline_days"] or 30))).replace(microsecond=0).isoformat())
        db.add_event(conn, request_id, "send", "draft", "sent",
                     ("DRY_RUN: письмо не отправлено" if result["dry_run"] else f"Письмо отправлено на {to_email}")
                     + (f" · {result.get('message_id', '')}"))
    else:
        db.update_request(conn, request_id, error=result["detail"])
        db.add_event(conn, request_id, "send_failed", "draft", "draft", result["detail"])
    return {"ok": result["ok"], "dry_run": result["dry_run"], "detail": result["detail"],
            "request": request_public(db.get_request(conn, request_id) or {})}


@app.delete("/api/requests/{request_id}")
def remove_request(request_id: int, conn=Depends(get_db)) -> dict[str, Any]:
    if not db.delete_request(conn, request_id):
        raise HTTPException(status_code=404, detail="Запрос не найден")
    return {"ok": True, "detail": "Запрос и его история удалены."}


# --- статистика ------------------------------------------------------------
@app.get("/api/stats")
def get_stats(conn=Depends(get_db), vault: Vault = Depends(get_vault)) -> dict[str, Any]:
    rows = db.list_requests(conn)
    blob, _ = db.load_profile_blob(conn)
    profile = profile_from_blob(vault, blob)
    return stats_mod.compute_stats(rows, profile_filled=profile_filled(profile))


DEMO_SPEC = [
    # (broker, category, method, status, дней назад отправлено, дней до/после дедлайна, дней до ответа)
    ("Spokeo", "people_search", "form", "deleted", 41, -30, 9),
    ("Whitepages", "people_search", "form", "deleted", 35, -30, 14),
    ("Radaris", "people_search", "form", "responded", 12, 18, 4),
    ("Intelius", "people_search", "form", "refused", 28, 2, 6),
    ("Acxiom", "data_broker", "form", "sent", 38, -8, None),
    ("LiveRamp", "marketing", "email", "sent", 33, -3, None),
    ("TruePeopleSearch", "people_search", "form", "deleted", 21, -30, 2),
    ("Яндекс (выдача)", "search", "form", "sent", 9, 21, None),
    ("Google (выдача)", "search", "form", "sent", 6, 24, None),
    ("Российский сервис (152-ФЗ)", "data_broker", "email", "responded", 17, 13, 11),
    ("Маркетинговая база", "marketing", "email", "draft", None, None, None),
    ("Европейский сервис (GDPR)", "data_broker", "email", "sent", 2, 28, None),
]


def build_demo_requests() -> list[dict[str, Any]]:
    today = date.today()
    out: list[dict[str, Any]] = []
    for i, (name, cat, method, status, sent_ago, deadline_offset, resp_days) in enumerate(DEMO_SPEC, start=1):
        sent_at = None
        deadline_at = None
        responded_at = None
        deleted_at = None
        if sent_ago is not None:
            sent_dt = datetime.combine(today - timedelta(days=sent_ago), datetime.min.time(), tzinfo=timezone.utc)
            sent_at = sent_dt.isoformat()
            deadline_at = (sent_dt + timedelta(days=30)).isoformat()
            if resp_days is not None:
                responded_at = (sent_dt + timedelta(days=resp_days)).isoformat()
            if status == "deleted":
                deleted_at = (sent_dt + timedelta(days=(resp_days or 5) + 2)).isoformat()
        out.append({
            "id": 9000 + i,
            "broker_id": f"demo-{i}",
            "broker_name": name,
            "broker_category": cat,
            "method": method,
            "status": status,
            "sent_at": sent_at,
            "responded_at": responded_at,
            "deleted_at": deleted_at,
            "deadline_at": deadline_at,
            "deadline_days": 30,
            "created_at": sent_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        })
    return out


@app.post("/api/stats/demo")
def demo_stats(conn=Depends(get_db)) -> dict[str, Any]:
    data = stats_mod.compute_stats(build_demo_requests(), profile_filled=True, demo=True)
    data["detail"] = DEMO_DENY
    return data


# --- AI-помощник -----------------------------------------------------------
@app.get("/api/assistant/status")
def assistant_status() -> dict[str, Any]:
    cfg = assistant.llm_config()
    return {
        "configured": assistant.is_configured(),
        "model": cfg["model"] or None,
        "base_url_host": (cfg["base_url"].split("//")[-1].split("/")[0] if cfg["base_url"] else None),
        "hint": None if assistant.is_configured() else assistant.HINT_NOT_CONFIGURED,
    }


@app.post("/api/assistant")
async def ask_assistant(payload: ChatIn) -> JSONResponse:
    result = await assistant.ask(payload.question, payload.history)
    if result.get("blocked"):
        return JSONResponse(status_code=422, content={"ok": False, **result})
    if result.get("error"):
        return JSONResponse(status_code=502, content={"ok": False, **result})
    return JSONResponse(content={"ok": True, **result})


# --- очистка / экспорт -----------------------------------------------------
@app.post("/api/wipe")
async def wipe(request: Request, conn=Depends(get_db)) -> dict[str, Any]:
    body = {}
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}
    if str(body.get("confirm", "")).strip().upper() != "DELETE":
        raise HTTPException(
            status_code=422,
            detail="Для полной очистки отправьте {\"confirm\": \"DELETE\"}. Операция необратима.",
        )
    counts = db.wipe_all(conn)
    return {"ok": True, "detail": "Все данные удалены: профиль, запросы, история, ваши сервисы.", "deleted": counts}


@app.get("/api/export")
def export_data(conn=Depends(get_db), vault: Vault = Depends(get_vault)) -> JSONResponse:
    blob, _ = db.load_profile_blob(conn)
    records = []
    for row in db.list_requests(conn):
        records.append({
            **request_public(row),
            "subject": vault.decrypt_text(row["subject_enc"]),
            "body": vault.decrypt_text(row["body_enc"]),
            "events": db.list_events(conn, row["id"]),
        })
    payload = {
        "exported_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "warning": "В файле ВАШИ персональные данные в открытом виде. Храните его как конфиденциальный документ.",
        "profile": profile_from_blob(vault, blob),
        "requests": records,
    }
    return JSONResponse(content=payload, headers={
        "Content-Disposition": 'attachment; filename="datacleaner-export.json"'
    })


# -------------------------------------------------------------------- static
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return JSONResponse({"detail": "static/index.html не найден"}, status_code=500)


@app.get("/api/statuses")
def statuses() -> dict[str, Any]:
    return {"statuses": db.STATUS_LABELS, "transitions": {k: sorted(v) for k, v in ALLOWED_TRANSITIONS.items()},
            "categories": stats_mod.CATEGORY_LABELS}
