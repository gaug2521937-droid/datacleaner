#!/usr/bin/env python3
"""Сборка одностраничной версии DataCleaner.

Источники:
    frontend/index.template.html   — разметка и CSS
    frontend/js/01-core.js         — утилиты и чистая логика (письма, PII, статусы)
    frontend/js/02-stats-store.js  — статистика, хранилище, слой API
    frontend/js/03-ui.js           — рендеринг
    frontend/js/04-actions.js      — действия, самопроверка, запуск

Результат:
    datacleaner.html          — автономный файл (открывается с телефона/ПК без сервера)
    app/static/index.html     — тот же файл, его отдаёт FastAPI по адресу /

Запуск:  python tools/build_html.py
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "frontend" / "index.template.html"
JS_FILES = [
    ROOT / "frontend" / "js" / "01-core.js",
    ROOT / "frontend" / "js" / "02-stats-store.js",
    ROOT / "frontend" / "js" / "03-ui.js",
    ROOT / "frontend" / "js" / "04-actions.js",
]
TARGETS = [ROOT / "datacleaner.html", ROOT / "app" / "static" / "index.html"]

BANNER = (
    "<!--\n"
    "  Файл собран автоматически: python tools/build_html.py\n"
    "  Правьте исходники в frontend/ (index.template.html + frontend/js/*.js),\n"
    "  а не этот файл — иначе изменения потеряются при следующей сборке.\n"
    "  Внешних CSS/JS/шрифтов нет: файл работает офлайн и с телефона.\n"
    "-->\n"
)


def build() -> str:
    if not TEMPLATE.exists():
        raise SystemExit(f"Нет шаблона: {TEMPLATE}")
    html = TEMPLATE.read_text(encoding="utf-8")

    parts = []
    for path in JS_FILES:
        if not path.exists():
            raise SystemExit(f"Нет исходника: {path}")
        parts.append(f"/* ---------- {path.name} ---------- */\n" + path.read_text(encoding="utf-8"))

    script = "<script>\n" + "\n".join(parts) + "\n</script>\n"

    if "</body>" not in html:
        raise SystemExit("В шаблоне нет </body> — некуда вставлять скрипт")
    html = html.replace("</body>", script + "</body>", 1)

    # баннер после <!DOCTYPE html>
    marker = "<!DOCTYPE html>\n"
    if html.startswith(marker):
        html = marker + BANNER + html[len(marker):]
    else:
        html = BANNER + html
    return html


def main() -> None:
    html = build()
    for target in TARGETS:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
        size = len(html.encode("utf-8"))
        print(f"собрано: {target.relative_to(ROOT)} ({size / 1024:.1f} КиБ)")
    head = html.split("<script>")[0]
    # xmlns и data:-URI — не сетевые запросы, поэтому их не считаем
    probe = re.sub(r"xmlns='[^']*'|xmlns=\"[^\"]*\"|data:[^\"'()\s]+", "", head)
    externals = sorted({m.group(0) for m in re.finditer(r"https?://[^\"'\s>]+", probe)})
    print("внешние ресурсы в разметке/CSS:", externals or "нет")


if __name__ == "__main__":
    main()
