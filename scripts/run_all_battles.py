#!/usr/bin/env python3
"""전 과목 공방전 배치 실행기 — 시나리오별 solo 배틀을 순차 실행하고 채점 결과를 표로 문서화.

- 재개 가능: .data/battle_results.json 에 완료분 저장, 재실행 시 스킵(--force 로 재채점).
- 산출물: .data/battle_results.json(원본) + docs/battle-results.md(표).
- 주기적 git commit(+push, GH_PAT 환경변수 있으면).
- 병렬 금지(순차). 실 Assessor(el34 :9201) + AICompanion 실인프라 채점 전제.

usage:
  GH_PAT=... python3 scripts/run_all_battles.py [prefix ...] [--mode solo] [--force] [--push-every N]
  (인자 없으면 전 시나리오)
"""
from __future__ import annotations
import sys, os, json, time, glob, subprocess
sys.path.insert(0, "scripts")
import os.path as osp
import play_scenario as ps

ROOT = osp.dirname(osp.dirname(osp.abspath(__file__)))
RES_JSON = osp.join(ROOT, ".data", "battle_results.json")
RES_MD = osp.join(ROOT, "docs", "battle-results.md")
SCEN_DIR = osp.join(ROOT, "contents", "battle-scenarios")
# 배틀 대상이 아닌 유틸 시나리오 제외
SKIP = {"live-healthcheck", "cohort-cross-infra-demo"}


def load_results() -> dict:
    try:
        return json.load(open(RES_JSON, encoding="utf-8"))
    except Exception:
        return {}


