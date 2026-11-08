#!/usr/bin/env python3
"""Дымовой UI-тест DataCleaner в реальном браузере (Playwright + Chromium).

Что проверяется:
  * серверная версия (http://127.0.0.1:8811) — все 6 экранов, профиль, каталог,
    создание и отправка запроса, автопилот, AI-поток, PII-фильтр, самопроверка;
  * локальная версия (file://…/datacleaner.html) — профиль, письмо, отправка,
    самопроверка, демо-статистика, подсказка «AI не настроен»;
  * телефон 390 px — нет горизонтальной прокрутки и ошибок JS.

Запуск:
    pip install playwright && python3 -m playwright install-deps chromium \
        && python3 -m playwright install chromium
    bash tools/run_ui_server.sh &          # сервер на :8811 (DRY_RUN=1)
    python3 tools/ui_smoke.py

Скриншоты складываются в screens/. Скрипт ничего не удаляет: серверную базу
для проверок держите отдельной (DATACLEANER_DB=/tmp/ui.db в run_ui_server.sh).
"""

from __future__ import annotations

import asyncio
import json
import sys
import urllib.request
from pathlib import Path

from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8811/"
LOCAL = (Path(__file__).resolve().parent.parent / "datacleaner.html").as_uri()
SHOTS = Path(__file__).resolve().parent.parent / "screens"
VIEWS = ["dashboard", "requests", "catalog", "autopilot", "ai", "profile"]


