"""Phase 9.3 — 학생 보고 이벤트의 채점 근거 분석기.

목표 (사용자 피드백 반영):
- 현재 reasoning 은 학생 입력을 그대로 echo + 미션 기준 나열만 했음 → "분석" 이 0%
- 실제 필요: "당신은 X 를 했다 (학생 보고). 미션 기준은 Y 였다.
            당신의 X 가 success_criteria #1, #3 을 충족하지만 #2 가 빠짐.
            negative_signs #1 (쿠키 누락) 과 일치 — 그래서 ~~. 이렇게 했어야 함: ~.
            학습 권장: courseN weekM 의 MITRE T1110.001 개념"

채점 모델 분기:
- bastion: heuristic — 키워드 매칭으로 success_criteria/negative_signs 평가, 비용 0
- claude:  진짜 LLM 호출 — 위 입력 모두 → 자연어 분석

**원칙**: 단순 echo / 템플릿 출력 금지. heuristic 도 학생 보고 텍스트와 미션
기준을 실제로 비교한 결과만 출력. 매칭이 없으면 솔직히 "확인 불가" 라고 적음.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
import httpx

log = logging.getLogger(__name__)

_CLAUDE_CMD = shutil.which("claude") or "/usr/local/bin/claude"
_CLAUDE_MODEL = os.getenv("TUBEWAR_ANALYZER_MODEL", "claude-haiku-4-5")
_CLAUDE_TIMEOUT = float(os.getenv("TUBEWAR_ANALYZER_TIMEOUT", "40"))
# 채점(grade)은 claude -p 1회가 ~30-40s 걸리고 멀티라운드(직접 점검)면 더 길어 → 넉넉히.
_GRADE_TIMEOUT = float(os.getenv("TUBEWAR_GRADE_TIMEOUT", "150"))

# 동시 채점 제한 — 학생 20명이 동시에 채점 요청해도 claude -p 프로세스가 폭주하지 않도록
# 동시 실행 수를 제한(나머지는 대기 큐). lazy 초기화(이벤트 루프 바인딩 회피).
_GRADE_CONCURRENCY = int(os.getenv("TUBEWAR_GRADE_CONCURRENCY", "4"))
_grade_sem: "asyncio.Semaphore | None" = None


def _get_grade_sem() -> "asyncio.Semaphore":
    global _grade_sem
    if _grade_sem is None:
        _grade_sem = asyncio.Semaphore(_GRADE_CONCURRENCY)
    return _grade_sem


@dataclass
class StudentReport:
    """학생이 이벤트로 보고한 내용 — 분석의 입력."""
    user_name: str
    event_type: str
    target: str
    points_claimed: int
    description: str
    what_i_did: str = ""
    what_happened: str = ""

    def combined_text(self) -> str:
        """매칭 분석에 쓸 통합 텍스트 (lowercased)."""
        parts = [self.description, self.what_i_did, self.what_happened, self.target]
        return " ".join(p for p in parts if p).lower()


@dataclass
class MissionContext:
    """채점 기준이 될 미션 정보 — 시나리오에서 추출."""
    side: str                    # red | blue
    order: int
    instruction: str
    target_vm: str | None
    points: int
    hint: str | None
    verify_expect: str | None
    semantic_intent: str | None  # 예: "MITRE T1110.001 (Brute Force) — ..."
    success_criteria: list[str] = field(default_factory=list)
    acceptable_methods: list[str] = field(default_factory=list)
    negative_signs: list[str] = field(default_factory=list)


@dataclass
class ScenarioContext:
    title: str
    description: str
    course_ref: str | None       # "course3" 등 → 학습 권장에 활용


@dataclass
class AnalysisResult:
    reasoning: str               # markdown 자연어 — 분석 본문
    model: str                   # bastion-analyzer / claude-haiku-4-5 / needs-review
    cost_usd: float = 0.0
    # 구조화된 평가 (UI 가 추가 표시·통계용으로 쓸 수 있음)
    criteria_met: list[str] = field(default_factory=list)
    criteria_missing: list[str] = field(default_factory=list)
    negative_signs_hit: list[str] = field(default_factory=list)
    # AI 시맨틱 채점 결과 (grade() 가 채움). awarded_points=None → 채점 보류(강사 검토).
    verdict: str = "review"      # pass | partial | fail | review
    awarded_points: int | None = None


# ──────────────────────────────────────────────────────
# heuristic (bastion 모드) — LLM 호출 없이 진짜 비교 분석
# ──────────────────────────────────────────────────────

# 한 success_criterion 텍스트에서 의미있는 keyword (소문자 + 길이 3 이상) 추출.
# 분석 정확도를 높이려고 단순 split 이 아닌 alphanumeric token + 한국어 구간 보존.
_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-/.:]+|[가-힣]+")


def _tokens(text: str) -> list[str]:
    if not text:
        return []
    return [t.lower() for t in _TOKEN_RE.findall(text) if len(t) >= 3]


# 너무 일반적이라 매칭에 noise 만 주는 stopword 들 — 한국어/영어 둘 다.
_STOPWORDS = {
    "the", "and", "for", "with", "this", "that", "from", "into", "out",
    "log", "logs", "응답", "확인", "사용", "수행", "이용", "통해", "내용",
}


def _meaningful(tokens: list[str]) -> list[str]:
    return [t for t in tokens if t not in _STOPWORDS]


def _criterion_match_score(criterion: str, student_text: str) -> tuple[float, list[str]]:
    """단일 criterion 의 keyword 가 학생 텍스트에 얼마나 들어있는지 비율 + 매칭된 단어."""
    crit_tokens = _meaningful(_tokens(criterion))
    if not crit_tokens:
        return 0.0, []
    student_lower = student_text  # 이미 lowercased (combined_text)
    hits = [t for t in crit_tokens if t in student_lower]
    return len(hits) / len(crit_tokens), hits


def _evaluate_criteria(
    criteria: list[str], student_text: str, *, threshold: float = 0.34,
) -> tuple[list[tuple[str, float, list[str]]], list[tuple[str, float]]]:
    """충족(>= threshold) / 미충족(< threshold) 분리. 충족은 매칭 단어도 함께."""
    met: list[tuple[str, float, list[str]]] = []
    missing: list[tuple[str, float]] = []
    for c in criteria:
        score, hits = _criterion_match_score(c, student_text)
        if score >= threshold:
            met.append((c, score, hits))
        else:
            missing.append((c, score))
    return met, missing


def _evaluate_negative_signs(
    signs: list[str], student_text: str, *, threshold: float = 0.5,
) -> list[tuple[str, float, list[str]]]:
    """학생 보고에 negative_sign 이 매칭되면 경고."""
    hits: list[tuple[str, float, list[str]]] = []
    for s in signs:
        score, matched = _criterion_match_score(s, student_text)
        if score >= threshold:
            hits.append((s, score, matched))
    return hits


def _judge_score(
    *, claimed: int, mission_points: int, met_count: int, total_criteria: int,
    negative_hits: int,
) -> tuple[str, str]:
    """보고 점수의 적절성 판단 → (verdict, 한 줄 코멘트)."""
    if total_criteria == 0:
        return "미평가", "이 미션은 success_criteria 가 없어 자동 적정성 평가 불가."
    coverage = met_count / total_criteria
    if claimed > mission_points:
        return "과대 보고", f"미션 최대 {mission_points}점인데 {claimed} 점 보고 — 초과."
    if claimed < 0 and negative_hits == 0:
        return "감점 부적절", "감점이지만 negative_signs 매칭이 없어 근거가 약함."
    if coverage >= 0.66 and claimed >= int(mission_points * 0.66):
        return "적정", f"성공 조건의 {met_count}/{total_criteria} 충족 — 보고 점수 합리적."
    if coverage >= 0.34 and claimed > 0:
        return "부분 인정", f"기준의 {met_count}/{total_criteria} 만 충족 — 보고 점수 일부만 인정 가능."
    if coverage < 0.34 and claimed >= mission_points * 0.5:
        return "근거 부족", "보고 점수 대비 충족 기준이 너무 적음 — 추가 보고/검증 필요."
    if negative_hits > 0:
        return "오답 신호", "보고 내용이 negative_signs 와 일치 — 잘못된 시도 가능성."
    return "재검토", "충족 기준이 부족하지만 보고 점수도 작아 큰 문제는 아님."


def _learning_recommendation(
    mission: MissionContext, scenario: ScenarioContext,
) -> str | None:
    """semantic_intent (MITRE 코드 등) + course_ref → 학습 권장 1~2 문장."""
    bits: list[str] = []
    if scenario.course_ref:
        bits.append(scenario.course_ref)
    # MITRE T 코드 추출
    mitre = None
    if mission.semantic_intent:
        m = re.search(r"T\d{4}(?:\.\d{1,3})?", mission.semantic_intent)
        if m:
            mitre = m.group(0)
    if not bits and not mitre and not mission.semantic_intent:
        return None
    parts: list[str] = []
    if scenario.course_ref:
        parts.append(f"`{scenario.course_ref}` 의 관련 주차")
    if mitre:
        parts.append(f"MITRE ATT&CK **{mitre}**")
    if mission.semantic_intent:
        # 첫 콤마 또는 — 까지만 (nutshell)
        nutshell = mission.semantic_intent.split("—")[0].split(",")[0].strip()
        if nutshell and nutshell not in " ".join(parts):
            parts.append(nutshell)
    if not parts:
        return None
    return "다음 학습 권장: " + " · ".join(parts)


def _bastion_analyze(
    report: StudentReport,
    mission: MissionContext | None,
    scenario: ScenarioContext | None,
) -> AnalysisResult:
    """LLM 호출 없이 키워드 매칭 + 룰 기반 평가."""
    side_label = "공격(Red)" if report.event_type in ("attack", "exploit") else \
                 "방어(Blue)" if report.event_type in ("defend", "detect", "block", "alert") else "기타"

    # 미션 컨텍스트 없을 때 — 분석 불가, 솔직히 표기
    if mission is None:
        head = f"**채점 분석 (bastion 휴리스틱) — {side_label}**\n\n"
        body = (
            f"학생 `{report.user_name}` 의 보고:\n"
            f"- 행동: `{report.event_type}` on `{report.target or '(미지정)'}`, 보고 점수 **{report.points_claimed:+}**\n"
            f"- 설명: {report.description or '(없음)'}\n\n"
            "이 이벤트는 특정 미션과 연결되지 않아 (`mission_order` 미지정) "
            "자동 채점 분석이 불가능합니다. 관전자/심판이 직접 적정성을 판단해야 합니다.\n\n"
            "💡 다음 보고부터 `mission_order` + `what_i_did` + `what_happened` 를 함께 입력하면 "
            "성공 조건 대비 자동 분석이 가능합니다."
        )
        return AnalysisResult(reasoning=head + body, model="bastion-analyzer")

    student_text = report.combined_text()
    met, missing = _evaluate_criteria(mission.success_criteria, student_text)
    negs = _evaluate_negative_signs(mission.negative_signs, student_text)
    verdict, score_comment = _judge_score(
        claimed=report.points_claimed, mission_points=mission.points,
        met_count=len(met), total_criteria=len(mission.success_criteria),
        negative_hits=len(negs),
    )

    # ── 본문 markdown 작성 ─────────────────────
    lines: list[str] = []
    lines.append(f"**채점 분석 (bastion 휴리스틱) — {side_label} 미션 #{mission.order}**")
    lines.append("")
    lines.append(f"> {mission.instruction}")
    lines.append("")

    # 학생 보고 (실제 입력 그대로 — 분석 입력으로 사용된 것 노출)
    lines.append("### 1) 학생 보고")
    lines.append(f"- 행위자: `{report.user_name}` ({report.event_type})")
    lines.append(f"- 대상: `{report.target or mission.target_vm or '(미지정)'}`, 보고 점수 **{report.points_claimed:+}** / 미션 최대 {mission.points}")
    lines.append(f"- 한 줄 설명: {report.description or '(미입력)'}")
    if report.what_i_did:
        lines.append(f"- 사용한 명령/페이로드:\n  ```\n  {report.what_i_did[:500]}\n  ```")
    if report.what_happened:
        lines.append(f"- 결과/응답:\n  ```\n  {report.what_happened[:500]}\n  ```")
    if not report.what_i_did and not report.what_happened:
        lines.append("- ⚠️ `what_i_did` / `what_happened` 미입력 — 매칭 정확도가 낮음")
    lines.append("")

    # 잘한 점 / 부족한 점
    lines.append("### 2) 분석 — 성공 조건 대비")
    if not mission.success_criteria:
        lines.append("- 이 미션은 `success_criteria` 가 정의되어 있지 않아 자동 비교 불가.")
    else:
        if met:
            lines.append(f"**충족 ({len(met)}/{len(mission.success_criteria)})**")
            for c, score, hits in met:
                hits_view = ", ".join(f"`{h}`" for h in hits[:5])
                lines.append(f"- ✅ {c}  _(매칭 단어 {len(hits)}개: {hits_view})_")
        if missing:
            lines.append("")
            lines.append(f"**미충족 ({len(missing)}/{len(mission.success_criteria)})**")
            for c, score in missing:
                lines.append(f"- ❌ {c}  _(보고 텍스트에서 핵심 단어 발견 못함)_")
        if not met and not missing:
            lines.append("- (success_criteria 비어있음)")

    # negative_signs 경고
    if negs:
        lines.append("")
        lines.append(f"### 3) ⚠️ 흔한 실수 (negative_signs) {len(negs)}건 매칭")
        for s, score, hits in negs:
            lines.append(f"- 🔥 {s}")
        lines.append("→ 보고된 시도가 잘못된 방향일 가능성. 위 항목을 점검하세요.")

    # 점수 평가
    lines.append("")
    lines.append(f"### {('4' if negs else '3')}) 점수 적정성: **{verdict}**")
    lines.append(f"- {score_comment}")

    # 가이드 (스포일러 보호 — acceptable_methods 첫 1개만, hint 는 collapsed 안내)
    next_idx = 5 if negs else 4
    if missing or negs or not met:
        lines.append("")
        lines.append(f"### {next_idx}) 다시 시도할 때")
        if missing:
            target_crit = missing[0][0]
            lines.append(f"- 가장 먼저 충족시킬 기준: **{target_crit}**")
        if mission.acceptable_methods:
            lines.append(f"- 사용 가능한 방법 (예시): _{mission.acceptable_methods[0]}_")
            if len(mission.acceptable_methods) > 1:
                lines.append(f"  · 다른 경로 {len(mission.acceptable_methods) - 1}개 더 있음.")
        if mission.hint:
            lines.append("- 💡 **힌트** 은 미션 카드의 [상세 ▼ → 힌트] 에서 확인 (스포일러)")
        next_idx += 1

    # 학습 권장
    rec = _learning_recommendation(mission, scenario or ScenarioContext("", "", None))
    if rec:
        lines.append("")
        lines.append(f"### {next_idx}) 📚 {rec}")

    return AnalysisResult(
        reasoning="\n".join(lines),
        model="bastion-analyzer",
        cost_usd=0.0,
        criteria_met=[c for c, _, _ in met],
        criteria_missing=[c for c, _ in missing],
        negative_signs_hit=[s for s, _, _ in negs],
    )


# ──────────────────────────────────────────────────────
# claude 모드 — 진짜 LLM 분석
# ──────────────────────────────────────────────────────
_CLAUDE_SYSTEM = """\
You are a cyber-range exercise grader. The student reported an event in an
ongoing red/blue battle. Analyze whether their report demonstrates that they
satisfied the mission's success criteria.

