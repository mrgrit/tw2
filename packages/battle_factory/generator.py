#!/usr/bin/env python3
"""CCC Battle Factory — CTI(CVE) 데이터로부터 battle YAML 시나리오 자동 생성.

로드맵 Phase 3: 3-Layer Agent에서 Master 역할.
- 입력: contents/threats/*/CVE-*.json  (또는 CLI로 단일 CVE ID)
- 출력: contents/labs/battle-auto/YYYY-MM-DD-<cve_id>.yaml
- LLM 우선순위:
    1) Anthropic Claude (ANTHROPIC_API_KEY 설정 시) — Master Agent 정규
    2) Ollama Manager 모델 (LLM_MANAGER_MODEL, default gpt-oss:120b) — on-prem fallback
- 생성된 battle은 Bastion 실증 검증 후 배포 권장 (--verify 옵션)

배포 이식성 (하드코딩 금지):
- LLM_BASE_URL / LLM_MANAGER_MODEL / ANTHROPIC_API_KEY 환경변수 사용
- 경로: __file__ 기준 상대 해석
- VM IP: CTI·시나리오에 표준 실습 대역 10.20.30.0/24 사용하되 .env override 가능

실행:
    python3 -m apps.battle-factory.generator --cve CVE-2026-XXXX
    python3 -m apps.battle-factory.generator --latest 3        # 최근 N건
    python3 -m apps.battle-factory.generator --day 2026-04-18  # 특정 일자 전체
    python3 -m apps.battle-factory.generator --cve CVE-X --verify  # Bastion 검증 1건
"""
from __future__ import annotations
import argparse
import json
import os
import pathlib
import re
import sys
import urllib.parse
import urllib.request
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[2]
THREATS_DIR = pathlib.Path(os.getenv("CTI_OUT_DIR", str(ROOT / "contents" / "threats")))
BATTLE_OUT = pathlib.Path(os.getenv("BATTLE_OUT_DIR", str(ROOT / "contents" / "labs" / "battle-auto")))
BATTLE_OUT.mkdir(parents=True, exist_ok=True)

OLLAMA_URL = os.getenv("LLM_BASE_URL", "http://192.168.0.105:11434")
MGR_MODEL = os.getenv("LLM_MANAGER_MODEL", "gpt-oss:120b")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
ANTHROPIC_MODEL = os.getenv("ANTHROPIC_MODEL", "claude-opus-4-7")

# 실습 대역 (deployment 시 override 가능)
VM_ATTACKER = os.getenv("VM_ATTACKER_INT", "10.20.30.201")
VM_WEB = os.getenv("VM_WEB_INT", "10.20.30.80")
VM_SIEM = os.getenv("VM_SIEM_INT", "10.20.30.100")
VM_SECU = os.getenv("VM_SECU_INT", "10.20.30.1")


# ── LLM 호출 추상화 ──────────────────────────────────────

def _chat_anthropic(prompt: str, system: str = "", timeout: int = 90) -> str | None:
    """Anthropic Claude 호출 (Master Agent)."""
    if not ANTHROPIC_API_KEY:
        return None
    payload = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system:
        payload["system"] = system
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode())
        # content: [{"type":"text","text":"..."}]
        blocks = data.get("content") or []
        for b in blocks:
            if b.get("type") == "text":
                return b.get("text", "")
        return ""
    except Exception as e:
        print(f"[anthropic 실패, fallback: {e}]", file=sys.stderr)
        return None


