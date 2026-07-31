"""V7-1 + P7-2 — 파라미터 분해표와 weight tying / 메모리 추정."""
import torch

from gpt_model import GPT_CONFIG_124M, GPTModel

torch.manual_seed(123)
model = GPTModel(GPT_CONFIG_124M)

V, D, L, CTX = 50257, 768, 12, 1024

# --- named_parameters 를 그룹별로 실측 ---
groups = {"tok_emb": 0, "pos_emb": 0, "trf_blocks": 0, "final_norm": 0, "out_head": 0}
for name, p in model.named_parameters():
    for key in groups:
        if name.startswith(key):
            groups[key] += p.numel()
            break

# --- 산식 계산 ---
formulas = [
    ("토큰 임베딩", f"{V:,} x {D}", V * D, "tok_emb"),
    ("위치 임베딩", f"{CTX:,} x {D}", CTX * D, "pos_emb"),
    ("블록 x 12", f"7,085,568 x {L}", 7_085_568 * L, "trf_blocks"),
    ("최종 LayerNorm", f"2 x {D}", 2 * D, "final_norm"),
    ("출력 헤드", f"{D} x {V:,}", D * V, "out_head"),
]

lines = []
lines.append("# param_breakdown.md — GPT-2 124M 파라미터 분해 (V7-1 산출물)")
lines.append("")
lines.append("| 구성 요소 | 산식 | 파라미터 수(산식) | 실측치(named_parameters) | 일치 | 누적 합계 |")
lines.append("|---|---|---|---|---|---|")

cumulative = 0
all_match = True
for label, expr, calc, key in formulas:
    measured = groups[key]
    cumulative += calc
    match = "O" if calc == measured else f"**X ({calc - measured:+,})**"
    if calc != measured:
        all_match = False
    lines.append(f"| {label} | {expr} | {calc:,} | {measured:,} | {match} | **{cumulative:,}** |")

total_measured = sum(p.numel() for p in model.parameters())
lines.append(f"| **총합** | | **{cumulative:,}** | **{total_measured:,}** | "
             f"{'O' if cumulative == total_measured else 'X'} | |")
lines.append("")
lines.append(f"총합이 163,009,536 과 일치: **{total_measured == 163_009_536}**")
lines.append("")

# --- P7-2: weight tying 과 메모리 ---
head_params = groups["out_head"]
tied = total_measured - head_params
mem_f32 = total_measured * 4
mem_bf16 = total_measured * 2

lines.append("## weight tying 과 메모리 (P7-2)")
lines.append("")
lines.append("### 1) weight tying 시 파라미터 수")
lines.append("")
lines.append(f"전체 {total_measured:,} − 출력 헤드 {head_params:,} = **{tied:,}**")
lines.append("")
lines.append(f"이 값은 분해표의 **'최종 LayerNorm' 행 누적값**과 정확히 일치한다: "
             f"{V*D + CTX*D + 7_085_568*L + 2*D:,}")
lines.append("")
lines.append("즉 뺄셈으로 구할 필요가 없다 — **표에서 그대로 읽힌다.** 출력 헤드 직전까지의")
lines.append("누적값이 곧 tying 기준 파라미터 수다. 이것이 'GPT-2 124M' 이라는 이름의 유래다.")
lines.append("(교재 구현은 학습 유연성을 위해 임베딩과 출력 헤드를 분리하므로 163M 이 된다.)")
lines.append("")
lines.append("### 2~3) 메모리 크기")
lines.append("")
lines.append("| 정밀도 | 바이트/파라미터 | 총 바이트 | MB | GB |")
lines.append("|---|---|---|---|---|")
lines.append(f"| float32 | 4 | {mem_f32:,} | **{mem_f32/1024**2:.2f}** | {mem_f32/1024**3:.4f} |")
lines.append(f"| bfloat16 | 2 | {mem_bf16:,} | **{mem_bf16/1024**2:.2f}** | {mem_bf16/1024**3:.4f} |")
lines.append("")
lines.append(f"손계산: {total_measured:,} x 4 ÷ 1024² = {mem_f32/1024**2:.2f} MB")
lines.append(f"bf16 은 정확히 절반: {mem_bf16/1024**2:.2f} MB "
             f"(= {mem_f32/1024**2:.2f} / 2)")

with open("param_breakdown.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print("\n".join(lines))
print()
print("=== 게이트 판정 ===")
print(f"W07-G2 총 파라미터 163,009,536 : {total_measured == 163_009_536}")
print(f"W07-G3 분해표 산식==실측 전부  : {all_match}")
print(f"W07-G4 누적 124,412,160        : {V*D + CTX*D + 7_085_568*L + 2*D == 124_412_160}")
print(f"W07-G5 tying 124,412,160       : {tied == 124_412_160}")
print(f"W07-G6 float32 약 621.83MB     : {abs(mem_f32/1024**2 - 621.83) < 0.01}"
      f"  (실측 {mem_f32/1024**2:.2f} MB)")
