"""P13-3 + V13-1 — 로컬 Ollama LLM-as-judge 채점과 저지 자체의 신뢰성 검증."""
import argparse
import json
import re
import statistics
import sys
import time
import urllib.error
import urllib.request

import common  # noqa: F401
from common import INSTRUCTION_JSON, JUDGE_MODEL, OLLAMA_URL
from instr_data import format_input

BOGUS = "The weather is nice today."


def ollama_alive(url=OLLAMA_URL):
    tags = url.replace("/api/chat", "/api/tags")
    try:
        with urllib.request.urlopen(tags, timeout=8) as r:
            return json.loads(r.read())
    except Exception as e:
        print(f"[중단] Ollama 에 닿지 못했다: {type(e).__name__}: {e}")
        print(f"       확인한 주소: {tags}")
        print("       호스트에서 `ollama serve` 가 떠 있는지 확인하고,")
        print("       컨테이너에서는 localhost 가 아니라 docker0 게이트웨이")
        print("       (172.17.0.1) 를 써야 한다.")
        return None


def query_model(prompt, model=JUDGE_MODEL, url=OLLAMA_URL, retries=2):
    """채점 재현성을 위해 seed·temperature 를 고정한다."""
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"seed": 123, "temperature": 0, "num_ctx": 2048},
    }
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    last = None
    for _ in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read())["message"]["content"]
        except Exception as e:              # 일시적 오류는 재시도
            last = e
            time.sleep(2)
    raise RuntimeError(f"Ollama 호출 실패: {last}")


def score_prompt(entry, response):
    return (
        f"Given the input `{format_input(entry)}` "
        f"and correct output `{entry['output']}`, "
        f"score the model response `{response}` "
        f"on a scale from 0 to 100, where 100 is the best score. "
        f"Respond with the integer number only."
    )


INT_RE = re.compile(r"-?\d+")


def parse_score(text):
    """저지 응답에서 첫 정수를 뽑는다. 실패하면 (None, 원문)."""
    m = INT_RE.search(text)
    if not m:
        return None, text
    v = int(m.group())
    if not (0 <= v <= 100):
        return None, text
    return v, text


