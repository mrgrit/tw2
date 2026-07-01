#!/usr/bin/env python3
"""Phase 0 — AI 관제 시연용 데이터 시드.

기획: docs/initiatives/gwanje-demo.md (G1). 관제/피드백 대시보드가 비어 보이지 않도록
현실적인 **코호트 + 학생 + 배틀 + 활동/진도/제출/피드백**을 심는다.

- 멱등: `@demo.tw2` 학생·데모 코호트를 매 실행 시 먼저 지우고 다시 만든다(안전 재실행).
- 실 el34 실행 없음(순수 시드 목업). Scene 1(실습)만 실제로 돌릴지는 촬영 때 결정(§8).
- 학생 편차: fast(완주) / mid(진행중) / stuck(특정 미션 병목)로 진도·병목이 대시보드에 드러나게.

사용:  .venv/bin/python scripts/seed_demo_cohort.py
지움:  .venv/bin/python scripts/seed_demo_cohort.py --purge
"""
from __future__ import annotations
import os, sys, json, random, asyncio, argparse
import datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "apps", "api"))

from sqlalchemy import select, delete  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.security import hash_password  # noqa: E402
from app.models import (  # noqa: E402
    User, Cohort, CohortMembership, Scenario, Battle, BattleParticipant,
    BattleEvent, ActivityEvent, ProgressSnapshot, StudentSubmission, StudentFeedback,
)

DEMO_DOMAIN = "demo.ac.kr"  # 유효 TLD(.kr) — 로그인 EmailStr 검증 통과용
DEMO_PW = "demo1234"
SECTION_NAME = "2026-1 관제시연 A반"
random.seed(1337)


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


STUDENTS = [
    # (name, local, profile)  profile: fast | mid | stuck
    ("김민수", "s1", "fast"),
    ("이서연", "s2", "fast"),
    ("박지훈", "s3", "mid"),
    ("최유진", "s4", "mid"),
    ("정하늘", "s5", "mid"),
    ("강도현", "s6", "stuck"),
    ("윤예은", "s7", "stuck"),
]
INSTRUCTOR = ("박교수", "prof")

CMDS = {
    "recon": ["nmap -sS -T2 -Pn -p80,443 {ip}", "whatweb http://{ip}", "gobuster dir -u http://{ip} -w common.txt"],
    "exploit": ["curl -s -A 'demo-{sid}' 'http://{ip}/vulnerabilities/sqli/?id=1%27+UNION+SELECT+user,password+FROM+users--+'",
                "sqlmap -u 'http://{ip}/?id=1' --batch --dump", "curl -s 'http://{ip}/login' -d 'user=admin&pass=admin'"],
    "blue": ["tail -f /var/log/apache2/access.log", "grep -i union /var/log/modsec_audit.log",
             "iptables -A INPUT -s {att} -j DROP", "wazuh-control status"],
}
ALERTS = ["ModSecurity: SQL Injection Attack Detected (rule 942100)",
          "Suricata: ET WEB_SPECIFIC_APPS SQL Injection",
          "Wazuh: Multiple authentication failures from {att}"]


def mission_title(m: dict) -> str:
    instr = (m.get("instruction") or "").strip()
    for line in instr.splitlines():
        line = line.strip()
        if line.startswith("#"):
            return line.lstrip("#").strip()[:120]
    return f"미션 {m.get('order','?')}"


async def purge(s):
    """데모 데이터 제거 (의존성 역순)."""
    uids = [u.id for u in (await s.scalars(
        select(User).where(User.email.like(f"%@{DEMO_DOMAIN}")))).all()]
    cids = [c.id for c in (await s.scalars(
        select(Cohort).where(Cohort.name == SECTION_NAME))).all()]
    # 데모 코호트 서브트리 부모까지 (department/course) — course_ref 마커로 잡는다
    demo_cohorts = [c.id for c in (await s.scalars(
        select(Cohort).where(Cohort.course_ref == "demo:gwanje"))).all()]
    cids = list(set(cids + demo_cohorts))
    bids = [b.id for b in (await s.scalars(
        select(Battle).where(Battle.cohort_id.in_(cids or [-1])))).all()]
    for model, cond in [
        (StudentFeedback, StudentFeedback.user_id.in_(uids or [-1])),
        (StudentSubmission, StudentSubmission.user_id.in_(uids or [-1])),
        (ProgressSnapshot, ProgressSnapshot.user_id.in_(uids or [-1])),
        (ActivityEvent, ActivityEvent.user_id.in_(uids or [-1])),
        (BattleEvent, BattleEvent.battle_id.in_(bids or [-1])),
        (BattleParticipant, BattleParticipant.user_id.in_(uids or [-1])),
        (Battle, Battle.id.in_(bids or [-1])),
        (CohortMembership, CohortMembership.user_id.in_(uids or [-1])),
        (User, User.id.in_(uids or [-1])),
    ]:
        await s.execute(delete(model).where(cond))
    # 코호트는 트리(cascade) — 최상위 department 부터 지우면 하위 자동 삭제
    for cid in cids:
        obj = await s.get(Cohort, cid)
        if obj is not None:
            await s.delete(obj)
    await s.commit()


