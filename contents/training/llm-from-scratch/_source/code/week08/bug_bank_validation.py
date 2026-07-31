"""W08-G3 — 교재 8.7절 실기 버그 은행 10종의 삽입·검출 가능성 전수 검증.

조교 관점의 출제 검증이다. 각 버그를 실제로 심고, "학기 자산"(성질 테스트·정답지 수치)이
그 버그를 실제로 잡아내는지 확인한다. 잡히지 않는 버그는 출제하면 안 된다.

각 버그마다 보고하는 것:
  · 삽입 방법 (원본 코드 → 변형 코드)
  · 검출 수단 (어느 주차의 어떤 자산이 잡는가)
  · 검출 결과 (수치 증거)
"""
import sys
from pathlib import Path

import tiktoken
import torch
import torch.nn as nn

_HERE = Path(__file__).resolve().parent
for w in ("week03", "week04", "week05", "week06", "week07"):
    sys.path.insert(0, str(_HERE.parent / w))

results = []


def report(num, target, bug, detector, detected, evidence):
    results.append((num, target, bug, detector, detected, evidence))
    mark = "검출 O" if detected else "검출 X"
    print(f"\n[{num}] {target} — {bug}")
    print(f"    검출 수단: {detector}")
    print(f"    결과: {mark}")
    print(f"    증거: {evidence}")


# ==========================================================================
# #1 데이터로더 — target 을 한 칸이 아니라 두 칸 밀기
# ==========================================================================
from torch.utils.data import Dataset  # noqa: E402


class DatasetBug1(Dataset):
    def __init__(self, txt, tokenizer, max_length, stride):
        self.input_ids, self.target_ids = [], []
        ids = tokenizer.encode(txt)
        for i in range(0, len(ids) - max_length - 1, stride):
            self.input_ids.append(torch.tensor(ids[i:i + max_length]))
            # BUG: +1 이어야 하는데 +2
            self.target_ids.append(torch.tensor(ids[i + 2:i + max_length + 2]))

    def __len__(self):
        return len(self.input_ids)

    def __getitem__(self, i):
        return self.input_ids[i], self.target_ids[i]


tok = tiktoken.get_encoding("gpt2")
text = open(_HERE.parent / "week03" / "the-verdict.txt", encoding="utf-8").read()

ds = DatasetBug1(text, tok, 4, 1)
inp, tgt = ds[0]
shift_ok = inp[1:].tolist() == tgt[:-1].tolist()
report(1, "데이터로더", "target 을 두 칸 밀기",
       "3주차 V3-1 시프트 assert (input[1:] == target[:-1])",
       not shift_ok,
       f"input={inp.tolist()}, target={tgt.tolist()} → "
       f"input[1:]={inp[1:].tolist()} vs target[:-1]={tgt[:-1].tolist()} 불일치")

# ==========================================================================
# #2 데이터로더 — range 끝을 len(ids) 로 잡아 마지막 청크 초과
# ==========================================================================
class DatasetBug2(Dataset):
    def __init__(self, txt, tokenizer, max_length, stride):
        self.input_ids, self.target_ids = [], []
        ids = tokenizer.encode(txt)
        for i in range(0, len(ids), stride):          # BUG: - max_length 누락
            self.input_ids.append(torch.tensor(ids[i:i + max_length]))
            self.target_ids.append(torch.tensor(ids[i + 1:i + max_length + 1]))

    def __len__(self):
        return len(self.input_ids)

    def __getitem__(self, i):
        return self.input_ids[i], self.target_ids[i]


ds2 = DatasetBug2(text, tok, 4, 1)
n_expected = len(range(0, len(tok.encode(text)) - 4, 1))
last_len = len(ds2[len(ds2) - 1][0])
report(2, "데이터로더", "range 끝을 len(ids) 로 잡아 마지막 청크 초과",
       "3주차 그리드 실험 샘플 수 정답지(5,141) + 마지막 청크 길이 검사",
       len(ds2) != n_expected or last_len != 4,
       f"len(dataset)={len(ds2)} (정답 {n_expected}), "
       f"마지막 샘플 길이={last_len} (기대 4) → 길이 0 청크까지 생성")

