"""SQLite-слой: схема, подключение, CRUD.

Персональные данные в базе лежат только в зашифрованном виде (BLOB'ы Fernet).
Метаданные (статусы, даты, названия сервисов) — открытым текстом: они нужны
для статистики и не содержат ПД.
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

# Путь к базе можно переопределить переменной DATACLEANER_DB (полезно на хостингах
# с постоянным диском и в тестах).
DB_PATH = Path(
    os.getenv("DATACLEANER_DB") or (Path(__file__).resolve().parent.parent / "data" / "datacleaner.db")
)

SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS profile (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    data_enc      BLOB    NOT NULL,
    created_at    TEXT    NOT NULL,
    updated_at    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS custom_brokers (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    category      TEXT NOT NULL DEFAULT 'data_broker',
    method        TEXT NOT NULL DEFAULT 'email',
    url           TEXT NOT NULL DEFAULT '',
    email         TEXT NOT NULL DEFAULT '',
    language      TEXT NOT NULL DEFAULT 'ru',
    notes         TEXT NOT NULL DEFAULT '',
    deadline_days INTEGER NOT NULL DEFAULT 30,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requests (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    broker_id         TEXT NOT NULL,
    broker_name       TEXT NOT NULL,
    broker_category   TEXT NOT NULL DEFAULT 'data_broker',
    language          TEXT NOT NULL DEFAULT 'ru',
    method            TEXT NOT NULL DEFAULT 'email',
    to_email          TEXT NOT NULL DEFAULT '',
    subject_enc       BLOB,
    body_enc          BLOB,
    status            TEXT NOT NULL DEFAULT 'draft',
    deadline_days     INTEGER NOT NULL DEFAULT 30,
    created_at        TEXT NOT NULL,
    sent_at           TEXT,
    responded_at      TEXT,
    deleted_at        TEXT,
    deadline_at       TEXT,
    last_action_at    TEXT NOT NULL,
    note              TEXT NOT NULL DEFAULT '',
    error             TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id    INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    type          TEXT NOT NULL,
    from_status   TEXT NOT NULL DEFAULT '',
    to_status     TEXT NOT NULL DEFAULT '',
    note          TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_requests_status ON requests(status);
CREATE INDEX IF NOT EXISTS idx_requests_sent_at ON requests(sent_at);
CREATE INDEX IF NOT EXISTS idx_events_request ON events(request_id);

CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

STATUSES = ("draft", "sent", "responded", "deleted", "refused")
STATUS_LABELS = {
    "draft": "Черновик",
    "sent": "Отправлено",
    "responded": "Ответили",
    "deleted": "Удалено",
    "refused": "Отказ",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def init_db(path: Path | str | None = None) -> None:
    target = Path(path) if path else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(target) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


@contextmanager
def get_conn(path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    target = Path(path) if path else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: соединение живёт один HTTP-запрос и не шарится
    conn = sqlite3.connect(target, timeout=15, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------------------ профиль
def save_profile(conn: sqlite3.Connection, blob: bytes) -> None:
    ts = now_iso()
    exists = conn.execute("SELECT 1 FROM profile WHERE id = 1").fetchone()
    if exists:
        conn.execute("UPDATE profile SET data_enc = ?, updated_at = ? WHERE id = 1", (blob, ts))
    else:
        conn.execute(
            "INSERT INTO profile (id, data_enc, created_at, updated_at) VALUES (1, ?, ?, ?)",
            (blob, ts, ts),
        )


def load_profile_blob(conn: sqlite3.Connection) -> tuple[bytes | None, str | None]:
    row = conn.execute("SELECT data_enc, updated_at FROM profile WHERE id = 1").fetchone()
    if not row:
        return None, None
    return row["data_enc"], row["updated_at"]


# ---------------------------------------------------------- пользовательские БД
def list_custom_brokers(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM custom_brokers ORDER BY created_at").fetchall()
    return [dict(r) for r in rows]


def add_custom_broker(conn: sqlite3.Connection, broker: dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO custom_brokers
           (id, name, category, method, url, email, language, notes, deadline_days, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            broker["id"], broker["name"], broker["category"], broker["method"],
            broker.get("url", ""), broker.get("email", ""), broker.get("language", "ru"),
            broker.get("notes", ""), int(broker.get("deadline_days", 30)), now_iso(),
        ),
    )


def delete_custom_broker(conn: sqlite3.Connection, broker_id: str) -> bool:
    cur = conn.execute("DELETE FROM custom_brokers WHERE id = ?", (broker_id,))
    return cur.rowcount > 0


# ------------------------------------------------------------------- запросы
REQUEST_FIELDS = (
    "broker_id", "broker_name", "broker_category", "language", "method", "to_email",
    "subject_enc", "body_enc", "status", "deadline_days", "deadline_at", "note",
)


def create_request(conn: sqlite3.Connection, data: dict[str, Any]) -> int:
    ts = now_iso()
    cur = conn.execute(
        """INSERT INTO requests
           (broker_id, broker_name, broker_category, language, method, to_email,
            subject_enc, body_enc, status, deadline_days, created_at, last_action_at, note, deadline_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data["broker_id"], data["broker_name"], data.get("broker_category", "data_broker"),
            data.get("language", "ru"), data.get("method", "email"), data.get("to_email", ""),
            data.get("subject_enc"), data.get("body_enc"), data.get("status", "draft"),
            int(data.get("deadline_days", 30)), ts, ts, data.get("note", ""),
            data.get("deadline_at"),
        ),
    )
    req_id = int(cur.lastrowid)
    add_event(conn, req_id, "created", "", data.get("status", "draft"), "Запрос создан")
    return req_id


