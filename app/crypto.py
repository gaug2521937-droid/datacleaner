"""Шифрование персональных данных (Fernet / AES-128-CBC + HMAC-SHA256).

Ключ берётся из переменной окружения DATA_KEY. Если она не задана, для
локальной разработки создаётся файл .datacleaner.key (права 0600).
На сервере ВСЕГДА задавайте DATA_KEY через переменную окружения:
потеря ключа = потеря доступа к сохранённым данным (это by design).
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

DEFAULT_DEV_KEY_FILE = ".datacleaner.key"


class VaultError(RuntimeError):
    """Проблема с ключом шифрования."""


class Vault:
    """Обёртка над Fernet: JSON <-> зашифрованный blob."""

    def __init__(self, key: str | None = None, dev_key_path: str | Path = DEFAULT_DEV_KEY_FILE):
        raw = (key if key is not None else os.getenv("DATA_KEY", "")).strip()
        self.used_dev_key = False
        if not raw:
            raw = self._load_or_create_dev_key(Path(dev_key_path))
            self.used_dev_key = True
        try:
            self._fernet = Fernet(raw.encode("utf-8"))
        except Exception as exc:  # noqa: BLE001 — Fernet кидает разные типы
            raise VaultError(
                "DATA_KEY имеет неверный формат. Сгенерируйте ключ командой:\n"
                '  python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())"'
            ) from exc

    # ---------------------------------------------------------------- key load
    @staticmethod
    def _load_or_create_dev_key(path: Path) -> str:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        key = Fernet.generate_key().decode()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(key, encoding="utf-8")
        try:
            path.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
        except OSError:
            pass
        return key

    # --------------------------------------------------------------- interface
    def encrypt_json(self, payload: Any) -> bytes:
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return self._fernet.encrypt(data)

    def decrypt_json(self, blob: bytes | str | None) -> Any:
        if not blob:
            return None
        if isinstance(blob, str):
            blob = blob.encode("utf-8")
        try:
            return json.loads(self._fernet.decrypt(blob).decode("utf-8"))
        except InvalidToken as exc:
            raise VaultError(
                "Не удалось расшифровать данные: DATA_KEY не совпадает с тем, "
                "которым данные были зашифрованы."
            ) from exc

    def encrypt_text(self, text: str) -> bytes:
        return self._fernet.encrypt(text.encode("utf-8"))

    def decrypt_text(self, blob: bytes | None) -> str:
        if not blob:
            return ""
        if isinstance(blob, str):
            blob = blob.encode("utf-8")
        try:
            return self._fernet.decrypt(blob).decode("utf-8")
        except InvalidToken as exc:
            raise VaultError("Не удалось расшифровать текст: неверный DATA_KEY.") from exc