def api(path: str, method: str = "GET", body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        return json.loads(resp.read().decode())


async def shots(page, name: str, full: bool = True) -> None:
    SHOTS.mkdir(exist_ok=True)
    await page.screenshot(path=str(SHOTS / name), full_page=full)


async def server_flow(browser) -> dict:
    ctx = await browser.new_context(viewport={"width": 1440, "height": 960}, device_scale_factor=2)
    page = await ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    await page.goto(BASE, wait_until="networkidle")
    await page.wait_for_timeout(1000)
    await shots(page, "21-srv-dashboard.png")

    # профиль
    await page.click('button[data-view="profile"]')
    await page.fill("#pf-name", "Иван Иванов")
    await page.fill("#pf-emails", "ivan@example.com")
    await page.fill("#pf-phones", "+7 900 000-00-00")
    await page.fill("#pf-city", "Петрозаводск")
    await page.fill("#pf-birth", "1990")
    await page.click('#profile-form button[type="submit"]')
    await page.wait_for_timeout(800)
    await shots(page, "22-srv-profile.png")

    # каталог → запрос → письмо
    await page.click('button[data-view="catalog"]')
    await page.wait_for_timeout(400)
    await shots(page, "23-srv-catalog.png")
    await page.click('#broker-list button[data-act="create"]')
    await page.wait_for_timeout(1200)
    await shots(page, "24-srv-letter.png", full=False)
    await page.click("#modal-close")

    # запросы: отправка
    await page.click('button[data-view="requests"]')
    await page.wait_for_timeout(400)
    await page.click('#request-list button[data-act="send"]')
    await page.wait_for_timeout(1200)
    await page.click("#modal-close")
    await shots(page, "25-srv-requests.png")

    # автопилот
    await page.click('button[data-view="autopilot"]')
    await page.wait_for_timeout(500)
    await page.select_option("#smtp-preset", "yandex")
    await page.wait_for_timeout(250)
    preset = [await page.input_value("#smtp-host"), await page.input_value("#smtp-port")]
    await page.click("#ap-run")
    await page.wait_for_timeout(1500)
    await shots(page, "26-srv-autopilot.png")
    pilot_log = await page.inner_text("#pilot-log")

    # AI
    await page.click('button[data-view="ai"]')
    await page.wait_for_timeout(400)
    await page.fill("#chat-input", "Оператор не ответил 30 дней — что делать дальше?")
    await page.click("#btn-ai-send")
    await page.wait_for_timeout(3500)
    await page.fill("#chat-input", "мой email test@mail.ru — как удалить?")
    await page.click("#btn-ai-send")
    await page.wait_for_timeout(1200)
    await shots(page, "27-srv-ai.png")
    chat = await page.inner_text("#chat")

    # самопроверка
    await page.click("#btn-self-test")
    await page.wait_for_timeout(1000)
    selftest = (await page.inner_text("#modal-body")).splitlines()[0]
    await shots(page, "28-srv-selftest.png", full=False)
    await page.click("#modal-close")

    # демо-статистика
    await page.click('button[data-view="dashboard"]')
    await page.click("#btn-demo")
    await page.wait_for_timeout(1200)
    await shots(page, "29-srv-demo.png")
    await ctx.close()
    return {"errors": errors, "preset": preset, "pilot_log": pilot_log, "chat": chat, "selftest": selftest}


async def local_flow(browser) -> dict:
    ctx = await browser.new_context(viewport={"width": 1440, "height": 960}, device_scale_factor=2)
    page = await ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    await page.goto(LOCAL)
    await page.wait_for_timeout(1200)
    badge = await page.inner_text("#mode-badge")
    await shots(page, "30-local-dashboard.png")

    await page.click('button[data-view="profile"]')
    await page.fill("#pf-name", "Пётр Петров")
    await page.fill("#pf-emails", "petr@example.com")
    await page.fill("#pf-phones", "+7 911 111-11-11")
    await page.click('#profile-form button[type="submit"]')
    await page.wait_for_timeout(600)
    await page.click('button[data-view="catalog"]')
    await page.wait_for_timeout(400)
    await page.click('#broker-list button[data-act="create"]')
    await page.wait_for_timeout(1000)
    await shots(page, "31-local-letter.png", full=False)
    await page.click("#modal-close")
    await page.click('button[data-view="requests"]')
    await page.wait_for_timeout(300)
    await page.click('#request-list button[data-act="send"]')
    await page.wait_for_timeout(900)
    await page.click("#modal-close")
    await shots(page, "32-local-requests.png")
    await page.click("#btn-self-test")
    await page.wait_for_timeout(900)
    selftest = (await page.inner_text("#modal-body")).splitlines()[0]
    await page.click("#modal-close")
    await page.click('button[data-view="dashboard"]')
    await page.click("#btn-demo")
    await page.wait_for_timeout(1000)
    await shots(page, "33-local-demo.png")
    await page.click('button[data-view="ai"]')
    await page.fill("#chat-input", "Что делать, если оператор не ответил?")
    await page.click("#btn-ai-send")
    await page.wait_for_timeout(1200)
    chat = await page.inner_text("#chat")
    await shots(page, "34-local-ai.png")
    await ctx.close()
    return {"badge": badge, "errors": errors, "selftest": selftest, "chat": chat}


async def mobile_flow(browser) -> dict:
    out = {}
    for label, url in (("srv", BASE), ("local", LOCAL)):
        # is_mobile=False: в этой сборке Chromium is_mobile меняет ширину макета
        ctx = await browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        page = await ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(url)
        await page.wait_for_timeout(1200)
        widths = {}
        for view in VIEWS:
            await page.click('#bottom-nav button[data-view="%s"]' % view)
            await page.wait_for_timeout(450)
            widths[view] = await page.evaluate(
                "({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})")
        await page.click('#bottom-nav button[data-view="dashboard"]')
        await page.wait_for_timeout(500)
        await shots(page, f"35-{label}-mobile.png")
        out[label] = {"errors": errors, "widths": widths}
        await ctx.close()
    return out


async def main() -> int:
    try:
        text = urllib.request.urlopen(BASE + "api/health", timeout=10).read().decode()  # noqa: S310
    except Exception as exc:  # noqa: BLE001
        print(f"Сервер не отвечает на {BASE}: {exc}\nЗапустите: bash tools/run_ui_server.sh")
        return 2
    print("health:", text.strip())

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        srv = await server_flow(browser)
        loc = await local_flow(browser)
        mob = await mobile_flow(browser)
        await browser.close()

    print("\n=== СЕРВЕР ===")
    print("SMTP-пресет Яндекса:", srv["preset"])
    print("журнал автопилота:", srv["pilot_log"].replace("\n", " | ")[:240])
    print("самопроверка:", srv["selftest"])
    print("чат:", srv["chat"].replace("\n", " | ")[:400])
    print("ошибки JS:", srv["errors"] or "нет")

    print("\n=== ЛОКАЛЬНЫЙ ФАЙЛ ===")
    print("бейдж режима:", loc["badge"].replace("\n", " "))
    print("самопроверка:", loc["selftest"])
    print("чат:", loc["chat"].replace("\n", " | ")[:300])
    print("ошибки JS:", loc["errors"] or "нет")

    print("\n=== ТЕЛЕФОН 390 px ===")
    for label, data in mob.items():
        worst = {k: v for k, v in data["widths"].items() if v["sw"] > v["cw"]}
        print(label, "горизонтальная прокрутка:", worst or "нет", "ошибки JS:", data["errors"] or "нет")

    ok = (not srv["errors"] and not loc["errors"]
          and all(not d["errors"] for d in mob.values())
          and not any(v["sw"] > v["cw"] for d in mob.values() for v in d["widths"].values())
          and srv["selftest"].startswith("22 из 22") and loc["selftest"].startswith("22 из 22"))
    print("\nИТОГ:", "OK" if ok else "ЕСТЬ ЗАМЕЧАНИЯ")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
