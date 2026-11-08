#!/usr/bin/env python3
"""Проверка ЖИВОГО сайта DataCleaner (Render) в браузере.

Запуск (токен доступа передаётся ТОЛЬКО через переменную окружения):
    DC_ACCESS_TOKEN=... python3 tools/live_check.py [url]

Что делает:
  * открывает сайт, вводит код доступа, снимает экраны dashboard/requests/autopilot/ai;
  * проверяет, что бейдж показывает серверный режим, самопроверка проходит;
  * задаёт вопрос AI и ждёт потоковый ответ;
  * проверяет телефон 390 px (нет горизонтальной прокрутки, ошибок JS).
Скриншоты: screens/live-*.png
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from playwright.async_api import async_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "https://datacleaner-st2u.onrender.com/"
TOKEN = os.getenv("DC_ACCESS_TOKEN", "")
SHOTS = Path(__file__).resolve().parent.parent / "screens"


async def main() -> int:
    if not TOKEN:
        print("Нужен DC_ACCESS_TOKEN в окружении")
        return 2
    SHOTS.mkdir(exist_ok=True)
    errors: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1440, "height": 960}, device_scale_factor=2)
        page = await ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(URL, wait_until="networkidle", timeout=120000)
        await page.wait_for_timeout(1500)

        if await page.locator("#access-code").count():
            await page.fill("#access-code", TOKEN)
            await page.click("#modal-foot button.btn.primary")
            await page.wait_for_timeout(4000)

        badge = (await page.inner_text("#mode-badge")).replace("\n", " ")
        await page.screenshot(path=str(SHOTS / "live-01-dashboard.png"), full_page=True)

        await page.click('button[data-view="requests"]')
        await page.wait_for_timeout(800)
        await page.screenshot(path=str(SHOTS / "live-02-requests.png"), full_page=True)

        await page.click('button[data-view="autopilot"]')
        await page.wait_for_timeout(900)
        smtp_status = await page.inner_text("#smtp-status")
        await page.screenshot(path=str(SHOTS / "live-03-autopilot.png"), full_page=True)

        await page.click('button[data-view="ai"]')
        await page.wait_for_timeout(600)
        await page.fill("#chat-input", "Как отбить отказ «данные из общедоступных источников»?")
        await page.click("#btn-ai-send")
        await page.wait_for_timeout(14000)
        chat = await page.inner_text("#chat")
        await page.screenshot(path=str(SHOTS / "live-04-ai.png"), full_page=True)

        await page.click("#btn-self-test")
        await page.wait_for_timeout(1200)
        selftest = (await page.inner_text("#modal-body")).splitlines()[0]
        await page.click("#modal-close")

        mctx = await browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2)
        mp = await mctx.new_page()
        mp.on("pageerror", lambda e: errors.append("mobile: " + str(e)))
        await mp.goto(URL, wait_until="networkidle", timeout=120000)
        await mp.wait_for_timeout(1800)
        if await mp.locator("#access-code").count():
            await mp.fill("#access-code", TOKEN)
            await mp.click("#modal-foot button.btn.primary")
            await mp.wait_for_timeout(4000)
        await mp.screenshot(path=str(SHOTS / "live-05-mobile.png"), full_page=True)
        widths = await mp.evaluate("({sw: document.documentElement.scrollWidth, cw: document.documentElement.clientWidth})")

        await browser.close()

    print("бейдж:", badge)
    print("SMTP:", smtp_status.replace("\n", " ")[:120])
    print("самопроверка:", selftest)
    print("AI-ответ:", chat.replace("\n", " | ")[-600:])
    print("390 px:", widths)
    print("ошибки JS:", errors or "нет")
    ok = (badge.startswith("сервер") and widths["sw"] <= widths["cw"] + 1
          and not errors and selftest.startswith("22 из 22") and "AI" in chat)
    print("\nИТОГ:", "OK" if ok else "ЕСТЬ ЗАМЕЧАНИЯ")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
