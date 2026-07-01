#!/usr/bin/env python3
"""G6 — CC 오케스트레이션 러너 (시연용).

두 역할을 CC 가 실행하는 모습을 보여주는 스크립트. 시드(seed_demo_cohort)의 상수·헬퍼를
재사용하되, **증분(live 느낌)** 으로 데이터를 쌓고 **실제 분석 파이프라인**(lab_monitor·
feedback·reco)을 돌린다.

  setup            코호트+교수+학생+배틀 생성(활동 0 — 빈 상태로 시작)
  student [--tick]  '학생처럼' 1 틱 진행 — 일부 미션 통과/일부 병목 실패를 증분 추가
  analyze [--ai]    '분석가' 패스 — 진도 재계산·병목 피드백·통합 피드백·추천 직무 산출
  run  [--ticks N]  setup → student*N → analyze 를 한 번에(내레이션)

예)  .venv/bin/python scripts/orchestrate_demo.py run --ticks 3
     (촬영: setup 후 student 를 여러 번 눌러 대시보드가 채워지는 걸 보여주고 analyze)
"""
from __future__ import annotations
import os, sys, argparse, asyncio
import datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "api"))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from sqlalchemy import select, func  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    User, Cohort, CohortMembership, Battle, BattleParticipant,
    BattleEvent, ActivityEvent, StudentSubmission, StudentFeedback,
)
from app.services import lab_monitor, feedback as fb_svc, reco  # noqa: E402
import seed_demo_cohort as seed  # noqa: E402  (상수·purge·pick_scenario 재사용)

WEB = "192.168.0.161"; ATT = "192.168.0.202"


def target_done(profile: str, n_role: int) -> int:
    return {"fast": n_role, "mid": max(1, n_role - 1), "stuck": 1}[profile]


async def _ctx(s):
    """기존 데모 상태 로드 — (section, prof, [(user,profile,side,missions)], battle, scenario)."""
    section = await s.scalar(select(Cohort).where(Cohort.name == seed.SECTION_NAME))
    if not section:
        return None
    battle = await s.scalar(select(Battle).where(Battle.cohort_id == section.id)
                            .order_by(Battle.id.desc()).limit(1))
    if not battle:
        return None
    from app.models import Scenario
    sc = await s.get(Scenario, battle.scenario_id) if battle.scenario_id else None
    red = (sc.mission_red or {}).get("missions", []) or []
    blue = (sc.mission_blue or {}).get("missions", []) or []
    rows = []
    for i, (name, local, profile) in enumerate(seed.STUDENTS):
        u = await s.scalar(select(User).where(User.email == f"{local}@{seed.DEMO_DOMAIN}"))
        if not u:
            continue
        side = "red" if i % 2 == 0 else "blue"
        missions = (red if side == "red" else blue) or red or blue
        rows.append((u, profile, side, missions))
    prof = await s.scalar(select(User).where(User.email == f"{seed.INSTRUCTOR[1]}@{seed.DEMO_DOMAIN}"))
    return section, prof, rows, battle, sc


async def _done_count(s, battle_id, uid) -> int:
    """이 학생이 통과한 미션 수(BattleEvent report)."""
    evs = (await s.scalars(select(BattleEvent).where(
        BattleEvent.battle_id == battle_id, BattleEvent.actor_user_id == uid))).all()
    return sum(1 for e in evs if (e.detail or {}).get("report", {}).get("mission_order"))


async def _act_seq(s, uid) -> int:
    n = await s.scalar(select(func.count()).select_from(ActivityEvent)
                       .where(ActivityEvent.user_id == uid))
    return int(n or 0)