# ==========================================================================
# #3 어텐션 — √d 스케일링 생략
# ==========================================================================
from inputs import inputs  # noqa: E402
from multihead import MultiHeadAttention  # noqa: E402


class MHABugNoScale(MultiHeadAttention):
    def forward(self, x):
        b, T, _ = x.shape
        q = self.W_query(x).view(b, T, self.num_heads, self.head_dim).transpose(1, 2)
        k = self.W_key(x).view(b, T, self.num_heads, self.head_dim).transpose(1, 2)
        v = self.W_value(x).view(b, T, self.num_heads, self.head_dim).transpose(1, 2)
        s = q @ k.transpose(2, 3)
        s = s.masked_fill(self.mask.bool()[:T, :T], -torch.inf)
        w = torch.softmax(s, dim=-1)          # BUG: / head_dim**0.5 누락
        ctx = (w @ v).transpose(1, 2).contiguous().view(b, T, self.d_out)
        return self.out_proj(ctx)


torch.manual_seed(123)
ref = MultiHeadAttention(768, 768, 128, 0.0, 12).eval()
bug3 = MHABugNoScale(768, 768, 128, 0.0, 12).eval()
bug3.load_state_dict(ref.state_dict())
x = torch.randn(1, 128, 768) * 1.0
with torch.no_grad():
    o_ref, o_bug = ref(x), bug3(x)
diff3 = (o_ref - o_bug).abs().max().item()
# 4주차 실험 자산: 스케일링 없으면 분포가 원-핫에 가까워진다 → 엔트로피로 잡는다
with torch.no_grad():
    q = ref.W_query(x).view(1, 128, 12, 64).transpose(1, 2)
    k = ref.W_key(x).view(1, 128, 12, 64).transpose(1, 2)
    s = q @ k.transpose(2, 3)
    s = s.masked_fill(ref.mask.bool()[:128, :128], -torch.inf)
    w_scaled = torch.softmax(s / 64 ** 0.5, dim=-1)
    w_unscaled = torch.softmax(s, dim=-1)


def mean_entropy(w):
    p = w.clamp_min(1e-12)
    return float(-(w * p.log()).sum(-1).mean())


report(3, "어텐션", "√d 스케일링 생략",
       "4주차 P4-6 스케일링 실험 자산 (분포 엔트로피) + 기준 구현 차등 테스트",
       diff3 > 1e-4,
       f"출력 최대 오차 {diff3:.4f}; 평균 엔트로피 스케일 있음 "
       f"{mean_entropy(w_scaled):.4f} vs 없음 {mean_entropy(w_unscaled):.4f} "
       f"(원-핫에 가까워짐)")

# ==========================================================================
# #4 어텐션 — softmax dim=-2
# ==========================================================================
class MHABugDim(MultiHeadAttention):
    def forward(self, x):
        b, T, _ = x.shape
        q = self.W_query(x).view(b, T, self.num_heads, self.head_dim).transpose(1, 2)
        k = self.W_key(x).view(b, T, self.num_heads, self.head_dim).transpose(1, 2)
        v = self.W_value(x).view(b, T, self.num_heads, self.head_dim).transpose(1, 2)
        s = q @ k.transpose(2, 3)
        s = s.masked_fill(self.mask.bool()[:T, :T], -torch.inf)
        w = torch.softmax(s / self.head_dim ** 0.5, dim=-2)   # BUG
        ctx = (w @ v).transpose(1, 2).contiguous().view(b, T, self.d_out)
        return self.out_proj(ctx)


def causal_check(model, T=6, d_in=3):
    """5주차 V5-2 test_causal_invariance 를 함수화."""
    xx = torch.rand(2, T, d_in)
    xm = xx.clone()
    xm[:, -1, :] = torch.rand(2, d_in) + 10.0
    with torch.no_grad():
        a, b = model(xx), model(xm)
    t = 2
    return torch.allclose(a[:, :t + 1, :], b[:, :t + 1, :], atol=1e-6)


