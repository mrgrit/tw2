#!/usr/bin/env python3
"""트레이닝 lab 라이브 테스트 — 각 step.answer 를 el34 호스트(.151)에서 base64 로 실행하고
verify.expect 문자열이 출력에 있는지 확인. 사용: python scripts/test_training_lab.py <lab.yaml> [el34_ip]
"""
import sys, base64, yaml
sys.path.insert(0, "scripts")
import vh

LAB = sys.argv[1]
IP = sys.argv[2] if len(sys.argv) > 2 else "192.168.0.151"

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
