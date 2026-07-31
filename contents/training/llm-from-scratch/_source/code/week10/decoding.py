"""week10 디코딩 전략 — temperature / top-k / 최종 generate.

P10-1(temperature 해부) · P10-2(top-k 마스킹) · P10-3(generate 통합 + 그리드) 를
이 한 파일에 순서대로 쌓는다. 모듈로 import 하면 함수만 가져다 쓸 수 있도록
실행부는 __main__ 아래에 둔다 (V10-2 의 test_decoding.py 가 import 한다).
"""
import torch

# ---------------------------------------------------------------------------
# P10-1 — temperature
# ---------------------------------------------------------------------------

# 장난감 어휘. 교재가 준 순서 그대로 인덱스를 매긴다.
VOCAB = {
    "closer": 0,
    "every": 1,
    "effort": 2,
    "forward": 3,
    "inches": 4,
    "moves": 5,
    "pizza": 6,
    "toward": 7,
    "you": 8,
}
INVERSE_VOCAB = {v: k for k, v in VOCAB.items()}

NEXT_TOKEN_LOGITS = torch.tensor(
    [4.51, 0.89, -1.90, 6.75, 1.63, -1.62, -1.89, 6.28, 1.79]
)


def softmax_with_temperature(logits, temperature):
    """로짓을 temperature 로 나눈 뒤 softmax.

    T < 1 : 큰 로짓이 더 커져 분포가 뾰족해진다 (보수적)
    T > 1 : 로짓 차이가 눌려 분포가 평평해진다 (모험적)
    T → 0 : argmax 한 곳에 확률 1 — greedy 와 같아진다
    """
    scaled = logits / temperature
    return torch.softmax(scaled, dim=-1)


# ---------------------------------------------------------------------------
# P10-2 — top-k 마스킹
# ---------------------------------------------------------------------------

def topk_mask(logits, k):
    """상위 k 개 밖의 로짓을 -inf 로 채운 새 로짓을 돌려준다.

    -inf 로 채우는 이유: softmax 는 exp(x) 를 쓰므로 exp(-inf) = 0 이 되어
    해당 자리의 확률이 '정확히' 0 이 된다. 5주차 코잘 마스크의 그 트릭이다.
    """
    top_logits, _ = torch.topk(logits, k)
    min_val = top_logits[..., -1]           # k 번째로 큰 값 (경계값)
    return torch.where(
        logits < min_val,
        torch.tensor(float("-inf")).to(logits.device),
        logits,
    )


# ---------------------------------------------------------------------------
# P10-3 — 최종 generate
# ---------------------------------------------------------------------------

def generate(model, idx, max_new_tokens, context_size,
             temperature=0.0, top_k=None, eos_id=None):
    """temperature · top-k · greedy 폴백 · eos 조기 종료를 모두 갖춘 생성기."""
    for _ in range(max_new_tokens):
        idx_cond = idx[:, -context_size:]
        with torch.no_grad():
            logits = model(idx_cond)
        logits = logits[:, -1, :]                     # 마지막 시점만 [B, vocab]

        if top_k is not None:
            logits = topk_mask(logits, top_k)

        if temperature > 0.0:
            probs = torch.softmax(logits / temperature, dim=-1)
            idx_next = torch.multinomial(probs, num_samples=1)
        else:
            idx_next = torch.argmax(logits, dim=-1, keepdim=True)

        if eos_id is not None and (idx_next == eos_id).all():
            break

        idx = torch.cat((idx, idx_next), dim=1)
    return idx