# ── setup ──────────────────────────────────────────
async def cmd_setup():
    async with SessionLocal() as s:
        await seed.purge(s)
        dept = Cohort(kind="department", name="정보보안학과", course_ref="demo:gwanje")
        s.add(dept); await s.flush()
        course = Cohort(kind="course", name="AI 서비스 모의해킹", parent_id=dept.id, course_ref="demo:gwanje")
        s.add(course); await s.flush()
        section = Cohort(kind="section", name=seed.SECTION_NAME, parent_id=course.id, course_ref="demo:gwanje")
        s.add(section); await s.flush()
        prof = User(email=f"{seed.INSTRUCTOR[1]}@{seed.DEMO_DOMAIN}", name=seed.INSTRUCTOR[0],
                    password_hash=hash_password(seed.DEMO_PW), role="admin")
        s.add(prof); await s.flush()
        s.add(CohortMembership(cohort_id=section.id, user_id=prof.id, role="instructor"))
        students = []
        for name, local, _ in seed.STUDENTS:
            u = User(email=f"{local}@{seed.DEMO_DOMAIN}", name=name,
                     password_hash=hash_password(seed.DEMO_PW), role="student")
            s.add(u); await s.flush()
            s.add(CohortMembership(cohort_id=section.id, user_id=u.id, role="student"))
            students.append(u)
        sc = await seed.pick_scenario(s)
        battle = Battle(scenario_id=sc.id, cohort_id=section.id, mode="ffa", status="active",
                        monitor="claude", started_at=seed.now_utc(), created_by=prof.id,
                        time_limit_sec=sc.time_limit_sec or 1800)
        s.add(battle); await s.flush()
        for i, u in enumerate(students):
            s.add(BattleParticipant(battle_id=battle.id, user_id=u.id,
                                    role="red" if i % 2 == 0 else "blue", score=0))
        await s.commit()
        print(f"[setup] 코호트 {seed.SECTION_NAME} · 학생 {len(students)} · 배틀 #{battle.id} (활동 0, 빈 상태)")
        print(f"[setup] 교수 {prof.email} / 학생 s1~s{len(students)}@{seed.DEMO_DOMAIN} (비번 {seed.DEMO_PW})")


# ── student (증분 1 틱) ────────────────────────────
async def cmd_student():
    async with SessionLocal() as s:
        ctx = await _ctx(s)
        if not ctx:
            print("[student] 데모 상태 없음 — 먼저 setup 실행"); return
        section, prof, rows, battle, sc = ctx
        advanced, retried = [], []
        for (u, profile, side, missions) in rows:
            n_role = len(missions) or 3
            done = await _done_count(s, battle.id, u.id)
            base = await _act_seq(s, u.id)
            tgt = target_done(profile, n_role)
            if done < tgt:
                order = done + 1
                m = missions[order - 1] if order - 1 < len(missions) else {"order": order, "points": 20}
                mx = int(m.get("points", 20))
                s.add(BattleEvent(battle_id=battle.id, actor_user_id=u.id, event_type="grade",
                                  target=WEB, description=f"{side.upper()}-{order} 통과",
                                  detail={"report": {"mission_side": side, "mission_order": order, "verdict": "pass"}},
                                  points=mx, ts=seed.now_utc()))
                s.add(StudentSubmission(
                    user_id=u.id, battle_id=battle.id, scenario_id=sc.id, cohort_id=section.id,
                    mission_side=side, mission_order=order,
                    event_type="exploit" if side == "red" else "defend", target=WEB,
                    what_i_did=seed.CMDS["exploit" if side == "red" else "blue"][0].format(ip=WEB, att=ATT, sid=u.id),
                    what_happened="200 OK — 자격 증명 노출 확인" if side == "red" else "차단 규칙 적용(403)",
                    description=f"{seed.mission_title(m)} 수행", claimed_points=mx,
                    mission_snapshot={"title": seed.mission_title(m), "instruction": (m.get("instruction") or "")[:300],
                                      "points": mx, "target_vm": m.get("target_vm", "web")},
                    grade_status="graded", verdict="pass", awarded_points=mx, max_points=mx,
                    feedback="기준 충족: 핵심 절차 수행·근거 명확.",
                    criteria_met=["절차 수행", "근거 명확"], criteria_missing=[],
                    grader_model="orch-demo", client_token=f"orch-{u.id}-{order}",
                    submitted_at=seed.now_utc(), graded_at=seed.now_utc()))
                pool = seed.CMDS["recon"] + (seed.CMDS["exploit"] if side == "red" else seed.CMDS["blue"])
                for k in range(3):
                    s.add(ActivityEvent(battle_id=battle.id, cohort_id=section.id, user_id=u.id,
                          kind="command", scenario_step=order, dedupe_key=f"orch-{u.id}-{base+k}",
                          payload={"cmd": pool[k % len(pool)].format(ip=WEB, att=ATT, sid=u.id), "rc": 0},
                          ts=seed.now_utc()))
                advanced.append(f"{u.name}→미션{order} 통과")
            elif profile == "stuck":
                # 목표 도달(1)했지만 다음 미션에서 계속 막힘 → 실패/경보 누적(병목 심화)
                for k in range(2):
                    s.add(ActivityEvent(battle_id=battle.id, cohort_id=section.id, user_id=u.id,
                          kind="command", scenario_step=2, dedupe_key=f"orch-{u.id}-{base+k}",
                          payload={"cmd": seed.CMDS["exploit"][k % len(seed.CMDS['exploit'])].format(ip=WEB, att=ATT, sid=u.id),
                                   "rc": 1, "stderr": "403 Forbidden — ModSecurity rule 942100 blocked"},
                          ts=seed.now_utc()))
                s.add(ActivityEvent(battle_id=battle.id, cohort_id=section.id, user_id=u.id,
                      kind="alert", scenario_step=2, dedupe_key=f"orch-{u.id}-{base+2}",
                      payload={"rule": seed.ALERTS[0].format(att=ATT)}, ts=seed.now_utc()))
                retried.append(f"{u.name}(미션2 재시도 실패·WAF 차단)")
        await s.commit()
        if advanced:
            print("[student] 진전: " + ", ".join(advanced))
        if retried:
            print("[student] 병목 지속: " + ", ".join(retried))
        if not advanced and not retried:
            print("[student] 전원 목표 도달 — 더 진행할 미션 없음")