Respond in **Korean (한국어), markdown** with these sections — keep it focused
and concrete (no flattery, no padding):

### 1) 학생이 보고한 내용 (요약)
1~2문장으로 핵심만.

### 2) 채점 기준 대비 분석
- 어떤 success_criteria 를 충족했는지 (구체적 근거 인용)
- 어떤 기준이 빠졌는지 (왜 못 잡았는지)
- negative_signs 에 해당하는 신호가 있으면 명시

### 3) 점수 평가
보고된 점수가 적정한가? (`mission_points` 와 비교)

### 4) 다시 시도하거나 보강한다면
- 어디를 어떻게 했어야 하는지 한두 줄 가이드
- 단, **완전한 페이로드/비밀번호/정답을 그대로 적지 말 것** — 방향만

### 5) 📚 학습 권장
`scenario.course_ref` 와 `mission.semantic_intent` (MITRE 코드 포함) 를 보고
구체적 학습 주제 1~2개 제시. 예: "course3 의 web vuln 주차에서 hydra http-form
모듈" 같이.

Rules:
- 절대 새로운 사실을 지어내지 말 것. 학생이 보고한 내용 + 미션 spec 안에서만.
- payload/password/완전한 명령어를 통째로 적지 말 것 (학습 의도 보호).
- 학생 텍스트가 비어있거나 짧으면 솔직히 "보고 정보 부족" 이라고 적고 다음
  보고 시 무엇을 더 입력해야 할지 안내.