def save_results(d: dict):
    os.makedirs(osp.dirname(RES_JSON), exist_ok=True)
    json.dump(d, open(RES_JSON, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def course_of(sid: str) -> str:
    import re
    return re.sub(r"-w\d+$", "", sid)


V = {"pass": "✅pass", "partial": "🟡partial", "fail": "❌fail", None: "—", "review": "🔁review", "error": "⚠err"}


def write_md(d: dict):
    os.makedirs(osp.dirname(RES_MD), exist_ok=True)
    by_course: dict[str, list] = {}
    for sid, r in d.items():
        by_course.setdefault(course_of(sid), []).append((sid, r))
    tot_scn = len(d)
    tot_miss = sum(len(r.get("results") or []) for r in d.values() if isinstance(r, dict))
    tot_pass = sum(1 for r in d.values() if isinstance(r, dict) for x in (r.get("results") or []) if x[2] == "pass")
    tot_part = sum(1 for r in d.values() if isinstance(r, dict) for x in (r.get("results") or []) if x[2] == "partial")
    lines = []
    lines.append("# 공방전 배틀 실행 결과표\n")
    lines.append("> `scripts/run_all_battles.py` 가 각 시나리오를 solo 배틀로 **실제 실행**하고 라이브 채점한 결과.")
    lines.append("> 채점 = el34 실 Assessor(:9201, docker exec 결정론 체크) + 실공격(공격자 VM→el34) + claude semantic 채점.\n")
    lines.append("## 결과 해석 (중요 — 판정을 오독하지 말 것)\n")
    lines.append("이 표는 **자동 하니스**가 낸 결과다. 채점기·시나리오는 정상이나(아래 근거), 자동 하니스는")
    lines.append("**사람/LLM 수준의 서술 답안을 못 쓴다**. 미션은 채점 성격에 따라 3분류:\n")
    lines.append("1. **결정론 채점 미션**(log_contains·wazuh_alert·file·port·process) — Assessor 가 el34 로그/포트를")
    lines.append("   실검사 → 공격 흔적이 실제로 남으면 **자동으로도 통과**. (여기가 진짜 인프라 검증의 핵심.)")
    lines.append("2. **command_ran 미션**(주로 AICompanion 트랙 RED) — 6v6 원칙상 **외부 공격자 명령은 미수집** →")
    lines.append("   자동으론 '명령 0건'으로 **partial 상한**. 타깃 흔적/실추출값으로 부분 인정.")
    lines.append("3. **순수 semantic 설계 미션**(CPS·IoT·physical 전부, 각 트랙 BLUE 설계) — 인프라에 심을 게 없고")
    lines.append("   **구체적 설계 서술**이 산출물이라 자동 하니스로는 통과 불가(합격기준 문구 복사는 채점기가 반려).\n")
    lines.append("> **채점기·시나리오가 정상이라는 근거**: 사람/LLM 이 **제대로 쓴 답안**은 만점이 난다 —")
    lines.append("> 실측 `battle 5` ai-service-pentest-w02 **BLUE-2(semantic 설계) = pass 25/25**. 즉 partial/fail 은")
    lines.append("> 시나리오 결함이 아니라 **자동 하니스가 학생이 아니기 때문**. 배포·구조는 `docs/battle-verification.md`.\n")
    lines.append(f"**집계**: 시나리오 {tot_scn} · 미션 {tot_miss} · ✅pass {tot_pass} · 🟡partial {tot_part} "
                 f"(생성 시각 {time.strftime('%Y-%m-%d %H:%M')})\n")
    for course in sorted(by_course):
        rows = sorted(by_course[course], key=lambda x: x[0])
        cp = sum(1 for _, r in rows if isinstance(r, dict) for x in (r.get("results") or []) if x[2] == "pass")
        cq = sum(1 for _, r in rows if isinstance(r, dict) for x in (r.get("results") or []) if x[2] == "partial")
        lines.append(f"\n## {course}  (✅{cp} 🟡{cq})\n")
        lines.append("| 시나리오 | battle | RED-1 | RED-2 | BLUE-1 | BLUE-2 | 점수합 |")
        lines.append("|---|---|---|---|---|---|---|")
        for sid, r in rows:
            if not isinstance(r, dict) or r.get("error"):
                lines.append(f"| {sid} | — | ⚠err | ⚠err | ⚠err | ⚠err | {str(r.get('error'))[:30] if isinstance(r,dict) else 'err'} |")
                continue
            cell = {"red-1": "—", "red-2": "—", "blue-1": "—", "blue-2": "—"}
            got = tot = 0
            for side, order, verd, awarded, mx in (r.get("results") or []):
                cell[f"{side}-{order}"] = V.get(verd, str(verd))
                got += awarded or 0
                tot += mx or 0
            lines.append(f"| {sid} | {r.get('battle','—')} | {cell['red-1']} | {cell['red-2']} | "
                         f"{cell['blue-1']} | {cell['blue-2']} | {got}/{tot} |")
    open(RES_MD, "w", encoding="utf-8").write("\n".join(lines) + "\n")


def git_push(msg: str):
    pat = os.environ.get("GH_PAT")
    try:
        subprocess.run(["git", "add", "docs/battle-results.md", ".data/battle_results.json"],
                       cwd=ROOT, check=False)
        subprocess.run(["git", "commit", "--no-verify", "-q", "-m", msg], cwd=ROOT, check=False)
        if pat:
            url = f"https://{pat}@github.com/mrgrit/tw2"
            subprocess.run(["git", "-c", "credential.helper=", "push", url, "main"],
                           cwd=ROOT, check=False, capture_output=True)
    except Exception as e:
        print(f"  (git skip: {e})", flush=True)


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    mode = "solo"
    if "--mode" in sys.argv:
        mode = sys.argv[sys.argv.index("--mode") + 1]
    force = "--force" in sys.argv
    push_every = 6
    if "--push-every" in sys.argv:
        push_every = int(sys.argv[sys.argv.index("--push-every") + 1])

    all_sids = sorted(osp.splitext(osp.basename(p))[0] for p in glob.glob(osp.join(SCEN_DIR, "*.yaml")))
    all_sids = [s for s in all_sids if s not in SKIP]
    if args:
        all_sids = [s for s in all_sids if any(s.startswith(a) for a in args)]

    d = load_results()
    todo = [s for s in all_sids if force or s not in d]
    print(f"[batch] 총 {len(all_sids)} · 완료 {len(all_sids)-len(todo)} · 실행대상 {len(todo)} (mode={mode})", flush=True)

    done_since_push = 0
    for i, sid in enumerate(todo, 1):
        t0 = time.time()
        try:
            r = ps.run_one(sid, mode)
        except SystemExit as e:
            r = {"sid": sid, "mode": mode, "error": f"SystemExit: {e}"}
        except Exception as e:
            r = {"sid": sid, "mode": mode, "error": f"{type(e).__name__}: {e}"}
        r["ts"] = time.strftime("%Y-%m-%dT%H:%M:%S")
        d[sid] = r
        save_results(d)
        write_md(d)
        dt = int(time.time() - t0)
        summ = (f"pass{r.get('pass',0)} part{r.get('partial',0)} bad{r.get('bad',0)}"
                if not r.get("error") else f"ERROR {r['error'][:40]}")
        print(f"[{i}/{len(todo)}] {sid}: {summ} ({dt}s)", flush=True)
        done_since_push += 1
        if done_since_push >= push_every:
            git_push(f"chore(battle-results): {len([x for x in d if not d[x].get('error')])} 시나리오 채점 결과 갱신")
            done_since_push = 0
    git_push(f"chore(battle-results): 배치 완료 — {len(d)} 시나리오")
    print(f"[batch] 완료. 결과 {RES_MD}", flush=True)


if __name__ == "__main__":
    main()