# ── analyze (분석가 패스) ──────────────────────────
async def cmd_analyze(use_ai: bool):
    async with SessionLocal() as s:
        ctx = await _ctx(s)
        if not ctx:
            print("[analyze] 데모 상태 없음 — 먼저 setup/student 실행"); return
        section, prof, rows, battle, sc = ctx

        # 1) 진도/병목 재계산 (실제 lab_monitor)
        prog = await lab_monitor.snapshot_progress(s, battle.id)
        pmap = {p["user_id"]: p for p in prog}
        avg = round(sum(p["completion"] for p in prog) / len(prog)) if prog else 0
        stuck = [p for p in prog if p["stuck"]]
        print(f"[analyze] 진도 재계산 — 평균 {avg}% · 완주 {sum(1 for p in prog if p['completion']>=100)}명 · 병목 {len(stuck)}명")

        # 2) 병목 학생 — 건건 피드백 확보(없으면 결정론 1건)
        for p in stuck:
            u = await s.get(User, p["user_id"])
            has = await s.scalar(select(func.count()).select_from(StudentFeedback).where(
                StudentFeedback.user_id == u.id, StudentFeedback.trigger == "bottleneck"))
            if not has:
                flags = ", ".join((p["bottleneck_flags"] or {}).keys())
                s.add(StudentFeedback(
                    user_id=u.id, cohort_id=section.id, battle_id=battle.id,
                    scope="lab", trigger="bottleneck", delivered_to="both",
                    model="orch-rule", created_by=prof.id,
                    basis={"bottleneck": p["bottleneck_flags"], "completion": p["completion"]},
                    content_md=(f"### 병목 알림 — {u.name}\n\n미션 2에서 반복 실패(WAF 차단)가 감지됐습니다"
                                f"({flags}). 주석/인코딩 우회 또는 오류 기반 SQLi 를 시도하세요.")))
            print(f"[analyze]  ⚠ {u.name} 병목 — {list((p['bottleneck_flags'] or {}).keys())}")
        await s.commit()

        # 3) 통합 피드백(건건→통합) + 추천 직무
        print(f"[analyze] 통합 피드백 생성 (use_ai={use_ai}) …")
        for (u, profile, side, missions) in rows:
            # 기존 통합 제거 후 재생성(최신 데이터 반영)
            await s.execute(
                StudentFeedback.__table__.delete().where(
                    (StudentFeedback.user_id == u.id) & (StudentFeedback.scope == "periodic")))
            await s.commit()
            await fb_svc.integrate_feedback(s, user_id=u.id, cohort_id=section.id,
                                            battle_id=battle.id, created_by=prof.id, use_ai=use_ai)
            jobs = await reco.recommend_jobs(s, u.id)
            top = jobs[0] if jobs else None
            comp = pmap.get(u.id, {}).get("completion", 0)
            tag = "✅완주" if comp >= 100 else ("🚧병목" if pmap.get(u.id, {}).get("stuck") else "▶진행")
            job = f" → 추천 {top['title']}({top['match']}%)" if top else ""
            print(f"[analyze]  {tag} {u.name} {comp:>5}%{job}")
        print("[analyze] 완료 — 학생 대시보드/관제 대시보드에 반영됨")


async def cmd_run(ticks: int, use_ai: bool):
    await cmd_setup()
    for t in range(ticks):
        print(f"--- student tick {t+1}/{ticks} ---")
        await cmd_student()
    print("--- analyze ---")
    await cmd_analyze(use_ai)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("setup")
    sub.add_parser("student")
    a = sub.add_parser("analyze"); a.add_argument("--ai", action="store_true")
    r = sub.add_parser("run"); r.add_argument("--ticks", type=int, default=3); r.add_argument("--ai", action="store_true")
    args = ap.parse_args()
    if args.cmd == "setup":
        asyncio.run(cmd_setup())
    elif args.cmd == "student":
        asyncio.run(cmd_student())
    elif args.cmd == "analyze":
        asyncio.run(cmd_analyze(args.ai))
    elif args.cmd == "run":
        asyncio.run(cmd_run(args.ticks, args.ai))