"""


async def _claude_analyze(
    report: StudentReport,
    mission: MissionContext | None,
    scenario: ScenarioContext | None,
) -> tuple[str, float]:
    payload = {
        "student_report": {
            "user_name": report.user_name,
            "event_type": report.event_type,
            "target": report.target,
            "points_claimed": report.points_claimed,
            "description": report.description,
            "what_i_did": report.what_i_did,
            "what_happened": report.what_happened,
        },
        "mission": None if mission is None else {
            "side": mission.side, "order": mission.order,
            "instruction": mission.instruction,
            "target_vm": mission.target_vm,
            "points": mission.points,
            "verify_expect": mission.verify_expect,
            "semantic_intent": mission.semantic_intent,
            "success_criteria": mission.success_criteria,
            "acceptable_methods": mission.acceptable_methods,
            "negative_signs": mission.negative_signs,
        },
        "scenario": None if scenario is None else {
            "title": scenario.title,
            "description": (scenario.description or "")[:500],
            "course_ref": scenario.course_ref,
        },
    }
    user = "## 분석 입력 (JSON)\n```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
    try:
        proc = await asyncio.create_subprocess_exec(
            _CLAUDE_CMD, "-p", "--output-format", "json",
            "--model", _CLAUDE_MODEL,
            "--append-system-prompt", _CLAUDE_SYSTEM,
            user,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, err = await asyncio.wait_for(proc.communicate(), timeout=_CLAUDE_TIMEOUT)
    except asyncio.TimeoutError:
        return f"_분석 모델 timeout (>{_CLAUDE_TIMEOUT}s) — heuristic 결과로 fallback._", 0.0
    except FileNotFoundError:
        return "_Claude CLI not found — claude binary 가 PATH 에 없음._", 0.0
    if proc.returncode != 0:
        return (
            f"_Claude CLI exit {proc.returncode}: {err.decode('utf-8','replace')[:200]}_",
            0.0,
        )
    try:
        wrap = json.loads(out.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return "_Claude CLI: JSON 파싱 실패_", 0.0
    return (wrap.get("result") or "").strip(), float(wrap.get("total_cost_usd") or 0.0)


# ──────────────────────────────────────────────────────
# 통합 진입
# ──────────────────────────────────────────────────────
async def analyze_event(
    *,
    monitor: str,
    report: StudentReport,
    mission: MissionContext | None,
    scenario: ScenarioContext | None,
) -> AnalysisResult:
    """매뉴얼 이벤트 / 자동 모니터 모두 통과시킬 통합 분석.

    bastion: heuristic 만, 비용 0
    claude:  LLM 분석. heuristic 도 함께 계산해서 구조화 필드는 채움.
    """
    base = _bastion_analyze(report, mission, scenario)
    if monitor != "claude":
        return base
    text, cost = await _claude_analyze(report, mission, scenario)
    if not text or text.startswith("_"):
        # LLM 실패/빈 응답 → heuristic fallback (단, fallback 사실 명시)
        fallback_note = f"\n\n---\n_(claude 분석 실패: {text or 'empty'}) — 위는 bastion heuristic 결과._"
        return AnalysisResult(
            reasoning=base.reasoning + fallback_note,
            model="bastion-analyzer (claude-fallback)",
            cost_usd=cost,
            criteria_met=base.criteria_met,
            criteria_missing=base.criteria_missing,
            negative_signs_hit=base.negative_signs_hit,
        )
    return AnalysisResult(
        reasoning=text,
        model=_CLAUDE_MODEL,
        cost_usd=cost,
        criteria_met=base.criteria_met,
        criteria_missing=base.criteria_missing,
        negative_signs_hit=base.negative_signs_hit,
    )


# ──────────────────────────────────────────────────────
# AI 시맨틱 채점 — 학생 제출 + 읽기전용 증거 → verdict + 점수 (claude)
#
# 원칙(공정성): 학생 말만 믿지 않고 증거(실제 실행 명령/Assessor 상태)로 교차검증.
# 앰비언트 상태(공격자가 만든 로그 등)만으로는 절대 통과시키지 않는다. 점수는 AI 가 결정
# (학생이 부른 점수 무시). 제출 1건당 1회 판정(개별·병렬). claude 불가 시 보류(0점, 강사 검토).
# ──────────────────────────────────────────────────────
_CLAUDE_GRADE_SYSTEM = """\
You are a STRICT, FAIR cyber-range grader. Grade ONE student's submission for ONE mission by
**directly inspecting the student's infrastructure** (read-only) — do not just trust their words.