torch.manual_seed(123)
ref_s = MultiHeadAttention(3, 4, 6, 0.0, 2).eval()
bug4 = MHABugDim(3, 4, 6, 0.0, 2).eval()
bug4.load_state_dict(ref_s.state_dict())
xs = torch.rand(2, 6, 3)
with torch.no_grad():
    q = bug4.W_query(xs).view(2, 6, 2, 2).transpose(1, 2)
    k = bug4.W_key(xs).view(2, 6, 2, 2).transpose(1, 2)
    s = (q @ k.transpose(2, 3)).masked_fill(bug4.mask.bool()[:6, :6], -torch.inf)
    w_bug = torch.softmax(s / 2 ** 0.5, dim=-2)
rowsum = w_bug[0, 0].sum(-1)
report(4, "어텐션", "softmax dim=-2",
       "5주차 V5-2 인과성 테스트 + 가중치 행 합 == 1 검사",
       (not causal_check(bug4)) or (not torch.allclose(rowsum, torch.ones(6), atol=1e-6)),
       f"인과성 {'PASS' if causal_check(bug4) else 'FAIL'}; "
       f"행 합 {[round(float(v),4) for v in rowsum]} (1이 아니다)")

# ==========================================================================
# #5 코잘 — 마스크를 -inf 대신 0 으로 채움
# ==========================================================================
class MHABugZeroMask(MultiHeadAttention):
    def forward(self, x):
        b, T, _ = x.shape
        q = self.W_query(x).view(b, T, self.num_heads, self.head_dim).transpose(1, 2)
        k = self.W_key(x).view(b, T, self.num_heads, self.head_dim).transpose(1, 2)
        v = self.W_value(x).view(b, T, self.num_heads, self.head_dim).transpose(1, 2)
        s = q @ k.transpose(2, 3)
        s = s.masked_fill(self.mask.bool()[:T, :T], 0.0)     # BUG: -inf 여야 한다
        w = torch.softmax(s / self.head_dim ** 0.5, dim=-1)
        ctx = (w @ v).transpose(1, 2).contiguous().view(b, T, self.d_out)
        return self.out_proj(ctx)


torch.manual_seed(123)
bug5 = MHABugZeroMask(3, 4, 6, 0.0, 2).eval()
bug5.load_state_dict(ref_s.state_dict())
with torch.no_grad():
    q = bug5.W_query(xs).view(2, 6, 2, 2).transpose(1, 2)
    k = bug5.W_key(xs).view(2, 6, 2, 2).transpose(1, 2)
    s = (q @ k.transpose(2, 3)).masked_fill(bug5.mask.bool()[:6, :6], 0.0)
    w5 = torch.softmax(s / 2 ** 0.5, dim=-1)
leak5 = float((w5[0, 0] * bug5.mask[:6, :6]).sum())
report(5, "코잘", "마스크를 -inf 대신 0 으로 채움",
       "5주차 V5-1 (e⁰=1) + 인과성 테스트",
       (not causal_check(bug5)) or leak5 > 1e-6,
       f"인과성 {'PASS' if causal_check(bug5) else 'FAIL'}; "
       f"미래 위치 가중치 합 {leak5:.6f} (0이어야 한다)")

# ==========================================================================
# #6 코잘 — tril/triu 뒤바꿈 (미래만 보는 모델)
# ==========================================================================
class MHABugFlipMask(MultiHeadAttention):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        T = self.mask.shape[0]
        # BUG: triu(diagonal=1) 대신 tril(diagonal=-1) — 과거를 가린다
        self.mask.data = torch.tril(torch.ones(T, T), diagonal=-1)


torch.manual_seed(123)
bug6 = MHABugFlipMask(3, 4, 6, 0.0, 2).eval()
sd = dict(ref_s.state_dict())
sd.pop("mask", None)
bug6.load_state_dict(sd, strict=False)
report(6, "코잘", "tril/triu 뒤바꿈 (미래만 보는 모델)",
       "5주차 V5-2 인과성 테스트",
       not causal_check(bug6),
       f"인과성 {'PASS' if causal_check(bug6) else 'FAIL'} — "
       f"미래 토큰을 바꾸면 과거 출력이 변한다")

