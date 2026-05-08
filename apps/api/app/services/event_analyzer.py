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

log = logging.getLogger(__name__)

_CLAUDE_CMD = shutil.which("claude") or "/usr/local/bin/claude"
_CLAUDE_MODEL = os.getenv("TUBEWAR_ANALYZER_MODEL", "claude-haiku-4-5")
_CLAUDE_TIMEOUT = float(os.getenv("TUBEWAR_ANALYZER_TIMEOUT", "40"))


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
    model: str                   # bastion-analyzer / claude-haiku-4-5
    cost_usd: float = 0.0
    # 구조화된 평가 (UI 가 추가 표시·통계용으로 쓸 수 있음)
    criteria_met: list[str] = field(default_factory=list)
    criteria_missing: list[str] = field(default_factory=list)
    negative_signs_hit: list[str] = field(default_factory=list)


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