Inputs: the mission (intent / success_criteria / acceptable_methods / negative_signs / max_points),
the student's self-report, and read-only EVIDENCE already collected from their infra.

You may **request additional read-only inspection** of the student's infra before deciding. To inspect,
return ONLY this JSON: {"inspect":[{"type":"<t>","target":"<vm>","params":{...}}, ...]}
Allowed inspection types (read-only, no side effects):
  file_exists{path} · file_contains{path,pattern} · file_hash{path} · process_running{name} ·
  port_listening{port} · log_contains{log:apache_error|auth|modsec|suricata, pattern} ·
  wazuh_alert{rule_id|pattern} · fim_change{path} · command_ran{pattern}
Prefer inspecting to confirm the student's OWN ACTION — e.g. command_ran{pattern:"sqlmap"} or
command_ran{pattern:"modsec_audit"} to confirm they actually ran the required command;
file_contains to confirm config they created. After results come back, decide.

6v6 attacker model (IMPORTANT for fairness):
- Two attack personas exist: `attacker` (INSIDER — internal routing/DNS) and `attacker-ext` (OUTSIDER,
  on an isolated WAN net — reaches the target ONLY via public ports with a `Host:` header).
- The OUTSIDER's command log is NOT reliably collected by 6v6 — so `command_ran` on target `attacker-ext`
  is UNRELIABLE/borrowed evidence; DO NOT rely on it. For an EXTERNAL or CROSS-INFRA attack (a student
  attacking another VM, or assess_target=opponent), judge by the **TARGET (victim) infra's attack trace**:
  WAF (modsec) / IPS (suricata) / Wazuh alerts / access logs — and CORRELATE the source IP and the exact
  payload to confirm THIS student produced it. For an INSIDER attack on the student's own infra, the
  student's own `command_ran` is reliable evidence.