# ===========================================================================
# 실행부
# ===========================================================================
if __name__ == "__main__":
    import matplotlib.pyplot as plt
    import numpy as np

    print("=" * 74)
    print("P10-1 — temperature 해부")
    print("=" * 74)

    argmax_id = int(torch.argmax(NEXT_TOKEN_LOGITS))
    print(f"argmax 인덱스 {argmax_id} → 단어 **{INVERSE_VOCAB[argmax_id]}** "
          f"(로짓 {NEXT_TOKEN_LOGITS[argmax_id]:.2f})")
    print()

    TEMPS = [0.1, 1.0, 5.0]
    dists = {T: softmax_with_temperature(NEXT_TOKEN_LOGITS, T) for T in TEMPS}

    print("--- 온도별 확률분포 ---")
    header = f"{'단어':<9}{'로짓':>8}" + "".join(f"{f'T={T}':>14}" for T in TEMPS)
    print(header)
    print("-" * len(header))
    for i in range(len(NEXT_TOKEN_LOGITS)):
        row = f"{INVERSE_VOCAB[i]:<9}{NEXT_TOKEN_LOGITS[i]:>8.2f}"
        for T in TEMPS:
            row += f"{dists[T][i].item():>14.6f}"
        print(row)
    print(f"{'합계':<9}{'':>8}" + "".join(f"{dists[T].sum().item():>14.6f}" for T in TEMPS))

    # 막대그래프
    x = np.arange(len(VOCAB))
    width = 0.25
    fig, ax = plt.subplots(figsize=(11, 4.5))
    for j, T in enumerate(TEMPS):
        ax.bar(x + (j - 1) * width, dists[T].numpy(), width, label=f"T = {T}")
    ax.set_xticks(x)
    ax.set_xticklabels([INVERSE_VOCAB[i] for i in range(len(VOCAB))], rotation=30)
    ax.set_ylabel("확률")
    ax.set_title("temperature 가 분포를 바꾼다 (T 가 커질수록 평평해짐)")
    ax.legend()
    fig.tight_layout()
    fig.savefig("temp_plot.png", dpi=110)
    print("\n[저장] temp_plot.png")

    # 1000회 추첨
    print()
    print("--- torch.manual_seed(123) 후 multinomial 1000회 추첨 ---")
    N = 1000
    counts = {}
    for T in (1.0, 5.0):
        torch.manual_seed(123)
        probs = softmax_with_temperature(NEXT_TOKEN_LOGITS, T)
        sample = torch.multinomial(probs, num_samples=N, replacement=True)
        c = torch.bincount(sample, minlength=len(VOCAB))
        counts[T] = c
    hdr = f"{'단어':<9}" + "".join(f"{f'T={T} 횟수':>14}{f'(기대%)':>10}" for T in (1.0, 5.0))
    print(hdr)
    print("-" * len(hdr))
    for i in range(len(VOCAB)):
        row = f"{INVERSE_VOCAB[i]:<9}"
        for T in (1.0, 5.0):
            row += f"{counts[T][i].item():>14d}"
            row += f"{softmax_with_temperature(NEXT_TOKEN_LOGITS, T)[i].item()*100:>9.2f}%"
        print(row)

    pizza = VOCAB["pizza"]
    print()
    print(f"[검증 답] argmax 단어 = **{INVERSE_VOCAB[argmax_id]}**")
    print(f"[검증 답] pizza 추첨 횟수 : T=1 → **{counts[1.0][pizza].item()}회**, "
          f"T=5 → **{counts[5.0][pizza].item()}회** (1000회 중)")
    print(f"           pizza 이론 확률: T=1 → {dists[1.0][pizza].item()*100:.4f}%, "
          f"T=5 → {dists[5.0][pizza].item()*100:.2f}%")
    print(f"[검증 답] T=0.1 의 forward 확률 = {dists[0.1][argmax_id].item():.8f} "
          f"→ 사실상 greedy")

    # -----------------------------------------------------------------
    print()
    print("=" * 74)
    print("P10-2 — top-k 마스킹")
    print("=" * 74)

    top_logits, top_pos = torch.topk(NEXT_TOKEN_LOGITS, 3)
    print(f"torch.topk(logits, 3)")
    print(f"  values  : {top_logits.tolist()}")
    print(f"  indices : {top_pos.tolist()}")
    print("  → 단어  : " + ", ".join(
        f"{v:.2f}({INVERSE_VOCAB[int(p)]})" for v, p in zip(top_logits, top_pos)))

    masked = topk_mask(NEXT_TOKEN_LOGITS, 3)
    print()
    print(f"마스킹 로짓: {masked.tolist()}")

    probs_masked = torch.softmax(masked, dim=0)
    print()
    print(f"{'단어':<9}{'로짓':>8}{'마스킹후':>12}{'softmax':>14}")
    print("-" * 43)
    for i in range(len(VOCAB)):
        m = masked[i].item()
        print(f"{INVERSE_VOCAB[i]:<9}{NEXT_TOKEN_LOGITS[i]:>8.2f}"
              f"{('-inf' if m == float('-inf') else f'{m:.2f}'):>12}"
              f"{probs_masked[i].item():>14.6f}")

    zeros = [INVERSE_VOCAB[i] for i in range(len(VOCAB))
             if probs_masked[i].item() == 0.0]
    survivors = [i for i in range(len(VOCAB)) if probs_masked[i].item() != 0.0]
    print()
    print(f"[검증 답] 살아남은 로짓 3개: " + ", ".join(
        f"{NEXT_TOKEN_LOGITS[i]:.2f}({INVERSE_VOCAB[i]})" for i in survivors))
    print(f"[검증 답] softmax 후 정확히 0.0 인 자리: {len(zeros)}개 {zeros}")
    print(f"[검증 답] 남은 3개 확률 합 = {sum(probs_masked[i].item() for i in survivors):.10f}")
    print(f"           (torch 비교) 전체 합 == 1.0 : "
          f"{torch.isclose(probs_masked.sum(), torch.tensor(1.0)).item()}")

    # -----------------------------------------------------------------
    print()
    print("=" * 74)
    print("P10-3 — generate 통합 + (T × k) 그리드")
    print("=" * 74)

    import tiktoken

    from common import (MODEL_10EP, VERDICT, device, text_to_token_ids,
                        token_ids_to_text)
    from gpt_model import GPT_CONFIG_124M, GPTModel

    CFG = dict(GPT_CONFIG_124M, context_length=256)
    tokenizer = tiktoken.get_encoding("gpt2")

    model = GPTModel(CFG)
    model.load_state_dict(torch.load(MODEL_10EP, map_location="cpu"))
    model.to(device)
    model.eval()
    print(f"9주차 모델 로드 완료 (device={device})")

    START = "Every effort moves you"
    start_ids = text_to_token_ids(START, tokenizer).to(device)

    TEMPS_G = [0.5, 1.0, 1.4]
    TOPKS = [None, 25, 50]

    grid = {}
    for T in TEMPS_G:
        for k in TOPKS:
            torch.manual_seed(123)        # 각 조합 직전 시드 재설정
            out = generate(model, start_ids, max_new_tokens=30,
                           context_size=CFG["context_length"],
                           temperature=T, top_k=k)
            grid[(T, k)] = token_ids_to_text(out, tokenizer)

    for T in TEMPS_G:
        for k in TOPKS:
            print(f"\n--- T={T}, top_k={k} ---")
            print(grid[(T, k)])

    # 원문과의 겹침 정도를 정량화해 "암기 재현이 가장 강한 조합"을 근거로 짚는다
    with open(VERDICT, "r", encoding="utf-8") as f:
        norm_orig = " ".join(f.read().split())

    def longest_match(text):
        """생성문 중 원문에 그대로 존재하는 가장 긴 연속 단어 수."""
        w = " ".join(text.split()).split()
        best = 0
        for i in range(len(w)):
            for j in range(len(w), i + best, -1):
                if norm_orig.find(" ".join(w[i:j])) >= 0:
                    best = j - i
                    break
        return best

    orig_words = set(w.strip('.,;:!?"\'()-').lower() for w in norm_orig.split())

    def oov_ratio(text):
        """생성문 단어 중 원문에 아예 없는 단어의 비율 — '혼란도'의 2차 지표.

        최장 일치가 동률일 때 어느 쪽이 더 무너졌는지 가르는 데 쓴다.
        원문에 없는 단어가 많다는 것은 모델이 암기 궤도를 완전히 이탈했다는 뜻이다.
        """
        w = [x.strip('.,;:!?"\'()-').lower() for x in text.split()]
        w = [x for x in w if x]
        return sum(1 for x in w if x not in orig_words) / len(w)

    scores = {key: longest_match(txt) for key, txt in grid.items()}
    oov = {key: oov_ratio(txt) for key, txt in grid.items()}

    print()
    print("--- 원문 최장 연속 일치(단어 수) / 원문에 없는 단어 비율 ---")
    print("| T \\ top_k | " + " | ".join(str(k) for k in TOPKS) + " |")
    print("|---|---|---|---|")
    for T in TEMPS_G:
        print(f"| {T} | " + " | ".join(
            f"{scores[(T, k)]}단어 / {oov[(T, k)]*100:.0f}%" for k in TOPKS) + " |")

    # 1순위 최장 일치, 2순위 원문 이탈률(낮을수록 암기적)
    best_key = max(scores, key=lambda kk: (scores[kk], -oov[kk]))
    worst_key = min(scores, key=lambda kk: (scores[kk], -oov[kk]))
    print(f"\n[검증 답] 암기 재현 최강 조합 : T={best_key[0]}, top_k={best_key[1]} "
          f"(최장 연속 {scores[best_key]}단어, 원문 이탈 {oov[best_key]*100:.0f}%)")
    print(f"[검증 답] 가장 창의적(혼란) 조합: T={worst_key[0]}, top_k={worst_key[1]} "
          f"(최장 연속 {scores[worst_key]}단어, 원문 이탈 {oov[worst_key]*100:.0f}%)")

    same_row = all(grid[(0.5, None)] == grid[(0.5, k)] for k in TOPKS)
    print(f"[관찰]   T=0.5 행의 세 출력이 완전히 동일한가: {same_row}")

    # sampling_grid.md 저장
    lines = ["# sampling_grid.md — (temperature × top_k) 그리드 (P10-3 산출물)", ""]
    lines.append(f"모델: 9주차 `model_10ep.pth` (the-verdict 10에폭) / "
                 f"시작 문자열 `\"{START}\"` / 30 토큰 / 각 조합 직전 `torch.manual_seed(123)`")
    lines.append("")
    lines.append("## 3 × 3 생성 결과")
    lines.append("")
    lines.append("| T \\ top_k | " + " | ".join(str(k) for k in TOPKS) + " |")
    lines.append("|---|---|---|---|")
    for T in TEMPS_G:
        cells = []
        for k in TOPKS:
            cells.append(grid[(T, k)].replace("\n", " ").replace("|", "\\|").strip())
        lines.append(f"| **T={T}** | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## 정량 지표 — 원문 최장 연속 일치(단어) / 원문에 없는 단어 비율")
    lines.append("")
    lines.append("| T \\ top_k | " + " | ".join(str(k) for k in TOPKS) + " |")
    lines.append("|---|---|---|---|")
    for T in TEMPS_G:
        lines.append(f"| **T={T}** | " + " | ".join(
            f"{scores[(T, k)]}단어 / {oov[(T, k)]*100:.0f}%" for k in TOPKS) + " |")
    lines.append("")
    lines.append(f"- 암기 재현이 가장 강한 조합: **T={best_key[0]}, top_k={best_key[1]}** "
                 f"(최장 연속 {scores[best_key]}단어, 원문 이탈 {oov[best_key]*100:.0f}%)")
    lines.append(f"- 가장 창의적(=혼란한) 조합: **T={worst_key[0]}, top_k={worst_key[1]}** "
                 f"(최장 연속 {scores[worst_key]}단어, 원문 이탈 {oov[worst_key]*100:.0f}%)")
    lines.append("")
    lines.append("## 관찰")
    lines.append("")
    lines.append(f"**아래로 갈수록(T 증가) 문장이 무너진다.** top_k=None 열의 원문 이탈률이 "
                 f"{oov[(0.5, None)]*100:.0f}% → {oov[(1.0, None)]*100:.0f}% → "
                 f"{oov[(1.4, None)]*100:.0f}% 로 오른다. T=1.4·k=None 출력에는 "
                 f"`ConfederingAnnaenez`, `STAT`, `Role`, `shrimp` 같이 이 소설에 "
                 f"존재할 수 없는 토큰이 섞인다 — 로짓 차이가 눌리면서 확률 0.01% 짜리 "
                 f"토큰까지 추첨 대상이 되기 때문이다. 한 번 궤도를 벗어나면 그 토큰이 "
                 f"다음 스텝의 문맥이 되어 이탈이 연쇄된다.")
    lines.append("")
    lines.append(f"**옆으로 갈수록(k 증가) 효과는 T 에 종속된다.** "
                 f"T=0.5 행은 top_k None/25/50 세 출력이 **완전히 동일**하다"
                 f"{'(측정 확인)' if same_row else ''}. 분포가 이미 뾰족해 상위 25개가 "
                 f"확률질량을 거의 전부 차지하므로, 마스킹을 해도 같은 시드에서 같은 토큰이 "
                 f"뽑힌다. 반대로 T=1.4 행에서는 k=None(이탈 {oov[(1.4, None)]*100:.0f}%) 과 "
                 f"k=25(이탈 {oov[(1.4, 25)]*100:.0f}%) 가 뚜렷이 갈린다. "
                 f"**top_k 는 헛소리의 하한선을 막는 안전장치이고, 문체를 바꾸는 다이얼은 T 다.**")
    lines.append("")
    lines.append(f"**과적합 모델의 '창의성'은 대부분 '덜 정확한 암기'다.** "
                 f"T={worst_key[0]}·k={worst_key[1]} 조합의 출력도 새 아이디어가 아니라 "
                 f"원문 구절 조각(`I blocked the usual`, `as terrace`)을 잘못 이어 붙인 "
                 f"결과다. 이 모델이 본 데이터는 소설 한 권뿐이므로 '새 조합'을 만들 재료 "
                 f"자체가 없다 — 온도를 올려 얻는 것은 창의성이 아니라 손상이다.")

    with open("sampling_grid.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n[저장] sampling_grid.md")
