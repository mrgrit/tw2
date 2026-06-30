#!/usr/bin/env python3
"""sync_target_ip — el34 타깃/공격자 IP를 .env(단일 노브) → DB infras 로 전파.

배경: el34 인프라 IP는 배포마다 바뀐다(가변). 관제(gwanje/wazuh_probe)와 미션 IP 치환은
infras.vm_ip 를 읽으므로, IP가 바뀌면 .env 의 TUBEWAR_REF_TARGET_IP / TUBEWAR_REF_ATTACKER_IP
만 고치고 이 스크립트 한 번 실행하면 DB 의 등록 인프라 vm_ip 가 따라간다(하드코딩 없음).

사용:
    # .env 의 IP 를 DB 에 반영
    python3 scripts/sync_target_ip.py
    # 또는 인라인 지정(.env 도 함께 갱신)
    TUBEWAR_REF_TARGET_IP=192.168.0.80 python3 scripts/sync_target_ip.py --write-env

멱등. 읽기 우선순위: env > .env. el34 행(name='el34' 또는 port_map 에 'assessor')과
attacker 행(name='attacker')의 vm_ip 만 갱신한다."""
from __future__ import annotations
import argparse, os, re, sqlite3, sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_PATH = os.path.join(REPO, ".env")


def env_val(key: str) -> str | None:
    v = os.environ.get(key)
    if v:
        return v.strip()
    try:
        for ln in open(ENV_PATH):
            if ln.startswith(key + "="):
                return ln.split("=", 1)[1].strip()
    except FileNotFoundError:
        pass
    return None


def db_path() -> str:
    sys.path.insert(0, os.path.join(REPO, "apps/api"))
    try:
        from app.config import get_settings  # type: ignore
        m = re.search(r"sqlite[^/]*:/+(/.*\.sqlite3)", get_settings().database_url)
        if m:
            return m.group(1)
    except Exception:  # noqa: BLE001
        pass
    return os.path.join(REPO, ".data/tw2.sqlite3")


def upsert_env(key: str, val: str) -> None:
    lines, found = [], False
    if os.path.exists(ENV_PATH):
        lines = open(ENV_PATH).read().splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith(key + "="):
            lines[i] = f"{key}={val}"; found = True; break
    if not found:
        lines.append(f"{key}={val}")
    open(ENV_PATH, "w").write("\n".join(lines) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-env", action="store_true",
                    help="env 로 받은 값을 .env 에도 기록(인라인 변경 영구화)")
    a = ap.parse_args()

    target = env_val("TUBEWAR_REF_TARGET_IP")
    attacker = env_val("TUBEWAR_REF_ATTACKER_IP")
    if not target and not attacker:
        print("[sync] TUBEWAR_REF_TARGET_IP / TUBEWAR_REF_ATTACKER_IP 미설정 — .env 또는 env 로 지정하세요.")
        return 1

    if a.write_env:
        if target:
            upsert_env("TUBEWAR_REF_TARGET_IP", target)
        if attacker:
            upsert_env("TUBEWAR_REF_ATTACKER_IP", attacker)

    con = sqlite3.connect(db_path())
    total = 0
    if target:
        cur = con.execute(
            "UPDATE infras SET vm_ip=? WHERE name='el34' OR port_map LIKE '%assessor%'",
            (target,))
        total += cur.rowcount
        print(f"[sync] el34 vm_ip → {target} ({cur.rowcount} rows)")
    if attacker:
        cur = con.execute("UPDATE infras SET vm_ip=? WHERE name='attacker'", (attacker,))
        total += cur.rowcount
        print(f"[sync] attacker vm_ip → {attacker} ({cur.rowcount} rows)")
    con.commit()
    for r in con.execute("SELECT id, name, vm_ip FROM infras ORDER BY id"):
        print("   ", r)
    con.close()
    print(f"[sync] done — {total} rows. 관제는 다음 사이클부터 새 IP 로 붙는다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