Grading rules (fairness is critical — a single unfair point is a big problem):
- Simple keyword/state match counts ONLY for extremely certain, unambiguous facts (e.g., a specific
  file exists, a port listens). Everything else must be judged from inspected evidence, semantically.
- Award ZERO when the claim is unsupported by inspection, matches negative_signs, or relies on AMBIENT
  state created by someone else (e.g., a log/alert produced by the attacker, not by the student's own
  analysis/defense). The student must have performed the action themselves (verify via command_ran for
  insider actions, or via correlated target-side trace for external attacks).
- ATTRIBUTION via UNIQUE MARKER (blue rule/config CREATION missions): when the mission prescribes a
  MISSION-SPECIFIC unique marker — a Suricata `sid`, Wazuh rule `id`, auditd key, WAF rule id, or a
  named account/port (e.g. sid:9601011, rule id 102011, account soca01, port 54001) — and inspection
  confirms that EXACT marker is present in the target file/config matching the mission spec, that
  presence is BY ITSELF sufficient proof of the student's action. Such a scenario-specific marker
  cannot plausibly be "ambient" (no one else would create that exact id). Do NOT require command_ran or
  FIM for these (host/console/GUI edits frequently leave no shell trace, and FIM may not watch every
  config dir). Award full/near-full for a correct, spec-matching artifact; reserve deductions only for a
  wrong/missing marker, a syntax error, or functional duplication with a built-in rule.
- EXCEPTION for DEFENSIVE OBSERVATION/ANALYSIS missions (blue team READS logs/alerts/SIEM, often via a
  GUI console → NO shell-command trace exists; do NOT require command_ran here): the student's action is
  to FIND and INTERPRET evidence. Valid proof = (a) the claimed evidence genuinely EXISTS (confirm by
  inspecting the infra), AND (b) the student's report states VERIFIABLE SPECIFICS they could only know by
  actually observing it — correct source IP, timestamp, signature/rule id, count, or affected resource —
  that MATCH the inspected evidence. Specifics match → award (full or near-full). This is still strict and
  fair: a student who did NOT look cannot state the correct specifics. Withhold ONLY if the report is
  vague/generic with no verifiable specifics, the specifics are WRONG, or the evidence does not exist.
  Classify by the mission intent: rule/config/attack missions need the artifact/trace; pure
  observation/analysis missions need accurate, evidence-matching specifics.
