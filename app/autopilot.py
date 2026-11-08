"""Автопилот: сам отправляет черновики и напоминания операторам.

Работает как фоновая задача внутри процесса FastAPI (без Celery и Redis —
бесплатный хостинг этого не требует):

* «auto_send»        — новые черновики уходят сразу, как только появляются;
* «followup_enabled» — через N дней после отправки без ответа оператору уходит
                       повторное требование (один раз на запрос);
* DRY_RUN=1          — всё считается, события пишутся, но письма не уходят.

Интервал цикла настраивается в интерфейсе (по умолчанию 15 минут).
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from . import db, google_oauth, letters, mailer, settings as settings_mod
from .crypto import Vault

log = logging.getLogger("datacleaner.autopilot")

FOLLOWUP_EVENT = "followup"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(ts: str | None) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _profile(conn, vault: Vault) -> dict[str, Any]:
    blob, _ = db.load_profile_blob(conn)
    if not blob:
        return {}
    try:
        return vault.decrypt_json(blob) or {}
    except Exception:  # noqa: BLE001
        return {}


def _smtp(conn, vault: Vault) -> dict[str, Any]:
    """Настройки почты + активный транспорт: OAuth-токен Google, если подключён."""
    cfg = settings_mod.effective_smtp(conn, vault)
    token = google_oauth.access_token(conn, vault)
    if token:
        cfg["google_access"] = token
        cfg["google_sender"] = google_oauth.connected_email(conn, vault) or ""
    return cfg


def send_one(conn, vault: Vault, request_id: int, dry_run: bool | None = None) -> dict[str, Any]:
    """Отправить конкретный запрос. Используется и API, и автопилотом."""
    row = db.get_request(conn, request_id)
    if not row:
        return {"ok": False, "detail": "Запрос не найден"}
    if row["status"] != "draft":
        return {"ok": False, "detail": "Это не черновик"}

    profile = _profile(conn, vault)
    subject = vault.decrypt_text(row["subject_enc"])
    body = vault.decrypt_text(row["body_enc"])
    reply_to = (profile.get("emails") or [None])[0]
    cfg = _smtp(conn, vault)
    ts = _now().replace(microsecond=0)

    if row["method"] != "email" or not row["to_email"]:
        db.update_request(
            conn, request_id, status="sent", sent_at=ts.isoformat(), error="",
            deadline_at=(ts + timedelta(days=int(row["deadline_days"] or 30))).isoformat(),
        )
        db.add_event(conn, request_id, "status", "draft", "sent", "Отправлено вручную (форма/ручной способ)")
        return {"ok": True, "dry_run": True, "detail": "Нет email — запрос отмечен отправленным, отправьте через форму."}

    result = mailer.send_email(row["to_email"], subject, body, reply_to=reply_to,
                               force_dry_run=dry_run, cfg=cfg)
    if result["ok"]:
        db.update_request(
            conn, request_id, status="sent", sent_at=ts.isoformat(), error="",
            deadline_at=(ts + timedelta(days=int(row["deadline_days"] or 30))).isoformat(),
        )
        db.add_event(conn, request_id, "send", "draft", "sent",
                     ("DRY_RUN: письмо не отправлено" if result["dry_run"] else f"Письмо отправлено на {row['to_email']}")
                     + (f" · {result.get('message_id', '')}"))
    else:
        db.update_request(conn, request_id, error=result["detail"])
        db.add_event(conn, request_id, "send_failed", "draft", "draft", result["detail"])
    return result


def send_followup(conn, vault: Vault, request_id: int, dry_run: bool | None = None,
                  days: int = 14) -> dict[str, Any]:
    """Отправить повторное требование по запросу без ответа."""
    row = db.get_request(conn, request_id)
    if not row:
        return {"ok": False, "detail": "Запрос не найден"}
    if row["status"] not in ("sent", "refused"):
        return {"ok": False, "detail": "Напоминание отправляется только по запросам без ответа"}

    broker = {"id": row["broker_id"], "name": row["broker_name"], "language": row["language"],
              "email": row["to_email"]}
    profile = _profile(conn, vault)
    letter = letters.build_followup(profile, broker, language=row["language"],
                                    original_date=row["sent_at"])
    cfg = _smtp(conn, vault)
    to_email = row["to_email"]
    ts = _now().replace(microsecond=0)

    if row["method"] != "email" or not to_email:
        db.update_request(conn, request_id, last_action_at=ts.isoformat(),
                          deadline_at=(ts + timedelta(days=days)).isoformat())
        db.add_event(conn, request_id, FOLLOWUP_EVENT, row["status"], row["status"],
                     "Напоминание подготовлено (нет email — отправьте вручную)")
        return {"ok": True, "dry_run": True, "detail": "Нет email: напоминание сформировано, отправьте его через форму.",
                "letter": letter}

    result = mailer.send_email(to_email, letter["subject"], letter["body"], cfg=cfg,
                               reply_to=(profile.get("emails") or [None])[0], force_dry_run=dry_run)
    if result["ok"]:
        db.update_request(conn, request_id, last_action_at=ts.isoformat(),
                          deadline_at=(ts + timedelta(days=days)).isoformat())
        db.add_event(conn, request_id, FOLLOWUP_EVENT, row["status"], row["status"],
                     ("DRY_RUN: напоминание не отправлено" if result["dry_run"]
                      else f"Отправлено повторное требование на {to_email}"))
    else:
        db.update_request(conn, request_id, error=result["detail"])
        db.add_event(conn, request_id, "followup_failed", row["status"], row["status"], result["detail"])
    return {**result, "letter": letter}


def cycle(conn=None, vault: Vault | None = None, force: bool = False) -> dict[str, Any]:
    """Один проход автопилота. Возвращает отчёт для интерфейса и логов."""
    own_conn = conn is None
    vault = vault or Vault()
    report: dict[str, Any] = {"started_at": _now().replace(microsecond=0).isoformat(),
                              "sent": [], "followups": [], "manual": [],
                              "skipped": "", "errors": []}

    def run(c):
        cfg = settings_mod.load(c, vault)["autopilot"]
        dry = mailer.dry_run_enabled()
        smtp = _smtp(c, vault)
        if not mailer.mail_ready(smtp) and not dry:
            report["skipped"] = ("Почта не настроена и DRY_RUN выключен — отправлять нечем: "
                                 "заполните SMTP в «Автопилоте» или задайте BREVO_API_KEY / RESEND_API_KEY")
        if cfg.get("auto_send") or force:
            for row in db.list_requests(c, "draft"):
                if row["method"] != "email" or not row["to_email"]:
                    # у брокера нет email: письмо автоматически не отправить,
                    # пользователь отправляет его через форму на сайте
                    report["manual"].append({"id": row["id"], "broker": row["broker_name"]})
                    continue
                res = send_one(c, vault, row["id"])
                (report["sent"] if res.get("ok") else report["errors"]).append(
                    {"id": row["id"], "broker": row["broker_name"], "detail": res.get("detail", "")[:160]})
        if cfg.get("followup_enabled") and not force:
            days = int(cfg.get("followup_days") or 30)
            for row in db.list_requests(c, "sent"):
                sent_at = _parse(row["sent_at"])
                if not sent_at or _now() - sent_at < timedelta(days=days):
                    continue
                events = db.list_events(c, row["id"])
                if any(e["type"] == FOLLOWUP_EVENT for e in events):
                    continue  # напоминание уже отправляли — не спамим
                res = send_followup(c, vault, row["id"])
                (report["followups"] if res.get("ok") else report["errors"]).append(
                    {"id": row["id"], "broker": row["broker_name"], "detail": res.get("detail", "")[:160]})
        return report

    if own_conn:
        with db.get_conn() as c:
            run(c)
    else:
        run(conn)
    report["finished_at"] = _now().replace(microsecond=0).isoformat()
    if report["sent"] or report["followups"] or report["errors"]:
        log.info("autopilot: отправлено %s, напоминаний %s, ошибок %s",
                 len(report["sent"]), len(report["followups"]), len(report["errors"]))
    return report


async def loop(stop_event: asyncio.Event) -> None:
    """Фоновый цикл: спит interval_minutes и вызывает cycle()."""
    log.info("автопилот запущен")
    try:
        while not stop_event.is_set():
            try:
                vault = Vault()
                with db.get_conn() as conn:
                    cfg = settings_mod.load(conn, vault)["autopilot"]
                interval = max(5, int(cfg.get("interval_minutes") or 15))
                if cfg.get("auto_send") or cfg.get("followup_enabled"):
                    await asyncio.to_thread(cycle)
                try:
                    await asyncio.wait_for(stop_event.wait(), timeout=interval * 60)
                except asyncio.TimeoutError:
                    pass
            except Exception as exc:  # noqa: BLE001 — цикл не должен падать
                log.warning("автопилот: ошибка цикла: %s", exc)
                await asyncio.sleep(60)
    finally:
        log.info("автопилот остановлен")