def _chat_ollama(prompt: str, system: str = "", timeout: int = 180) -> str:
    """Ollama Manager(gpt-oss:120b) 호출 — fallback. JSON 형식 강제."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat",
        data=json.dumps({
            "model": MGR_MODEL,
            "messages": messages,
            "stream": False,
            "format": "json",   # Ollama JSON 모드 — 유효 JSON 보장
            "options": {"temperature": 0.3, "num_predict": 4000},
        }).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode())
        return (d.get("message") or {}).get("content", "")
    except Exception as e:
        return f"[ollama 실패: {e}]"


def llm_chat(prompt: str, system: str = "") -> tuple[str, str]:
    """Master(Claude) 우선, 실패 시 Manager(Ollama) fallback. (content, source) 반환."""
    if ANTHROPIC_API_KEY:
        text = _chat_anthropic(prompt, system)
        if text:
            return text, f"anthropic:{ANTHROPIC_MODEL}"
    return _chat_ollama(prompt, system), f"ollama:{MGR_MODEL}"


# ── Battle YAML 생성 프롬프트 ────────────────────────────

# f-string 사용 불가 (JSON 스키마의 { 중괄호가 충돌). 런타임 구성.
_INFRA_BLOCK = (
    "## 인프라 (실습 대역)\n"
    f"- attacker VM ({VM_ATTACKER}): nmap, hydra, sqlmap, nikto, curl, metasploit\n"
    f"- web VM ({VM_WEB}): Apache, ModSecurity, JuiceShop:3000, DVWA:8080, Docker\n"
    f"- secu VM ({VM_SECU}): nftables, Suricata\n"
    f"- siem VM ({VM_SIEM}): Wazuh Manager, Suricata 룰\n"
)

_SCHEMA_JSON = """스키마:
{
  "lab_id": "battle-auto-<cve>",
  "title": "...",
  "version": "ai",
  "course": "battle-auto",
  "week": 0,
  "description": "...",
  "difficulty": "easy|medium|hard",
  "duration_minutes": 120,
  "objectives": ["...", "..."],
  "prerequisites": ["..."],
  "infra_requirements": ["..."],
  "pass_threshold": 0.5,
  "steps": [
    {
      "order": 1,
      "instruction": "...",
      "hint": "...",
      "category": "recon|scan|exploit|detect|analyze|contain|remediate",
      "points": 10,
      "answer": "프롬프트: ...",
      "answer_detail": "...",
      "verify": {
        "type": "output_contains",
        "expect": "...",
        "field": "stdout",
        "semantic": {
          "intent": "한 줄 요약 — 이 step 의 목적 + 구체 명령/옵션/임계치/MITRE ID 포함",
          "success_criteria": ["실행 여부 기준", "결과 형태 기준", "개념 언급 기준"],
          "acceptable_methods": ["제시 명령", "동등 대체 도구1", "동등 대체 도구2"],
          "negative_signs": ["흔한 실수1", "흔한 실수2", "부족한 응답 패턴"]
        }
      },
      "target_vm": "attacker|web|secu|siem",
      "script": "shell 명령 한 줄",
      "risk_level": "low|medium|high",
      "bastion_prompt": "실행형 지시 (attacker VM에서 ...)"
    }
  ]
}
"""

SYSTEM_PROMPT = (
    "너는 CCC(Cyber Combat Commander) 사이버 침공대응 훈련 플랫폼의 battle 시나리오 설계자다.\n"
    "주어진 CVE 정보로부터 학생이 Red/Blue 팀으로 나눠 수행하는 실전 battle 시나리오를 생성한다.\n\n"
    + _INFRA_BLOCK + "\n"
    "## 규칙\n"
    "- category: RED 단계(recon, scan, exploit, lateral, persistence) / BLUE 단계(detect, analyze, contain, remediate)\n"
    "- verify.type=output_contains 권장, expect는 실제 명령 출력에 나올 구체 키워드 (예: '200 OK', 'alert', 'ESTABLISHED')\n"
    "- **verify.semantic 은 필수** (LLM 채점 근거) — intent 1줄, success_criteria 3개+, acceptable_methods 3~4개, negative_signs 3개\n"
    "- semantic.intent 는 step 의 instruction 을 복붙하지 말고 '왜/무엇을/어떻게' 한 줄로 요약 + MITRE ATT&CK ID/CVE/도구명/임계치 포함\n"
    "- success_criteria 는 '실행된 증거' + '결과 키워드' + '개념 언급' 3축으로 작성\n"
    "- acceptable_methods 는 동일 목적의 대체 도구/명령 (학생이 다른 방법 써도 pass 인정 근거)\n"
    "- negative_signs 는 흔한 오답/얕은 응답 패턴\n"
    "- target_vm: attacker/web/secu/siem\n"
    "- risk_level: low/medium/high\n"
    "- bastion_prompt: 실행형 지시문 (QA형 '~설명해줘' 금지)\n"
    "- 총 10~14 steps, RED 6~8 + BLUE 4~6 균형\n"
    "- 실제 실행 가능한 shell 명령, 파괴적 명령(rm -rf, shutdown 등) 금지\n\n"
    "## 출력\n"
    "**정확한 JSON만 출력** (코드블록·주석·설명 금지).\n\n"
    + _SCHEMA_JSON
)


def build_prompt(cve: dict) -> str:
    courses = cve.get("courses", [])
    return (
        f"## CVE 정보\n"
        f"- ID: {cve.get('id','')}\n"
        f"- Severity: {cve.get('severity','?')} (CVSS {cve.get('cvss_score','?')})\n"
        f"- Published: {cve.get('published','')[:10]}\n"
        f"- 한글 요약: {cve.get('summary','')}\n"
        f"- 영향: {cve.get('impact','')}\n"
        f"- 공격 벡터: {cve.get('attack_vector','')}\n"
        f"- 태그: {', '.join(cve.get('tags', []))}\n"
        f"- 관련 과목 힌트: {', '.join(courses) if courses else '-'}\n\n"
        f"위 CVE를 재현 가능한 battle 시나리오로 구성하라. "
        f"Red는 {cve.get('id','CVE-?')}와 유사한 공격 벡터를 시뮬레이션하고, "
        f"Blue는 탐지·분석·차단·복구를 수행한다.\n\n"
        f"YAML 시나리오 출력:"
    )


def extract_json(text: str) -> dict | None:
    """LLM 출력에서 JSON 추출. Ollama format=json이면 바로 파싱, 아니면 첫 {...} 블록."""
    text = text.strip()
    # 직접 파싱 시도
    try:
        return json.loads(text)
    except Exception:
        pass
    # 코드블록 제거
    m = re.search(r"```(?:json)?\s*\n([\s\S]*?)```", text)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # 첫 {...} 구간
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def validate_battle(data: dict) -> tuple[bool, str]:
    """battle data 스키마 검증."""
    if not isinstance(data, dict):
        return False, "최상위가 dict 아님"
    required = ["lab_id", "title", "steps"]
    missing = [k for k in required if k not in data]
    if missing:
        return False, f"필수 필드 누락: {missing}"
    steps = data.get("steps") or []
    if not isinstance(steps, list) or len(steps) < 5:
        return False, f"steps 최소 5개 필요 (현재 {len(steps)})"
    for i, s in enumerate(steps):
        for k in ("order", "instruction", "category"):
            if k not in s:
                return False, f"step {i+1} 필수 필드 누락: {k}"
    return True, f"OK ({len(steps)} steps)"


# ── CVE 로드 ────────────────────────────────────────────

def load_cve(cve_id: str) -> dict | None:
    for p in THREATS_DIR.glob(f"*/{cve_id}.json"):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
    return None


def load_latest(n: int = 3) -> list[dict]:
    items = []
    for p in THREATS_DIR.glob("*/CVE-*.json"):
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            doc["_path"] = str(p)
            items.append(doc)
        except Exception:
            continue
    # severity + cvss 정렬
    sev = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3, "UNKNOWN": 4}
    items.sort(key=lambda x: (sev.get(x.get("severity", "UNKNOWN"), 9), -float(x.get("cvss_score") or 0)))
    return items[:n]


def load_day(day: str) -> list[dict]:
    day_dir = THREATS_DIR / day
    if not day_dir.exists():
        return []
    items = []
    for p in sorted(day_dir.glob("CVE-*.json")):
        try:
            items.append(json.loads(p.read_text(encoding="utf-8")))
        except Exception:
            continue
    return items


# ── 생성 파이프라인 ─────────────────────────────────────

def generate_battle(cve: dict, max_retry: int = 2) -> dict:
    """CVE 1건 → battle JSON 생성 → YAML 변환 저장. 반환: {ok, path, source, message}"""
    import yaml as _y
    cve_id = cve.get("id", "CVE-UNKNOWN")
    prompt = build_prompt(cve)
    source = ""
    msg = ""
    for attempt in range(1, max_retry + 1):
        text, source = llm_chat(prompt, SYSTEM_PROMPT)
        data = extract_json(text)
        if not data:
            msg = "JSON 파싱 실패"
            print(f"[{cve_id}] attempt {attempt} {msg} → 재시도", file=sys.stderr)
            continue
        ok, msg = validate_battle(data)
        if ok:
            day = cve.get("published", "")[:10] or "2026-01-01"
            fname = f"{day}-{cve_id.lower()}.yaml"
            out_path = BATTLE_OUT / fname
            yaml_content = _y.safe_dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False)
            out_path.write_text(yaml_content, encoding="utf-8")
            return {"ok": True, "path": str(out_path), "source": source, "message": msg, "cve": cve_id}
        print(f"[{cve_id}] attempt {attempt} {msg} → 재시도", file=sys.stderr)
    return {"ok": False, "source": source, "message": msg, "cve": cve_id}


# ── Bastion 검증 (옵션) ────────────────────────────────

def verify_with_bastion(battle_path: str, max_steps: int = 3) -> dict:
    """생성된 battle의 처음 N steps를 Bastion으로 실증. 배포 이식성을 위해 Bastion URL env."""
    bastion_url = os.getenv("BASTION_URL", "http://192.168.0.103:8003")
    try:
        import yaml as _y
        data = _y.safe_load(pathlib.Path(battle_path).read_text(encoding="utf-8"))
    except Exception as e:
        return {"verified": False, "error": str(e)}
    results = []
    for step in (data.get("steps") or [])[:max_steps]:
        prompt = step.get("bastion_prompt") or step.get("instruction") or ""
        if not prompt:
            continue
        try:
            req = urllib.request.Request(
                f"{bastion_url}/chat",
                data=json.dumps({
                    "message": prompt, "auto_approve": True, "stream": False,
                    "course": "battle-auto", "lab_id": data.get("lab_id", ""),
                    "step_order": step.get("order", 0),
                }).encode(),
                headers={"Content-Type": "application/json"}, method="POST",
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read().decode()
            events = json.loads(body).get("events", []) if body.strip().startswith("{") else []
            executed = any(e.get("event") == "skill_start" for e in events)
            results.append({"order": step.get("order"), "executed": executed})
        except Exception as e:
            results.append({"order": step.get("order"), "error": str(e)[:100]})
    exec_rate = sum(1 for r in results if r.get("executed")) / max(len(results), 1)
    return {"verified": True, "sample_size": len(results), "exec_rate": exec_rate, "details": results}


# ── CLI ────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--cve", help="단일 CVE ID (예: CVE-2026-0894)")
    g.add_argument("--latest", type=int, help="severity 상위 N건")
    g.add_argument("--day", help="특정 일자 YYYY-MM-DD 전체")
    ap.add_argument("--verify", action="store_true", help="생성 후 Bastion에서 실증 (첫 3 steps)")
    args = ap.parse_args()

    targets: list[dict] = []
    if args.cve:
        doc = load_cve(args.cve)
        if not doc:
            print(f"[ERR] CVE 파일 없음: {args.cve}. 먼저 CTI collector 실행", file=sys.stderr)
            sys.exit(1)
        targets = [doc]
    elif args.latest:
        targets = load_latest(args.latest)
    elif args.day:
        targets = load_day(args.day)

    if not targets:
        print("[ERR] 생성 대상 CVE 없음", file=sys.stderr)
        sys.exit(1)

    print(f"[battle-factory] {len(targets)}건 생성 시작 (LLM: "
          f"{'Anthropic Master' if ANTHROPIC_API_KEY else 'Ollama Manager(' + MGR_MODEL + ')'})")
    report = []
    for cve in targets:
        print(f"  → {cve['id']} ...", end=" ", flush=True)
        res = generate_battle(cve)
        if res["ok"]:
            print(f"OK {pathlib.Path(res['path']).name} [{res['source']}] {res['message']}")
            if args.verify:
                v = verify_with_bastion(res["path"])
                res["verify"] = v
                print(f"    [verify] exec_rate={v.get('exec_rate',0)*100:.0f}% · {v.get('sample_size',0)} samples")
        else:
            print(f"FAIL {res['message']}")
        report.append(res)

    ok_count = sum(1 for r in report if r["ok"])
    print(f"\n결과: {ok_count}/{len(report)} 성공")


if __name__ == "__main__":
    main()
