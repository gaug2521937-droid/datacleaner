#!/usr/bin/env python3
"""Скриншоты новых карточек: простой вход (адрес + пароль) и переключатель отправки."""
import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

BASE = "http://127.0.0.1:8811/"
SHOTS = Path(__file__).resolve().parent.parent / "screens"


async def main() -> None:
    SHOTS.mkdir(exist_ok=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=2)
        page = await ctx.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.goto(BASE, wait_until="networkidle")
        await page.wait_for_timeout(800)
        await page.click('button[data-view="autopilot"]')
        await page.wait_for_timeout(900)

        # 1. карточка «вход в почту» крупным планом
        quick = page.locator('#quick-card')
        await quick.scroll_into_view_if_needed()
        await page.wait_for_timeout(400)
        await quick.screenshot(path=str(SHOTS / "41-quick-card.png"))

        # 2. автодетект по адресу
        await page.fill('#quick-email', 'ivan.petrov@yandex.ru')
        await page.wait_for_timeout(500)
        print("автодетект:", (await page.inner_text('#quick-autodetect')).strip())
        await quick.screenshot(path=str(SHOTS / "42-quick-autodetect.png"))

        # 3. ошибка входа — реальная попытка проверки SMTP (сеть в песочнице закрыта)
        await page.fill('#quick-pass', 'test-password-123')
        await page.click('#quick-connect')
        await page.wait_for_timeout(3500)
        print("результат:", (await page.inner_text('#quick-result')).strip()[:220])
        await quick.screenshot(path=str(SHOTS / "43-quick-result.png"))
        await page.fill('#quick-pass', '')

        # 4. справка «какой пароль вводить»
        await page.click('#quick-tip')
        await page.wait_for_timeout(700)
        await page.screenshot(path=str(SHOTS / "44-quick-help.png"))
        # закрыть модалку
        try:
            await page.click('#modal-foot button.btn.primary')
        except Exception:
            await page.keyboard.press('Escape')
        await page.wait_for_timeout(500)

        # 5. переключатель реальной отправки
        mode = page.locator('#send-mode-card')
        await mode.scroll_into_view_if_needed()
        await page.wait_for_timeout(400)
        await mode.screenshot(path=str(SHOTS / "45-send-mode.png"))
        print("режим:", (await page.inner_text('#send-mode-state')).strip())

        # 6. весь экран «Автопилот» с новыми карточками
        await page.screenshot(path=str(SHOTS / "46-autopilot-full.png"), full_page=True)

        # 7. телефон
        await page.set_viewport_size({"width": 390, "height": 900})
        await page.wait_for_timeout(600)
        over = await page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
        print("горизонтальная прокрутка 390px:", over)
        await page.screenshot(path=str(SHOTS / "47-autopilot-390.png"), full_page=True)

        print("ошибки JS:", errors or "нет")
        await browser.close()


asyncio.run(main())
