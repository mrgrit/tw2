"""공격자(attacker) VM 자동 설정 — 등록 시 SSH 로 `/etc/hosts` vhost 매핑 + 펜테스트 도구 보강.

el34 실습/배틀 콘텐츠는 자연 URL(`http://juice.el34.lab/…`) 로 공격하므로, 공격 VM 이
`*.el34.lab → 웹진입 IP` 를 resolve 해야 학생 명령이 그대로 동작한다. 이 서비스는
`kind=attacker` 인프라에 대해 **멱등 관리블록**으로 hosts 를 채우고, 없는 펜테스트 도구만
apt 로 best-effort 보강한다(도구가 이미 있거나 apt 불가여도 provision 실패로 보지 않음).

웹진입 IP 는 **하드코딩하지 않는다** — 같은 owner 의 target 인프라 `web_entry_ip`(폴백
`vm_ip`)에서 읽어 CLAUDE.md '단일 노브(IP 는 배포마다 가변)' 원칙을 지킨다.

sudo: att 등 공격 VM 계정이 무암호 sudo 면 `sudo -n`, 아니면 저장된 SSH 비번을 `sudo -S`
로 파이프(양쪽 모두 지원). hosts 갱신은 `sudo tee` 대신 temp파일+`sudo cp` 로 해
비번 stdin 과 파일 내용 stdin 이 충돌하지 않게 한다.
"""
from __future__ import annotations

import logging
import shlex
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..crypto import decrypt
from ..models import Infra

log = logging.getLogger(__name__)

# el34 실습/배틀 콘텐츠에 등장하는 vhost 전체 합집합 — 모두 웹진입 IP 로 매핑한다.
# 콘텐츠는 admin/juice 를, 인프라는 adminconsole/juiceshop 을 쓰기도 해 양쪽 alias 를 모두 포함.
# (합집합이라 실제보다 많아도 무해 — /etc/hosts 의 여분 이름은 그냥 resolve 될 뿐.)
EL34_VHOSTS: tuple[str, ...] = (
    "juice.el34.lab", "juiceshop.el34.lab", "dvwa.el34.lab", "neobank.el34.lab",
    "govportal.el34.lab", "mediforum.el34.lab", "adminconsole.el34.lab", "admin.el34.lab",
    "ai.el34.lab", "aicompanion.el34.lab", "siem.el34.lab", "portal.el34.lab",
    "bastion.el34.lab", "tunnel.el34.lab", "front.el34.lab", "exfil.el34.lab",
    "web.el34.lab", "dashboard.el34.lab", "assessor.el34.lab",
)
TOOLS: tuple[str, ...] = ("nmap", "curl", "hydra", "sqlmap", "nikto", "whatweb")

_MARKER = "tw2-el34-vhosts"


def build_script(web_entry: str) -> str:
    """공격 VM 에서 실행할 멱등 provision 셸 스크립트를 만든다.

    web_entry 는 검증된 IP 문자열만 들어온다(호출부에서 target 인프라의 등록 IP).
    비밀번호는 호출부에서 `SUDO_PW=<shlex.quote>` 를 앞에 붙여 넣는다.
    """
    vhosts = " ".join(EL34_VHOSTS)
    tools = " ".join(TOOLS)
    return f"""set -u
# 무암호 sudo 면 sudo -n, 아니면 저장 비번을 sudo -S 로. (stdin 안 쓰는 명령에만 사용)
PW_SUDO() {{ sudo -n "$@" 2>/dev/null || {{ echo "$SUDO_PW" | sudo -S "$@" 2>/dev/null; }}; }}
WEB_ENTRY="{web_entry}"
VHOSTS="{vhosts}"
# 1) /etc/hosts 관리블록 (멱등: 기존 마커 블록 삭제 후 재작성). tee 파이프 대신 temp+cp.
TMP="$(mktemp)"
sed '/# >>> {_MARKER} >>>/,/# <<< {_MARKER} <<</d' /etc/hosts > "$TMP" 2>/dev/null || cp /etc/hosts "$TMP"
printf '# >>> {_MARKER} >>>\\n%s %s\\n# <<< {_MARKER} <<<\\n' "$WEB_ENTRY" "$VHOSTS" >> "$TMP"
PW_SUDO cp "$TMP" /etc/hosts
rm -f "$TMP"
# 2) 펜테스트 도구 — 없는 것만 best-effort (apt 없거나 실패해도 무시)
NEED=""; for t in {tools}; do command -v "$t" >/dev/null 2>&1 || NEED="$NEED $t"; done
if [ -n "$NEED" ] && command -v apt-get >/dev/null 2>&1; then
  PW_SUDO apt-get update -qq && PW_SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y -qq $NEED >/dev/null 2>&1 || true
fi
# 3) 기계판독 리포트
echo TW2_PROVISION_BEGIN
for h in {vhosts}; do echo "host:$h=$(getent hosts "$h" | head -1 | awk '{{print $1}}')"; done
for t in {tools}; do command -v "$t" >/dev/null 2>&1 && echo "tool:$t=present" || echo "tool:$t=missing"; done
echo TW2_PROVISION_END
"""


