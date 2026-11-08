#!/usr/bin/env python3
"""Деплой DataCleaner на Render: GitHub-репозиторий → сервис → проверка.

Одной командой:
    GH_TOKEN=<токен с Contents:write> RENDER_API_KEY=<rnd_...> python3 tools/deploy_render.py

Что делает:
 1. Проверяет Render-ключ и находит ownerId (workspace).
 2. Проверяет GitHub-токен: логин, наличие репозитория, при необходимости создаёт его.
 3. Коммитит и пушит текущий каталог в репозиторий (ветка main).
 4. Создаёт (или обновляет) Render web service: Docker, план free, health check /api/health.
 5. Генерирует DATA_KEY и ACCESS_TOKEN (если не заданы), прокидывает env-переменные.
 6. Ждёт первый деплой и печатает адрес сервиса и код доступа.

Переменные окружения:
    GH_TOKEN            обязательна, fine-grained PAT с «Contents: Read and write»
                        (+ «Administration: Read and write», если репозиторий надо создать)
    RENDER_API_KEY      обязательна, ключ Render
    REPO                имя репозитория, по умолчанию datacleaner
    BRANCH              ветка, по умолчанию main
    REGION              регион Render, по умолчанию frankfurt
    SERVICE_NAME        имя сервиса, по умолчанию datacleaner
    DATA_KEY            ключ Fernet (если нет — сгенерируется и будет напечатан)
    ACCESS_TOKEN        код доступа к приложению (если нет — сгенерируется)
    LLM_API_KEY, LLM_BASE_URL, LLM_MODEL   настройки AI (необязательно)
    DRY_RUN             по умолчанию 1
    SKIP_PUSH=1         не пушить код, только создать сервис
"""

from __future__ import annotations

import base64
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GITHUB_API = "https://api.github.com"
RENDER_API = "https://api.render.com/v1"


# ---------------------------------------------------------------- httpx-less API
def api(method: str, url: str, token: str, payload: dict | None = None) -> tuple[int, object]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = resp.read().decode() or "{}"
            return resp.status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode() or "{}"
        try:
            return exc.code, json.loads(body)
        except json.JSONDecodeError:
            return exc.code, {"message": body[:300]}


def die(msg: str) -> None:
    print(f"\n✖ {msg}\n")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"✔ {msg}")


def fernet_key() -> str:
    raw = secrets.token_bytes(32)
    return base64.urlsafe_b64encode(raw).decode()


# --------------------------------------------------------------------- steps
def check_render(key: str) -> str:
    status, data = api("GET", f"{RENDER_API}/owners?limit=20", key)
    if status != 200 or not isinstance(data, list) or not data:
        die(f"Render-ключ не принят ({status}). Проверьте RENDER_API_KEY.")
    owner = data[0]["owner"]
    ok(f"Render: workspace «{owner['name']}» ({owner['id']})")
    return owner["id"]


def check_github(key: str, repo: str) -> str:
    status, data = api("GET", f"{GITHUB_API}/user", key)
    if status != 200:
        die(f"GitHub-токен не принят ({status}).")
    login = data["login"]
    ok(f"GitHub: пользователь {login}")
    return login


def ensure_repo(key: str, login: str, repo: str) -> str:
    full = f"{login}/{repo}"
    status, data = api("GET", f"{GITHUB_API}/repos/{full}", key)
    if status == 200:
        ok(f"Репозиторий уже есть: {full}")
    elif status == 404:
        print(f"… создаю репозиторий {full}")
        status, data = api("POST", f"{GITHUB_API}/user/repos", key, {
            "name": repo,
            "description": "DataCleaner — удаление персональных данных: 152-ФЗ, GDPR, CCPA",
            "private": False,
            "auto_init": False,
        })
        if status not in (200, 201):
            die(
                "Не удалось создать репозиторий: "
                f"{data.get('message')}. Токену нужны права «Administration: Read and write». "
                "Либо создайте пустой публичный репозиторий вручную и повторите запуск."
            )
        ok(f"Создан репозиторий {full}")
    else:
        die(f"Ошибка доступа к репозиторию: {status} {data.get('message')}")
    return full


def push(full: str, branch: str, token: str) -> None:
    git = lambda *args: subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)  # noqa: E731
    git("init", "-q")
    git("config", "user.name", "DataCleaner")
    git("config", "user.email", "datacleaner@users.noreply.github.com")
    git("add", "-A")
    git("commit", "-q", "-m", "DataCleaner deploy")
    git("branch", "-M", branch)
    url = f"https://x-access-token:{token}@github.com/{full}.git"
    res = git("push", "--force", url, f"{branch}:{branch}")
    if res.returncode != 0:
        tail = (res.stderr or res.stdout).strip().splitlines()[-3:]
        die("git push не удался:\n  " + "\n  ".join(tail) +
            "\n  Проверьте, что у токена есть право «Contents: Read and write» на этот репозиторий.")
    ok(f"Код запушен в {full} (ветка {branch})")