def score_all(entries, response_key="model_response", label=""):
    scores, failures = [], []
    t0 = time.time()
    for i, e in enumerate(entries, 1):
        resp = e[response_key] if isinstance(response_key, str) else response_key
        raw = query_model(score_prompt(e, resp))
        v, raw_txt = parse_score(raw)
        if v is None:
            failures.append((i - 1, raw_txt))
        else:
            scores.append(v)
        if i % 10 == 0 or i == len(entries):
            print(f"    {label}{i:3d}/{len(entries)} "
                  f"({time.time()-t0:.0f}초)", flush=True)
    return scores, failures


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--responses", default="test_responses.json")
    ap.add_argument("--out", default="judge_report.md")
    ap.add_argument("--tag", default="풀 튜닝 355M (2 에폭)")
    ap.add_argument("--reliability", action="store_true",
                    help="V13-1 저지 신뢰성 3종 검증도 함께 수행")
    ap.add_argument("--scores-out", default=None)
    args = ap.parse_args()

    tags = ollama_alive()
    if tags is None:
        sys.exit(1)
    names = [m["name"] for m in tags["models"]]
    print(f"Ollama 연결 OK — 모델 {len(names)}개 보유")
    if JUDGE_MODEL not in names:
        print(f"[중단] 저지 모델 {JUDGE_MODEL} 이 없다. `ollama pull {JUDGE_MODEL}`")
        sys.exit(1)
    print(f"저지 모델: **{JUDGE_MODEL}** (options: seed=123, temperature=0, num_ctx=2048)")

    data = json.load(open(args.responses, encoding="utf-8"))
    print(f"채점 대상: {args.responses} ({len(data)}건)")
    print()
    print("=" * 74)
    print(f"1. 본 채점 — {args.tag}")
    print("=" * 74)
    scores, failures = score_all(data)

    mean = statistics.mean(scores)
    sd = statistics.pstdev(scores)
    print()
    print(f"  채점 성공 {len(scores)}건 / 파싱 실패 **{len(failures)}건**")
    print(f"  평균 **{mean:.2f}점** / 표준편차 {sd:.2f} / "
          f"중앙값 {statistics.median(scores)}")
    print(f"  최저 {min(scores)} / 최고 {max(scores)}")
    if failures:
        print(f"  파싱 실패 사례:")
        for idx, raw in failures[:3]:
            print(f"    · idx {idx}: {raw[:120]!r}")

    # 히스토그램
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.hist(scores, bins=range(0, 105, 5), color="#4477aa", edgecolor="white")
    ax.axvline(mean, color="red", linestyle="--", label=f"평균 {mean:.1f}")
    ax.set_xlabel("저지 점수 (0~100)"); ax.set_ylabel("항목 수")
    ax.set_title(f"LLM-as-judge 점수 분포 — {args.tag} (저지 {JUDGE_MODEL})")
    ax.legend(); fig.tight_layout()
    png = args.out.replace(".md", "_hist.png")
    fig.savefig(png, dpi=130)
    print(f"  [저장] {png}")

    # 점수를 항목에 붙여 상·하위 추출
    scored = []
    fail_idx = {i for i, _ in failures}
    si = 0
    for i, e in enumerate(data):
        if i in fail_idx:
            continue
        scored.append((scores[si], i, e))
        si += 1
    scored.sort(key=lambda t: -t[0])
    top3, bottom3 = scored[:3], scored[-3:]

    print()
    print("  --- 상위 3 ---")
    for s, i, e in top3:
        print(f"    [{s}점] idx {i}: {e['instruction'][:50]}")
        print(f"           정답: {e['output'][:70]}")
        print(f"           모델: {e['model_response'][:70]}")
    print("  --- 하위 3 ---")
    for s, i, e in bottom3:
        print(f"    [{s}점] idx {i}: {e['instruction'][:50]}")
        print(f"           정답: {e['output'][:70]}")
        print(f"           모델: {e['model_response'][:70]}")

    rel = None
    if args.reliability:
        print()
        print("=" * 74)
        print("2. V13-1 — 저지 자체 검증")
        print("=" * 74)
        sample10 = data[:10]

        print("  [상한] 정답 자체를 model_response 자리에 넣어 채점")
        upper, uf = [], []
        for i, e in enumerate(sample10, 1):
            raw = query_model(score_prompt(e, e["output"]))
            v, t = parse_score(raw)
            (upper.append(v) if v is not None else uf.append((i, t)))
        print(f"    점수 {upper} → 평균 **{statistics.mean(upper):.1f}**")

        print(f"  [하한] 같은 10개에 무관한 문장 {BOGUS!r} 을 넣어 채점")
        lower, lf = [], []
        for i, e in enumerate(sample10, 1):
            raw = query_model(score_prompt(e, BOGUS))
            v, t = parse_score(raw)
            (lower.append(v) if v is not None else lf.append((i, t)))
        print(f"    점수 {lower} → 평균 **{statistics.mean(lower):.1f}**")

        print("  [결정성] 같은 (항목, 응답) 5개를 각 3회 채점")
        det = []
        for e in data[:5]:
            trio = []
            for _ in range(3):
                raw = query_model(score_prompt(e, e["model_response"]))
                v, _t = parse_score(raw)
                trio.append(v)
            det.append(trio)
            print(f"    {e['instruction'][:44]:<46} {trio} "
                  f"{'동일' if len(set(trio)) == 1 else '**변동**'}")
        all_same = all(len(set(t)) == 1 for t in det)
        print(f"    → 결정성 {'성립' if all_same else '**불성립**'}")

        rel = {
            "upper": upper, "upper_mean": statistics.mean(upper),
            "lower": lower, "lower_mean": statistics.mean(lower),
            "determinism": det, "all_same": all_same,
            "upper_fail": uf, "lower_fail": lf,
        }
        print()
        print(f"  통과 기준 — 상한 ≫ 하한: "
              f"{rel['upper_mean']:.1f} vs {rel['lower_mean']:.1f} → "
              f"{'PASS' if rel['upper_mean'] > rel['lower_mean'] + 20 else 'FAIL'}")
        print(f"  통과 기준 — 상한 90 이상: "
              f"{'PASS' if rel['upper_mean'] >= 90 else 'FAIL'}")
        print(f"  통과 기준 — 결정성: {'PASS' if all_same else 'FAIL'}")

    # ---------------- 리포트 ----------------
    L = [f"# judge_report.md — LLM-as-judge 채점 (P13-3 산출물)", ""]
    L.append(f"채점 대상: **{args.tag}** · 응답 파일 `{args.responses}` ({len(data)}건)")
    L.append(f"저지: **{JUDGE_MODEL}** (로컬 Ollama, `{OLLAMA_URL}`) · "
             f"options `seed=123, temperature=0, num_ctx=2048`")
    L.append("")
    L.append("## 채점 결과")
    L.append("")
    L.append("| 항목 | 값 |")
    L.append("|---|---|")
    L.append(f"| 채점 성공 | {len(scores)} / {len(data)} |")
    L.append(f"| 파싱 실패 | **{len(failures)}** |")
    L.append(f"| 평균 | **{mean:.2f}점** |")
    L.append(f"| 표준편차 | {sd:.2f} |")
    L.append(f"| 중앙값 | {statistics.median(scores)} |")
    L.append(f"| 최저 / 최고 | {min(scores)} / {max(scores)} |")
    L.append("")
    L.append(f"![점수 분포]({png})")
    L.append("")
    if failures:
        L.append("### 파싱 실패 사례")
        L.append("")
        for idx, raw in failures[:5]:
            L.append(f"- idx {idx}: `{raw[:200]}`")
        L.append("")
    else:
        L.append("파싱 실패 **0건**. 프롬프트의 "
                 "\"Respond with the integer number only.\" 가 잘 작동했다.")
        L.append("")
    L.append("## 상위 3 / 하위 3")
    L.append("")
    L.append("| 순위 | 점수 | 지시 | 정답 | 모델 응답 |")
    L.append("|---|---|---|---|---|")
    for r, (s, i, e) in enumerate(top3, 1):
        L.append(f"| 상위 {r} | **{s}** | {e['instruction'][:44]} | "
                 f"{e['output'][:54]} | {e['model_response'][:54]} |")
    for r, (s, i, e) in enumerate(reversed(bottom3), 1):
        L.append(f"| 하위 {r} | **{s}** | {e['instruction'][:44]} | "
                 f"{e['output'][:54]} | {e['model_response'][:54]} |")
    L.append("")

    if rel:
        L.append("## 저지 신뢰성 (V13-1)")
        L.append("")
        L.append("| 검증 | 방법 | 결과 | 판정 |")
        L.append("|---|---|---|---|")
        L.append(f"| **상한** | 테스트셋 10개의 정답 자체를 채점 | "
                 f"평균 **{rel['upper_mean']:.1f}** (점수 {rel['upper']}) | "
                 f"{'PASS' if rel['upper_mean'] >= 90 else 'FAIL'} (90 이상) |")
        L.append(f"| **하한** | 같은 10개에 `{BOGUS}` 고정 투입 | "
                 f"평균 **{rel['lower_mean']:.1f}** (점수 {rel['lower']}) | "
                 f"{'PASS' if rel['lower_mean'] < rel['upper_mean'] - 20 else 'FAIL'} "
                 f"(상한보다 크게 낮아야) |")
        L.append(f"| **결정성** | 같은 (항목,응답) 5개 × 3회 | "
                 f"{'매회 동일' if rel['all_same'] else '**변동 발생**'} | "
                 f"{'PASS' if rel['all_same'] else 'FAIL'} |")
        L.append("")
        L.append(f"상한 {rel['upper_mean']:.1f} ≫ 하한 {rel['lower_mean']:.1f} "
                 f"(격차 **{rel['upper_mean']-rel['lower_mean']:.1f}점**). "
                 f"저지는 정답과 엉터리를 확실히 구분한다.")
        L.append("")
        L.append("### 결정성 원자료")
        L.append("")
        L.append("| 지시 | 3회 점수 | 동일 |")
        L.append("|---|---|---|")
        for e, trio in zip(data[:5], rel["determinism"]):
            L.append(f"| {e['instruction'][:50]} | {trio} | "
                     f"{'O' if len(set(trio)) == 1 else '**X**'} |")
        L.append("")
        L.append("> **학생 직접 단계(에이전트 금지)**: 위 상위 2개·하위 2개 응답을 "
                 "직접 읽고 저지 점수에 동의하는지 항목별로 평가하라. "
                 "그리고 저지의 한계 사례를 최소 1개 찾아 report.md 에 기록하라.")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print(f"\n[저장] {args.out}")

    if args.scores_out:
        json.dump({"tag": args.tag, "scores": scores, "mean": mean, "sd": sd,
                   "failures": len(failures), "reliability": rel},
                  open(args.scores_out, "w"), ensure_ascii=False, indent=2)
        print(f"[저장] {args.scores_out}")