async def resolve_web_entry(session: AsyncSession, infra: Infra) -> str:
    """공격 VM 이 vhost 를 걸어야 할 웹진입 IP. 하드코딩 대신 인프라 등록값에서 유도.

    우선순위: 이 attacker 인프라의 명시 web_entry_ip → 같은 owner 의 target 인프라
    web_entry_ip/vm_ip → (최후) 자기 vm_ip.
    """
    if infra.web_entry_ip:
        return infra.web_entry_ip
    target = await session.scalar(
        select(Infra)
        .where(Infra.owner_id == infra.owner_id, Infra.kind == "target")
        .order_by(Infra.id.desc())
    )
    if target:
        return target.web_entry_ip or target.vm_ip
    return infra.vm_ip


async def provision(session: AsyncSession, infra: Infra, *, timeout: int = 120) -> dict[str, Any]:
    """공격 VM 에 SSH 접속해 provision 스크립트를 실행하고 구조화된 결과를 반환.

    반환: {ok, web_entry, hosts{name:ip}, tools{name:state}, missing_tools[], summary}.
    실패해도 예외를 던지지 않고 ok=False + summary 로 리포트한다(등록 흐름 비차단).
    """
    import asyncssh

    web_entry = await resolve_web_entry(session, infra)
    try:
        pw = decrypt(infra.ssh_password_enc)
    except Exception:
        pw = infra.ssh_password_enc  # Phase1 평문 fallback
    port = int((infra.port_map or {}).get("ssh", 22))

    result: dict[str, Any] = {
        "ok": False, "web_entry": web_entry, "hosts": {}, "tools": {},
        "missing_tools": [], "summary": "",
    }
    script = "SUDO_PW=" + shlex.quote(pw) + "\n" + build_script(web_entry)
    try:
        async with asyncssh.connect(
            infra.vm_ip, port=port, username=infra.ssh_user, password=pw,
            known_hosts=None, connect_timeout=10,
        ) as conn:
            r = await conn.run(script, check=False, timeout=timeout)
        out = r.stdout or ""
    except Exception as e:  # noqa: BLE001 — SSH/네트워크 오류를 결과로 보고
        result["summary"] = f"SSH 실패({infra.ssh_user}@{infra.vm_ip}:{port}): {type(e).__name__}: {e}"
        return result

    body = out
    if "TW2_PROVISION_BEGIN" in out:
        body = out.split("TW2_PROVISION_BEGIN", 1)[1].split("TW2_PROVISION_END", 1)[0]
    for line in body.splitlines():
        line = line.strip()
        if line.startswith("host:") and "=" in line:
            k, v = line[len("host:"):].split("=", 1)
            result["hosts"][k] = v
        elif line.startswith("tool:") and "=" in line:
            k, v = line[len("tool:"):].split("=", 1)
            result["tools"][k] = v

    hosts_ok = bool(result["hosts"]) and all(v == web_entry for v in result["hosts"].values())
    missing = [k for k, v in result["tools"].items() if v != "present"]
    result["missing_tools"] = missing
    result["ok"] = hosts_ok
    n = len(result["hosts"])
    parts = [f"vhost {n}개 → {web_entry}"]
    if not hosts_ok:
        bad = [k for k, v in result["hosts"].items() if v != web_entry]
        parts.append(f"⚠ 매핑 실패 {len(bad)}개" + (f"({','.join(bad[:3])}…)" if bad else ""))
    parts.append("도구 완비" if not missing else f"도구 미설치 {len(missing)}개: {','.join(missing)}")
    result["summary"] = "; ".join(parts)
    return result