async def pick_scenario(s) -> Scenario:
    """웹 공방전 성격의 시나리오 우선 선택(없으면 첫 시나리오)."""
    for cond in [Scenario.category == "secuops-easy",
                 Scenario.title.like("%웹%"), Scenario.title.like("%SQL%")]:
        sc = await s.scalar(select(Scenario).where(cond).order_by(Scenario.id).limit(1))
        if sc:
            return sc
    return await s.scalar(select(Scenario).order_by(Scenario.id).limit(1))


async def main(purge_only: bool = False):
    async with SessionLocal() as s:
        await purge(s)
        if purge_only:
            print("데모 데이터 제거 완료.")
            return

        # ── 코호트 트리: 학과 → 교과목 → 분반 ──
        dept = Cohort(kind="department", name="정보보안학과", course_ref="demo:gwanje")
        s.add(dept); await s.flush()
        course = Cohort(kind="course", name="AI 서비스 모의해킹", parent_id=dept.id,
                        course_ref="demo:gwanje")
        s.add(course); await s.flush()
        section = Cohort(kind="section", name=SECTION_NAME, parent_id=course.id,
                         course_ref="demo:gwanje")
        s.add(section); await s.flush()

        # ── 교수 + 학생 + 멤버십 ──
        prof = User(email=f"{INSTRUCTOR[1]}@{DEMO_DOMAIN}", name=INSTRUCTOR[0],
                    password_hash=hash_password(DEMO_PW), role="student")  # 강사 UI는 멤버십 role로
        s.add(prof); await s.flush()
        s.add(CohortMembership(cohort_id=section.id, user_id=prof.id, role="instructor"))

        students: list[User] = []
        for name, local, _ in STUDENTS:
            u = User(email=f"{local}@{DEMO_DOMAIN}", name=name,
                     password_hash=hash_password(DEMO_PW), role="student")
            s.add(u); await s.flush()
            s.add(CohortMembership(cohort_id=section.id, user_id=u.id, role="student"))
            students.append(u)

        # ── 시나리오 + 배틀 ──
        sc = await pick_scenario(s)
        red = (sc.mission_red or {}).get("missions", []) or []
        blue = (sc.mission_blue or {}).get("missions", []) or []
        steps_total = max(len(red), len(blue), 3)
        started = now_utc() - dt.timedelta(hours=2)
        battle = Battle(scenario_id=sc.id, cohort_id=section.id, mode="ffa",
                        status="active", monitor="claude", started_at=started,
                        created_by=prof.id, time_limit_sec=sc.time_limit_sec or 1800)
        s.add(battle); await s.flush()

        att_ip = "192.168.0.202"; web_ip = "192.168.0.161"
        counts = {"activity": 0, "progress": 0, "submissions": 0, "feedback": 0}

        for i, u in enumerate(students):
            profile = STUDENTS[i][2]
            side = "red" if i % 2 == 0 else "blue"
            missions = red if side == "red" else blue
            if not missions:
                missions = red or blue
            n_role = len(missions) or 3
            s.add(BattleParticipant(battle_id=battle.id, user_id=u.id, role=side, score=0))

            # 프로필별 진도(완료 미션 수)
            done = {"fast": n_role, "mid": max(1, n_role - 1), "stuck": 1}[profile]
            comp = int(round(100.0 * done / n_role))

            # ── 진도의 권위 소스: BattleEvent (points>0 + report.side/order) ──
            #    lab_monitor.compute_progress 가 이걸로 steps_done 을 센다.
            score = 0
            for order in range(1, done + 1):
                m = missions[order - 1] if order - 1 < len(missions) else {"order": order, "points": 20}
                mx = int(m.get("points", 20)); score += mx
                s.add(BattleEvent(
                    battle_id=battle.id, actor_user_id=u.id, event_type="grade",
                    target=web_ip, description=f"{side.upper()}-{order} 통과",
                    detail={"report": {"mission_side": side, "mission_order": order, "verdict": "pass"}},
                    points=mx, ts=started + dt.timedelta(minutes=18 * order + 2)))

            # ── 활동(ActivityEvent): 병목 신호를 프로필별로 결정론 생성 ──
            #    stuck 만 실패명령>=3 + alert/log>=5 로 bottleneck flag 유발.
            acts: list[tuple[str, dict, int]] = []   # (kind, payload, step)
            succ = CMDS["blue"] if side == "blue" else (CMDS["recon"] + CMDS["exploit"])
            if profile == "fast":
                for k in range(20):
                    acts.append(("command", {"cmd": succ[k % len(succ)].format(ip=web_ip, att=att_ip, sid=u.id), "rc": 0},
                                 min(n_role, 1 + k // max(1, 20 // n_role))))
                acts += [("alert", {"rule": ALERTS[0].format(att=att_ip)}, 2),
                         ("log", {"line": f"GET / 200 UA=demo-{u.id}"}, 3)]
            elif profile == "mid":
                for k in range(12):
                    acts.append(("command", {"cmd": succ[k % len(succ)].format(ip=web_ip, att=att_ip, sid=u.id), "rc": 0},
                                 min(n_role, 1 + k // 5)))
                acts += [("alert", {"rule": ALERTS[1].format(att=att_ip)}, 2),
                         ("log", {"line": f"GET / 200 UA=demo-{u.id}"}, 2)]
            else:  # stuck — 병목
                for k in range(4):  # step1 성공
                    acts.append(("command", {"cmd": CMDS["recon"][k % len(CMDS["recon"])].format(ip=web_ip, att=att_ip, sid=u.id), "rc": 0}, 1))
                for k in range(5):  # step2 반복 실패(WAF 차단)
                    acts.append(("command", {"cmd": CMDS["exploit"][k % len(CMDS["exploit"])].format(ip=web_ip, att=att_ip, sid=u.id),
                                             "rc": 1, "stderr": "403 Forbidden — ModSecurity rule 942100 blocked"}, 2))
                for k in range(6):  # 경보/로그 누적
                    acts.append(("alert" if k % 2 == 0 else "log",
                                 {"rule": ALERTS[k % len(ALERTS)].format(att=att_ip)} if k % 2 == 0
                                 else {"line": f"POST /login 403 UA=demo-{u.id}"}, 2))
            for k, (kind, payload, step) in enumerate(acts):
                t = started + dt.timedelta(minutes=int(k * (110 / max(1, len(acts)))))
                s.add(ActivityEvent(
                    battle_id=battle.id, cohort_id=section.id, user_id=u.id,
                    kind=kind, scenario_step=step, dedupe_key=f"demo-{u.id}-{k}",
                    payload=payload, ts=t))
                counts["activity"] += 1

            # ── 진도 스냅샷 (표현용 — 라이브 엔드포인트는 재계산하지만 일부 뷰가 참조) ──
            snap_flags = {"repeated_failed_commands": 5, "error_alerts": 6} if profile == "stuck" else {}
            s.add(ProgressSnapshot(
                battle_id=battle.id, cohort_id=section.id, user_id=u.id,
                completion=int(comp), steps_done=int(done), steps_total=int(n_role),
                bottleneck_flags=snap_flags, ts=now_utc()))
            counts["progress"] += 1
            steps_total = n_role  # 아래 피드백 표기용

            # ── 제출/채점 (완료 미션 수만큼) ──
            for order in range(1, done + 1):
                m = missions[order - 1] if order - 1 < len(missions) else {"order": order, "points": 20}
                mx = int(m.get("points", 20))
                if profile == "fast":
                    verdict = "pass"; awarded = mx
                elif profile == "mid":
                    verdict = "pass" if order < done else "partial"
                    awarded = mx if verdict == "pass" else int(mx * 0.6)
                else:
                    verdict = "pass"; awarded = mx  # stuck 은 done=1 만 통과
                s.add(StudentSubmission(
                    user_id=u.id, battle_id=battle.id, scenario_id=sc.id, cohort_id=section.id,
                    mission_side=side, mission_order=order,
                    event_type="exploit" if side == "red" else "defend",
                    target=web_ip,
                    what_i_did=random.choice(CMDS["exploit" if side == "red" else "blue"]).format(ip=web_ip, att=att_ip, sid=u.id),
                    what_happened="200 OK — 응답에서 자격 증명 노출 확인" if side == "red" else "차단 규칙 적용, 후속 요청 403",
                    description=f"{mission_title(m)} 수행 및 근거 정리",
                    claimed_points=mx,
                    mission_snapshot={"title": mission_title(m), "instruction": (m.get("instruction") or "")[:400],
                                      "points": mx, "target_vm": m.get("target_vm", "web")},
                    grade_status="graded", verdict=verdict,
                    awarded_points=awarded, max_points=mx,
                    feedback=f"기준 충족: 핵심 절차 수행. {'부분 감점: 근거 서술 미흡.' if verdict=='partial' else '정확한 태깅/근거.'}",
                    criteria_met=["절차 수행", "산출물 제출"] + (["근거 명확"] if verdict == "pass" else []),
                    criteria_missing=[] if verdict == "pass" else ["근거 서술 보강"],
                    grader_model="seed-demo",
                    client_token=f"demo-{u.id}-{order}",
                    submitted_at=started + dt.timedelta(minutes=20 * order),
                    graded_at=started + dt.timedelta(minutes=20 * order + 2)))
                counts["submissions"] += 1

            # ── 예시 피드백 (Phase 2 AI 생성 전 seed) ──
            if profile == "stuck":
                s.add(StudentFeedback(
                    user_id=u.id, cohort_id=section.id, battle_id=battle.id,
                    scope="lab", trigger="bottleneck", delivered_to="both",
                    model="seed-demo", created_by=prof.id,
                    basis={"bottleneck": snap_flags, "completion": comp},
                    content_md=(f"### 병목 알림 — {STUDENTS[i][0]}\n\n"
                                f"**미션 2(SQLi)** 에서 반복 실패(WAF 차단)가 감지됐습니다. "
                                f"WAF(ModSecurity)가 UNION 기반 페이로드를 차단하는 패턴입니다.\n\n"
                                f"- 다음 시도: 주석/인코딩 우회(`/*!50000UNION*/`, URL 인코딩) 또는 오류 기반 SQLi\n"
                                f"- 개념 복습: 워크북 W05 §RAG/입력검증 우회\n")))
                counts["feedback"] += 1
            else:
                s.add(StudentFeedback(
                    user_id=u.id, cohort_id=section.id, battle_id=battle.id,
                    scope="lab", trigger="end", delivered_to="student",
                    model="seed-demo", created_by=prof.id,
                    basis={"completion": comp, "done": done, "total": steps_total},
                    content_md=(f"### 실습 피드백 — {STUDENTS[i][0]}\n\n"
                                f"진도 {comp}% ({done}/{steps_total} 미션). "
                                f"{'전 미션 완주 — 탐지 회피와 근거 정리가 우수합니다.' if profile=='fast' else '핵심 절차는 안정적입니다. 근거 서술을 더 구체화하면 만점권입니다.'}\n")))
                counts["feedback"] += 1

        await s.commit()

        print("=== Phase 0 시드 완료 ===")
        print(f"코호트: {dept.name} > {course.name} > {section.name} (section id={section.id})")
        print(f"교수: {prof.email} / 학생 {len(students)}명 (비번 {DEMO_PW})")
        print(f"시나리오: [{sc.id}] {sc.title[:50]} | 배틀 id={battle.id} (active)")
        print(f"활동 {counts['activity']} · 진도 {counts['progress']} · 제출 {counts['submissions']} · 피드백 {counts['feedback']}")
        print(f"로그인 예: s6@{DEMO_DOMAIN}(병목 학생) / prof@{DEMO_DOMAIN}(교수)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--purge", action="store_true", help="데모 데이터만 제거")
    args = ap.parse_args()
    asyncio.run(main(purge_only=args.purge))