# ==========================================================================
# #7 MHA — transpose 누락 후 reshape (shape 은 맞는데 값이 오염)
# ==========================================================================
class MHABugNoTranspose(MultiHeadAttention):
    def forward(self, x):
        b, T, _ = x.shape
        q = self.W_query(x).view(b, T, self.num_heads, self.head_dim).transpose(1, 2)
        k = self.W_key(x).view(b, T, self.num_heads, self.head_dim).transpose(1, 2)
        v = self.W_value(x).view(b, T, self.num_heads, self.head_dim).transpose(1, 2)
        s = q @ k.transpose(2, 3)
        s = s.masked_fill(self.mask.bool()[:T, :T], -torch.inf)
        w = torch.softmax(s / self.head_dim ** 0.5, dim=-1)
        ctx = w @ v                                     # [b, heads, T, head_dim]
        # BUG: .transpose(1,2) 누락하고 바로 reshape → 헤드/토큰 축이 섞인다
        ctx = ctx.contiguous().view(b, T, self.d_out)
        return self.out_proj(ctx)


torch.manual_seed(123)
bug7 = MHABugNoTranspose(3, 4, 6, 0.0, 2).eval()
bug7.load_state_dict(ref_s.state_dict())
with torch.no_grad():
    o_ref7, o_bug7 = ref_s(xs), bug7(xs)
shape_same = o_ref7.shape == o_bug7.shape
diff7 = (o_ref7 - o_bug7).abs().max().item()
report(7, "MHA", "transpose 누락 후 reshape (조용히 값만 오염)",
       "5주차 V5-2 인과성 테스트 + 기준 구현 차등 테스트",
       (not causal_check(bug7)) or diff7 > 1e-6,
       f"shape 동일 {shape_same} (오류 안 남!), 출력 최대 오차 {diff7:.4f}, "
       f"인과성 {'PASS' if causal_check(bug7) else 'FAIL'}")

# ==========================================================================
# #8 블록 — 잔차 덧셈 누락
# ==========================================================================
from layers import FeedForward, LayerNorm  # noqa: E402
from transformer_block import GPT_CONFIG_124M  # noqa: E402


class BlockBugNoResidual(nn.Module):
    def __init__(self, cfg):
        super().__init__()
        self.att = MultiHeadAttention(cfg["emb_dim"], cfg["emb_dim"],
                                      cfg["context_length"], cfg["drop_rate"],
                                      cfg["n_heads"], cfg["qkv_bias"])
        self.ff = FeedForward(cfg)
        self.norm1 = LayerNorm(cfg["emb_dim"])
        self.norm2 = LayerNorm(cfg["emb_dim"])
        self.drop = nn.Dropout(cfg["drop_rate"])

    def forward(self, x):
        x = x + self.drop(self.att(self.norm1(x)))
        x = self.drop(self.ff(self.norm2(x)))    # BUG: + shortcut 누락
        return x


cfg8 = dict(GPT_CONFIG_124M, context_length=16, drop_rate=0.0)
torch.manual_seed(123)
blk_bug = BlockBugNoResidual(cfg8)
x8 = torch.rand(1, 8, 768, requires_grad=True)
blk_bug(x8).sum().backward()
g_bug = x8.grad.abs().mean().item()

sys.path.insert(0, str(_HERE.parent / "week06"))
from transformer_block import TransformerBlock  # noqa: E402
torch.manual_seed(123)
blk_ref = TransformerBlock(cfg8)
x8b = torch.rand(1, 8, 768, requires_grad=True)
blk_ref(x8b).sum().backward()
g_ref = x8b.grad.abs().mean().item()

report(8, "블록", "잔차 덧셈 누락 (x = Dropout(FF(LN(x))))",
       "6주차 P6-4 기울기 측정 자산 (입력 기울기 크기 비교)",
       g_bug < g_ref * 0.5,
       f"입력 기울기 절대평균: 정상 {g_ref:.6f} vs 버그 {g_bug:.6f} "
       f"({g_bug/g_ref:.4f}배로 감소)")

# ==========================================================================
# #9 GPT — 위치 임베딩 덧셈 누락
# ==========================================================================
from gpt_model import GPTModel  # noqa: E402


class GPTBugNoPos(GPTModel):
    def forward(self, in_idx):
        _, seq_len = in_idx.shape
        x = self.tok_emb(in_idx)          # BUG: + pos_emb 누락
        x = self.drop_emb(x)
        x = self.trf_blocks(x)
        x = self.final_norm(x)
        return self.out_head(x)