- NEVER trust the student's self-claimed points. YOU decide points in [0, max_points]. Partial allowed.
- If evidence is insufficient after inspection, be conservative and explain what's missing.

When ready, return ONE final JSON object (no markdown, no prose):
{"passed": true|false, "awarded_points": <int 0..max_points>, "verdict": "pass|partial|fail",
 "criteria_met": ["..."], "criteria_missing": ["..."],
 "reasoning": "<한국어 — 어떤 증거(직접 점검 포함)로 무엇을 인정/불인정했는지, 점수 근거, 부족한 점>"}
"""

_ALLOWED_INSPECT = {
    "file_exists", "file_contains", "file_hash", "process_running",
    "port_listening", "log_contains", "wazuh_alert", "fim_change", "command_ran",
}


async def _claude_grade(payload: dict, model: str | None = None) -> tuple[str | None, float]:
    """CC (Claude Code CLI) 채점 1회. (text, cost) 반환, 실패 시 (None, 0)."""
    user = "## 채점 입력 (JSON)\n```json\n" + json.dumps(payload, ensure_ascii=False) + "\n```"
    try:
        async with _get_grade_sem():   # 동시 채점 수 제한(20명 동시 → 큐잉)
            proc = await asyncio.create_subprocess_exec(
                _CLAUDE_CMD, "-p", "--output-format", "json", "--model", (model or _CLAUDE_MODEL),
                "--append-system-prompt", _CLAUDE_GRADE_SYSTEM, user,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            out, _err = await asyncio.wait_for(proc.communicate(), timeout=_GRADE_TIMEOUT)
        if proc.returncode != 0:
            return None, 0.0
        wrap = json.loads(out.decode("utf-8", "replace"))
        return (wrap.get("result") or "").strip(), float(wrap.get("total_cost_usd") or 0.0)
    except (asyncio.TimeoutError, FileNotFoundError, json.JSONDecodeError):
        return None, 0.0


async def _bastion_grade(payload: dict, base_url: str, model: str,
                         api_key: str | None) -> tuple[str | None, float]:
    """6v6 Bastion LLM (ollama 호환 /api/generate) 채점 1회. 로컬 모델이라 cost=0."""
    if not base_url:
        return None, 0.0
    prompt = (_CLAUDE_GRADE_SYSTEM + "\n\n## 채점 입력 (JSON)\n"
              + json.dumps(payload, ensure_ascii=False)
              + "\n\n위 지시에 따라 최종 JSON 하나만 출력하라.")
    url = base_url.rstrip("/") + "/api/generate"
    headers = {"X-API-Key": api_key or "", "content-type": "application/json"}
    body = {"model": model, "prompt": prompt, "stream": False, "format": "json"}
    try:
        async with httpx.AsyncClient(timeout=_GRADE_TIMEOUT, verify=False) as c:
            r = await c.post(url, headers=headers, json=body)
            if r.status_code >= 300:
                return None, 0.0
            data = r.json()
            # ollama generate → {"response": "..."}; chat 변형 → {"message":{"content":...}}
            text = data.get("response")
            if not text and isinstance(data.get("message"), dict):
                text = data["message"].get("content")
            return ((text or "").strip() or None), 0.0
    except Exception:
        return None, 0.0


def _extract_json_obj(text: str) -> dict:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1].rsplit("```", 1)[0] if "\n" in t else t
    i = t.find("{")
    if i == -1:
        raise ValueError("no json")
    j = t.rfind("}")
    if j != -1:
        try:
            return json.loads(t[i:j + 1])
        except Exception:
            pass
    # 잘린 JSON 복구 — 미완 문자열/배열/객체를 닫아 마지막 유효 객체를 회수
    # (claude 출력이 길어 잘리면 정상 판정이 0점 처리되던 것 방지).
    return json.loads(_repair_truncated_json(t[i:]))


def _repair_truncated_json(s: str) -> str:
    """여는 괄호/문자열이 미완인 잘린 JSON 문자열을 닫아 파싱 가능하게 복구."""
    stack: list[str] = []
    in_str = esc = False
    for ch in s:
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]" and stack:
            stack.pop()
    out = s + ('"' if in_str else "")
    out = re.sub(r"[,:]\s*$", "", out.rstrip())   # 트레일링 콤마/콜론 제거
    for ch in reversed(stack):
        out += "}" if ch == "{" else "]"
    return out


async def grade(
    *,
    report: StudentReport,
    mission: MissionContext | None,
    scenario: ScenarioContext | None,
    evidence_text: str = "",
    max_points: int = 0,
    inspector=None,          # async callable(list[check-spec]) -> list[result]  (참여자 infra 직접 점검)
    max_rounds: int = int(os.getenv("TUBEWAR_GRADE_ROUNDS", "2")),  # 라운드(claude 호출) 수. 1=초기증거(체크결과 포함)만으로 즉시 판정 → claude 호출/레이트 절반. env TUBEWAR_GRADE_ROUNDS.
    grader: dict | None = None,   # {provider:cc|bastion, model, base_url, api_key} — 시나리오별 채점기
) -> AnalysisResult:
    """학생 제출 1건을 AI 가 **참여자 인프라를 직접 점검**하며 시맨틱 채점. 점수는 AI 가 결정.

    grader 로 시나리오별 채점 AI/모델 선택(CC=claude CLI / bastion=6v6 LLM). 미지정 시 CC 기본.
    inspector 가 주어지면 AI 가 추가 read-only check 를 요청할 수 있고(에이전트형), 그 결과를
    근거로 최종 판정한다. 단순 키워드 매칭은 극히 확실한 경우에만, 나머지는 AI 직접 점검.
    """
    grader = grader or {"provider": "cc", "model": _CLAUDE_MODEL}
    provider = grader.get("provider", "cc")
    g_model = grader.get("model") or _CLAUDE_MODEL
    model_label = f"{provider}:{g_model}"

    async def _call(p: dict) -> tuple[str | None, float]:
        if provider == "bastion":
            return await _bastion_grade(p, grader.get("base_url") or "", g_model, grader.get("api_key"))
        return await _claude_grade(p, g_model)
    if mission is None:
        return AnalysisResult(
            reasoning="미션이 지정되지 않아 자동 채점 불가 — 강사 검토가 필요합니다.",
            model="needs-review", verdict="review", awarded_points=None)

    # 테스트/e2e 전용 결정론 stub (운영 OFF). 플러밍 검증용 — what_i_did 가 있으면 통과.
    if os.getenv("TUBEWAR_GRADER_STUB", "").lower() in ("1", "true", "yes"):
        did = bool((report.what_i_did or "").strip())
        return AnalysisResult(
            reasoning="[grader-stub] " + ("제출 증거(what_i_did) 있음 → 통과" if did else "증거 없음 → 불인정"),
            model="grader-stub", verdict="pass" if did else "fail",
            awarded_points=(max_points if did else 0),
            criteria_met=(list(mission.success_criteria) if did else []),
            criteria_missing=([] if did else list(mission.success_criteria)))

    payload = {
        "mission": {
            "side": mission.side, "order": mission.order, "instruction": mission.instruction,
            "target_vm": mission.target_vm, "max_points": max_points,
            "semantic_intent": mission.semantic_intent,
            "success_criteria": mission.success_criteria,
            "acceptable_methods": mission.acceptable_methods,
            "negative_signs": mission.negative_signs,
        },
        "student_report": {
            "user_name": report.user_name, "event_type": report.event_type,
            "target": report.target, "claimed_points": report.points_claimed,
            "description": report.description,
            "what_i_did": report.what_i_did, "what_happened": report.what_happened,
        },
        "read_only_evidence": evidence_text or "(초기 증거 없음 — 필요하면 inspect 로 직접 점검하라)",
        "max_points": max_points,
        "can_inspect": inspector is not None,
    }

    total_cost = 0.0
    for _round in range(max_rounds):
        final = (_round == max_rounds - 1)
        # 마지막 라운드는 '추가 점검 금지, 지금 최종 verdict' 강제 → CC 의 분석을 점수로 확정.
        p = dict(payload)
        if final:
            p["finalize"] = ("추가 inspect 금지. 지금까지의 증거(직접 점검 포함)만으로 최종 verdict "
                             "JSON 하나만 출력하라.")
        text, cost = await _call(p)
        total_cost += cost
        if text is None and final:        # 마지막 결정 호출 실패 → 1회 재시도(CC 작업 유실 방지)
            text, cost = await _call(p)
            total_cost += cost
        if text is None:
            if final:
                return AnalysisResult(
                    reasoning="_AI 채점기 호출 실패(타임아웃/오류) — 자동 점수 보류, 강사 검토 대기 "
                              "(불공정 방지)._",
                    model="needs-review", verdict="review", awarded_points=None, cost_usd=total_cost)
            continue   # 비-최종 라운드 실패 → 다음 라운드(증거 유지) 재시도

        try:
            v = _extract_json_obj(text)
        except Exception:
            # 최종 라운드 파싱 실패 → 1회 재시도(잘린/깨진 JSON 회복; 정상 제출이 0점 되는 것 방지).
            if final:
                text2, cost2 = await _call(p)
                total_cost += cost2
                try:
                    v = _extract_json_obj(text2 or "")
                except Exception:
                    return AnalysisResult(
                        reasoning=f"_AI 응답 파싱 실패(재시도 후) — 강사 검토 필요._\n\n```\n{(text or '')[:400]}\n```",
                        model="needs-review", verdict="review", awarded_points=None, cost_usd=total_cost)
            else:
                continue

        # AI 가 인프라 직접 점검을 요청 (마지막 라운드 전까지만)
        req = v.get("inspect")
        if req and inspector is not None and not final:
            checks = []
            for n, c in enumerate(req[:8], start=1):
                if isinstance(c, dict) and c.get("type") in _ALLOWED_INSPECT:
                    checks.append({"id": f"ai-{_round}-{n}", "type": c["type"],
                                   "target": c.get("target") or mission.target_vm,
                                   "params": c.get("params") or {}})
            results = await inspector(checks) if checks else []
            payload["read_only_evidence"] += (
                f"\n[AI 가 직접 요청한 점검 결과 round {_round + 1}]\n" + json.dumps(results, ensure_ascii=False)
            )
            continue

        # 최종 판정
        pts = max(0, min(int(v.get("awarded_points") or 0), max_points))
        verdict = str(v.get("verdict") or ("pass" if v.get("passed") else "fail"))
        return AnalysisResult(
            reasoning=str(v.get("reasoning") or ""),
            model=model_label, cost_usd=total_cost,
            criteria_met=list(v.get("criteria_met") or []),
            criteria_missing=list(v.get("criteria_missing") or []),
            verdict=verdict, awarded_points=pts,
        )

    return AnalysisResult(
        reasoning="_AI 가 점검을 반복했으나 최종 판정에 이르지 못함 — 강사 검토 필요._",
        model="needs-review", verdict="review", awarded_points=None, cost_usd=total_cost)


# ── 중앙 SIEM 로그 분석 Q&A (강사가 페이지에서 질문 → CC/bastion 이 로그 근거로 답변) ──
_SIEM_ANALYST_SYSTEM = (
    "당신은 사이버 보안 실습 플랫폼 tubewar 의 SIEM 분석가다. 주어진 학생 활동 로그"
    "(명령/알림/파일변경/서비스), 통계, 진도·클리어 데이터를 근거로 강사의 질문에 한국어로"
    " 간결·정확하게 답한다.\n"
    "원칙:\n"
    "- 추측 금지. 데이터에 없으면 '데이터에 없음'이라고 분명히 말한다.\n"
    "- 구체적 근거(학생 번호, 시각, 명령/룰, 시나리오·미션)를 인용한다.\n"
    "- 보안 교육 관점의 통찰(막힌 학생, 공격/방어 흐름, 이상 징후, 의심 활동)을 우선한다.\n"
    "- 표·불릿으로 구조화하고 장황하지 않게. 결론을 먼저."
)


async def _claude_text(system: str, user: str, model: str | None = None) -> tuple[str | None, float]:
    """CC 자유서술 1회 (JSON 강제 X). (text, cost)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            _CLAUDE_CMD, "-p", "--output-format", "json", "--model", (model or _CLAUDE_MODEL),
            "--append-system-prompt", system, user,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        out, _err = await asyncio.wait_for(proc.communicate(), timeout=_GRADE_TIMEOUT)
        if proc.returncode != 0:
            return None, 0.0
        wrap = json.loads(out.decode("utf-8", "replace"))
        return (wrap.get("result") or "").strip() or None, float(wrap.get("total_cost_usd") or 0.0)
    except (asyncio.TimeoutError, FileNotFoundError, json.JSONDecodeError):
        return None, 0.0


