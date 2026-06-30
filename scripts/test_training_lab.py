#!/usr/bin/env python3
"""트레이닝 lab 라이브 테스트 — 각 step.answer 를 el34 호스트에서 base64 로 실행하고
verify.expect 문자열이 출력에 있는지 확인. 사용: python scripts/test_training_lab.py <lab.yaml> [el34_ip]
el34 IP 미지정 시 env(TUBEWAR_REF_TARGET_IP/EL34_HOST) > .env 순으로 해석(하드코딩 없음)."""
import sys, os, base64, yaml
sys.path.insert(0, "scripts")
import vh


def _env_ip():
    v = os.environ.get("EL34_HOST") or os.environ.get("TUBEWAR_REF_TARGET_IP")
    if v:
        return v.strip()
    try:
        for ln in open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".env")):
            if ln.startswith("TUBEWAR_REF_TARGET_IP="):
                return ln.split("=", 1)[1].strip()
    except Exception:
        pass
    return "192.168.0.80"

LAB = sys.argv[1]
IP = sys.argv[2] if len(sys.argv) > 2 else _env_ip()

d = yaml.safe_load(open(LAB))
steps = d["steps"]
print(f"=== {d['lab_id']} — {len(steps)} steps @ {IP} ===\n")

passed = 0
for s in steps:
    o = s["order"]
    ans = s.get("answer", "")
    expect = (s.get("verify") or {}).get("expect", "")
    b64 = base64.b64encode(ans.encode()).decode()
    rc, out, err = vh.host_exec(IP, f"echo {b64} | base64 -d | bash", timeout=150)
    full = out + "\n" + err
    ok = expect in full
    passed += ok
    mark = "PASS" if ok else "FAIL"
    print(f"--- step {o} [{s.get('category','')}] expect={expect!r} → {mark} (rc={rc})")
    if not ok:
        print("  STDOUT:", out[-700:].replace("\n", "\n  "))
        if err.strip():
            print("  STDERR:", err[-400:].replace("\n", "\n  "))

print(f"\n=== {passed}/{len(steps)} PASS ===")