def get_request(conn: sqlite3.Connection, request_id: int) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM requests WHERE id = ?", (request_id,)).fetchone()
    return dict(row) if row else None


def list_requests(conn: sqlite3.Connection, status: str | None = None) -> list[dict[str, Any]]:
    if status:
        rows = conn.execute(
            "SELECT * FROM requests WHERE status = ? ORDER BY id DESC", (status,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM requests ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def update_request(conn: sqlite3.Connection, request_id: int, **fields: Any) -> None:
    if not fields:
        return
    allowed = set(REQUEST_FIELDS) | {"sent_at", "responded_at", "deleted_at", "last_action_at", "error"}
    unknown = set(fields) - allowed
    if unknown:
        raise ValueError(f"Неизвестные поля: {sorted(unknown)}")
    fields["last_action_at"] = now_iso()
    keys = ", ".join(f"{k} = ?" for k in fields)
    conn.execute(f"UPDATE requests SET {keys} WHERE id = ?", (*fields.values(), request_id))


def delete_request(conn: sqlite3.Connection, request_id: int) -> bool:
    cur = conn.execute("DELETE FROM requests WHERE id = ?", (request_id,))
    return cur.rowcount > 0


# --------------------------------------------------------------------- события
def add_event(
    conn: sqlite3.Connection,
    request_id: int,
    event_type: str,
    from_status: str = "",
    to_status: str = "",
    note: str = "",
) -> None:
    conn.execute(
        "INSERT INTO events (request_id, type, from_status, to_status, note, created_at) VALUES (?,?,?,?,?,?)",
        (request_id, event_type, from_status, to_status, note, now_iso()),
    )


def list_events(conn: sqlite3.Connection, request_id: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM events WHERE request_id = ? ORDER BY id", (request_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# ------------------------------------------------------------------- утилиты
def kv_set(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def kv_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM kv WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def wipe_all(conn: sqlite3.Connection) -> dict[str, int]:
    """Полная очистка: ПД + запросы + кастомные брокеры. Необратимо."""
    counts: dict[str, int] = {}
    for table in ("events", "requests", "custom_brokers", "profile", "kv"):
        counts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        conn.execute(f"DELETE FROM {table}")
    return counts
