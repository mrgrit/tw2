"""학생 SSH 자격 등 비밀 데이터 envelope 암호화 (Fernet).

키 출처:
  1) env TUBEWAR_FERNET_KEY (운영 권장 — 외부 KMS/secret manager 가 주입)
  2) 없으면 .data/fernet.key 에 자동 생성 (dev only) + stderr 경고

암호문 형식:
  "fernet:" + base64-urlsafe-token   (마이그레이션 식별자 prefix)
"""
from __future__ import annotations
import logging
import os
import sys
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger(__name__)
PREFIX = "fernet:"
_KEY_FILE = Path(__file__).resolve().parents[3] / ".data" / "fernet.key"


def _load_key() -> bytes:
    env = os.environ.get("TUBEWAR_FERNET_KEY")
    if env:
        return env.encode() if isinstance(env, str) else env
    _KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    if _KEY_FILE.exists():
        return _KEY_FILE.read_bytes().strip()
    key = Fernet.generate_key()
    _KEY_FILE.write_bytes(key)
    _KEY_FILE.chmod(0o600)
    sys.stderr.write(
        f"[tubewar][WARN] no TUBEWAR_FERNET_KEY env — generated dev key at {_KEY_FILE}. "
        "Set TUBEWAR_FERNET_KEY in prod to avoid losing encrypted data.\n"
    )
    return key


_FERNET = Fernet(_load_key())


def encrypt(plain: str) -> str:
    if plain is None:
        return ""
    token = _FERNET.encrypt(plain.encode("utf-8")).decode("ascii")
    return PREFIX + token


def decrypt(ciphertext: str) -> str:
    if not ciphertext:
        return ""
    # 마이그레이션 단계 — prefix 없으면 평문 (Phase 1 잔여) 으로 본다
    if not ciphertext.startswith(PREFIX):
        return ciphertext
    raw = ciphertext[len(PREFIX):].encode("ascii")
    try:
        return _FERNET.decrypt(raw).decode("utf-8")
    except InvalidToken as e:
        raise ValueError(f"failed to decrypt secret: {e}") from e


def is_encrypted(value: str | None) -> bool:
    return bool(value) and value.startswith(PREFIX)