async def _bastion_text(system: str, user: str, base_url: str, model: str,
                        api_key: str | None) -> tuple[str | None, float]:
    """6v6 Bastion LLM (ollama 호환) 자유서술 1회. (text, 0)."""
    if not base_url:
        return None, 0.0
    url = base_url.rstrip("/") + "/api/generate"
    headers = {"X-API-Key": api_key or "", "content-type": "application/json"}
    body = {"model": model, "prompt": system + "\n\n" + user, "stream": False}
    try:
        async with httpx.AsyncClient(timeout=_GRADE_TIMEOUT, verify=False) as c:
            r = await c.post(url, headers=headers, json=body)
            if r.status_code >= 300:
                return None, 0.0
            data = r.json()
            text = data.get("response")
            if not text and isinstance(data.get("message"), dict):
                text = data["message"].get("content")
            return ((text or "").strip() or None), 0.0
    except Exception:
        return None, 0.0


async def analyze_logs(question: str, context: dict, grader: dict) -> AnalysisResult:
    """강사 질문 + 로그/통계 컨텍스트를 CC 또는 bastion 에 보내 분석 답변을 받는다.

    grader: graders.resolve_* 가 주는 dict {provider, model, base_url, api_key, name}.
    """
    ctx = json.dumps(context, ensure_ascii=False, default=str)
    if len(ctx) > 24000:          # 토큰 보호 — 너무 크면 자른다
        ctx = ctx[:24000] + " …(생략)"
    user = ("## 강사 질문\n" + (question or "(질문 없음)")
            + "\n\n## 분석 대상 데이터 (JSON: 통계 + 최근 로그 + 진도)\n```json\n" + ctx + "\n```")
    provider = grader.get("provider", "cc")
    model = grader.get("model") or _CLAUDE_MODEL
    if provider == "bastion":
        text, cost = await _bastion_text(_SIEM_ANALYST_SYSTEM, user, grader.get("base_url") or "",
                                         model, grader.get("api_key"))
    else:
        text, cost = await _claude_text(_SIEM_ANALYST_SYSTEM, user, model)
    if not text:
        return AnalysisResult(reasoning="_AI 응답 없음 또는 시간 초과 — 잠시 후 다시 시도하세요._",
                              model=f"{provider}:error", cost_usd=0.0)
    return AnalysisResult(reasoning=text, model=f"{provider}:{model}", cost_usd=cost)