def find_service(key: str, owner: str, name: str) -> dict | None:
    status, data = api("GET", f"{RENDER_API}/services?limit=100", key)
    if status != 200 or not isinstance(data, list):
        return None
    for item in data:
        svc = item.get("service", {})
        if svc.get("name") == name and svc.get("ownerId", owner) == owner:
            return svc
    return None


def create_service(key: str, owner: str, name: str, repo_url: str, branch: str,
                   region: str, env_vars: list[dict]) -> dict:
    payload = {
        "type": "web_service",
        "name": name,
        "ownerId": owner,
        "repo": repo_url,
        "branch": branch,
        "autoDeploy": "yes",
        "envVars": env_vars,
        "serviceDetails": {
            "env": "docker",
            "plan": "free",
            "region": region,
            "healthCheckPath": "/api/health",
            "dockerfilePath": "./Dockerfile",
        },
    }
    status, data = api("POST", f"{RENDER_API}/services", key, payload)
    if status not in (200, 201):
        die(f"Render не создал сервис: {status} {data.get('message') or json.dumps(data)[:400]}")
    return data.get("service", data)


def wait_live(key: str, service_id: str, timeout: int = 900) -> dict:
    deadline = time.time() + timeout
    last = ""
    while time.time() < deadline:
        status, data = api("GET", f"{RENDER_API}/services/{service_id}", key)
        if status == 200:
            svc = data.get("service", data)
            deploy_status = (svc.get("serviceDetails") or {}).get("deployStatus") or svc.get("deployStatus")
            if deploy_status and deploy_status != last:
                print(f"… статус деплоя: {deploy_status}")
                last = deploy_status
            if deploy_status in ("live", "deployed"):
                return svc
            if deploy_status in ("build_failed", "update_failed", "canceled", "deactivated"):
                print("✖ Деплой не удался. Логи: Render Dashboard → сервис → Logs.")
                return svc
        time.sleep(12)
    print("… ждём дольше обычного: сборка Docker на free-плане может занять 5–10 минут.")
    return {}


def main() -> None:
    gh = (os.getenv("GH_TOKEN") or "").strip()
    rk = (os.getenv("RENDER_API_KEY") or "").strip()
    if not gh or not rk:
        die("Задайте GH_TOKEN и RENDER_API_KEY (см. докстринг в начале файла).")

    repo = os.getenv("REPO", "datacleaner")
    branch = os.getenv("BRANCH", "main")
    region = os.getenv("REGION", "frankfurt")
    service_name = os.getenv("SERVICE_NAME", "datacleaner")

    data_key = os.getenv("DATA_KEY") or fernet_key()
    access_token = os.getenv("ACCESS_TOKEN") or ("dc-" + secrets.token_urlsafe(18))

    owner = check_render(rk)
    login = check_github(gh, repo)

    if os.getenv("SKIP_PUSH") == "1":
        full = f"{login}/{repo}"
        ok(f"Пуш пропущен, используем {full}")
    else:
        full = ensure_repo(gh, login, repo)
        push(full, branch, gh)

    repo_url = f"https://github.com/{full}"
    existing = find_service(rk, owner, service_name)
    if existing:
        ok(f"Сервис «{service_name}» уже существует: {existing.get('serviceDetails', {}).get('url', '')}")
        svc = existing
    else:
        env_vars = [
            {"key": "DATA_KEY", "value": data_key},
            {"key": "ACCESS_TOKEN", "value": access_token},
            {"key": "DRY_RUN", "value": os.getenv("DRY_RUN", "1")},
            {"key": "DATACLEANER_DB", "value": "/data/datacleaner.db"},
        ]
        for env_key in ("LLM_API_KEY", "LLM_BASE_URL", "LLM_MODEL"):
            value = (os.getenv(env_key) or "").strip()
            if value:
                env_vars.append({"key": env_key, "value": value})
        print(f"… создаю Render web service «{service_name}» ({region}, Docker, free)")
        svc = create_service(rk, owner, service_name, repo_url, branch, region, env_vars)

    service_id = svc.get("id")
    url = (svc.get("serviceDetails") or {}).get("url") or ""
    if service_id:
        live = wait_live(rk, service_id)
        url = (live.get("serviceDetails") or {}).get("url") or url

    print("\n" + "=" * 62)
    print("DataCleaner задеплоен")
    print("=" * 62)
    print(f"Репозиторий : {repo_url}")
    print(f"Адрес       : {url or 'смотрите Render Dashboard → сервис → URL'}")
    print(f"Код доступа : {access_token}")
    print(f"DATA_KEY    : {data_key}")
    print("=" * 62)
    print("Сохраните DATA_KEY: без него данные в базе не расшифровать.")
    print("Ключ LLM и SMTP можно добавлять/менять в Render → Environment.")


if __name__ == "__main__":
    main()