cfg9 = dict(GPT_CONFIG_124M, n_layers=1, context_length=16, drop_rate=0.0)
torch.manual_seed(123)
m9 = GPTBugNoPos(cfg9).eval()
# 3주차 P3-5 자산: 같은 토큰이 두 위치에 있을 때 표현이 달라야 한다
ids9 = torch.tensor([[262, 3797, 290, 262, 3290]])   # ' the' 가 위치 0, 3
with torch.no_grad():
    h_tok = m9.tok_emb(ids9)
same_no_pos = torch.equal(h_tok[0, 0], h_tok[0, 3])
# 위치 임베딩이 실제로 쓰였는지: pos_emb 기울기가 흐르는가
m9b = GPTBugNoPos(cfg9)
m9b(ids9).sum().backward()
pos_grad = m9b.pos_emb.weight.grad
pos_unused = pos_grad is None or float(pos_grad.abs().sum()) == 0.0
report(9, "GPT", "위치 임베딩 덧셈 누락",
       "3주차 P3-5 위치 실험 자산 + pos_emb 기울기 검사",
       pos_unused,
       f"같은 토큰 두 위치의 표현 동일 {same_no_pos}; "
       f"pos_emb 기울기 총합 {0.0 if pos_grad is None else float(pos_grad.abs().sum()):.6f} "
       f"→ 위치 임베딩이 전혀 학습되지 않는다")

# ==========================================================================
# #10 생성 — argmax 를 마지막 위치가 아닌 전체에 적용
# ==========================================================================
def generate_bug10(model, idx, max_new_tokens, context_size):
    for _ in range(max_new_tokens):
        idx_cond = idx[:, -context_size:]
        with torch.no_grad():
            logits = model(idx_cond)
        # BUG: logits[:, -1, :] 로 마지막 위치를 취하지 않고 전체에 argmax
        idx_next = torch.argmax(logits, dim=-1)[:, -1:]
        idx = torch.cat((idx, idx_next), dim=1)
    return idx


from generate import generate_text_simple  # noqa: E402

cfg10 = dict(GPT_CONFIG_124M, n_layers=1, context_length=32, drop_rate=0.0)
torch.manual_seed(123)
m10 = GPTModel(cfg10).eval()
start = torch.tensor([[15496, 11, 314, 716]])
out_ref10 = generate_text_simple(m10, start, 5, 32)
out_bug10 = generate_bug10(m10, start, 5, 32)
# 이 버그는 "우연히 같은 값"이 될 수 있다 — 그래서 여러 시작점으로 확인한다
diffs = []
for seed_ids in ([[15496, 11, 314, 716]], [[40, 2497, 262, 3797]], [[1, 2, 3, 4, 5, 6]]):
    st = torch.tensor(seed_ids)
    a = generate_text_simple(m10, st, 5, 32)
    b = generate_bug10(m10, st, 5, 32)
    diffs.append(torch.equal(a, b))
report(10, "생성", "argmax 를 마지막 위치가 아닌 전체에 적용",
       "7주차 V7-2 생성 자산 + 기준 구현 차등 테스트 (여러 시작점)",
       not all(diffs),
       f"3개 시작점 중 결과가 같은 경우 {sum(diffs)}/3 — "
       f"다르면 검출됨. 첫 시작점: ref={out_ref10[0].tolist()} vs bug={out_bug10[0].tolist()}")

# ==========================================================================
# 종합
# ==========================================================================
print()
print("=" * 78)
print("W08-G3 종합 — 버그 은행 10종의 검출 가능성")
print("=" * 78)
print("| # | 대상 | 버그 | 검출 |")
print("|---|---|---|---|")
for num, target, bug, detector, detected, ev in results:
    print(f"| {num} | {target} | {bug} | {'O' if detected else '**X**'} |")
undetected = [r for r in results if not r[4]]
print()
print(f"검출 성공 {len(results) - len(undetected)}/{len(results)}")
if undetected:
    print("검출 실패 항목 (출제 부적합):")
    for num, target, bug, detector, detected, ev in undetected:
        print(f"  #{num} {target} — {bug}: {ev}")
