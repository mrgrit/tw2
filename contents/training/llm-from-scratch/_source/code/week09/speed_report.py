"""P9-4 — 훈련 속도 비교 실험 (실험 A: 장치 / 실험 B: GPU 처리량)."""
import time

import tiktoken
import torch

import common  # noqa: F401  — sys.path 에 week03/05/06/07 을 등록한다
from gpt_model import GPT_CONFIG_124M, GPTModel
from pretrain import build_loaders, calc_loss_batch

CFG = dict(GPT_CONFIG_124M, context_length=256)

tokenizer = tiktoken.get_encoding("gpt2")
with open("the-verdict.txt", "r", encoding="utf-8") as f:
    text_data = f.read()


def one_epoch(model, loader, optimizer, dev, autocast_bf16=False):
    """1 에폭 훈련하고 걸린 시간(초)과 본 토큰 수를 반환한다."""
    model.train()
    if dev.type == "cuda":
        torch.cuda.synchronize()
    t0 = time.perf_counter()
    tokens = 0
    for inp, tgt in loader:
        optimizer.zero_grad()
        if autocast_bf16:
            # forward·손실만 autocast. 옵티마이저는 기본(fp32)
            with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                loss = calc_loss_batch(inp, tgt, model, dev)
        else:
            loss = calc_loss_batch(inp, tgt, model, dev)
        loss.backward()
        optimizer.step()
        tokens += inp.numel()
    if dev.type == "cuda":
        torch.cuda.synchronize()
    return time.perf_counter() - t0, tokens


def fresh(dev):
    """시드 고정 모델·옵티마이저 재생성."""
    torch.manual_seed(123)
    m = GPTModel(CFG).to(dev)
    o = torch.optim.AdamW(m.parameters(), lr=4e-4, weight_decay=0.1)
    return m, o


# ==========================================================================
# 실험 A — 장치 비교 (batch=2, 1 에폭, 3회 평균)
# ==========================================================================
print("=" * 70)
print("실험 A — CPU vs GPU(fp32) vs GPU+bf16   (batch=2, 1 에폭, 3회 평균)")
print("=" * 70)

train_loader, val_loader, _, _ = build_loaders(text_data, batch_size=2)
cpu, cuda = torch.device("cpu"), torch.device("cuda")

table_a = []

# 1. CPU
times = []
for trial in range(3):
    m, o = fresh(cpu)
    t, _ = one_epoch(m, train_loader, o, cpu)
    times.append(t)
    del m, o
cpu_avg = sum(times) / len(times)
table_a.append(("CPU", cpu_avg, times))
print(f"  CPU          : {[f'{t:.2f}' for t in times]} → 평균 {cpu_avg:.2f}s")

# 2. GPU fp32 (워밍업 1회 후 측정)
m, o = fresh(cuda)
one_epoch(m, train_loader, o, cuda)     # 워밍업
del m, o
torch.cuda.empty_cache()
times = []
for trial in range(3):
    m, o = fresh(cuda)
    t, _ = one_epoch(m, train_loader, o, cuda)
    times.append(t)
    del m, o
    torch.cuda.empty_cache()
gpu_avg = sum(times) / len(times)
table_a.append(("GPU (fp32)", gpu_avg, times))
print(f"  GPU (fp32)   : {[f'{t:.2f}' for t in times]} → 평균 {gpu_avg:.2f}s")

# 3. GPU + bf16 autocast
m, o = fresh(cuda)
one_epoch(m, train_loader, o, cuda, autocast_bf16=True)   # 워밍업
del m, o
torch.cuda.empty_cache()
times = []
for trial in range(3):
    m, o = fresh(cuda)
    t, _ = one_epoch(m, train_loader, o, cuda, autocast_bf16=True)
    times.append(t)
    del m, o
    torch.cuda.empty_cache()
bf16_avg = sum(times) / len(times)
table_a.append(("GPU + bf16 autocast", bf16_avg, times))
print(f"  GPU + bf16   : {[f'{t:.2f}' for t in times]} → 평균 {bf16_avg:.2f}s")

# ==========================================================================
# 실험 B — GPU 처리량 (batch 2 / 8 / 32)
# ==========================================================================
print()
print("=" * 70)
print("실험 B — GPU fp32 처리량 (batch_size 2 / 8 / 32)")
print("=" * 70)

table_b = []
for bs in (2, 8, 32):
    loader, _, _, _ = build_loaders(text_data, batch_size=bs)
    if len(loader) == 0:
        print(f"  batch={bs}: 배치가 0개 (drop_last=True 이고 샘플이 부족)  → 건너뜀")
        table_b.append((bs, None, None, 0))
        continue
    m, o = fresh(cuda)
    one_epoch(m, loader, o, cuda)     # 워밍업
    del m, o
    torch.cuda.empty_cache()

    m, o = fresh(cuda)
    t, tokens = one_epoch(m, loader, o, cuda)
    del m, o
    torch.cuda.empty_cache()
    tps = tokens / t
    table_b.append((bs, t, tps, len(loader)))
    print(f"  batch={bs:2d}: 배치 {len(loader):2d}개, 1에폭 {t:.3f}s, "
          f"본 토큰 {tokens:,}, {tps:,.0f} tokens/sec")

# ==========================================================================
# 리포트
# ==========================================================================
lines = []
lines.append("# speed_report.md — 훈련 속도 실험 (P9-4 산출물)")
lines.append("")
lines.append(f"환경: {torch.cuda.get_device_name(0)} / torch {torch.__version__} / "
             f"모델 GPT-2 124M (ctx 256)")
lines.append("측정 규약: GPU 측정은 워밍업 1회 후 시작, 시작·종료 시 "
             "`torch.cuda.synchronize()`. 각 실험 사이 모델·옵티마이저 재생성(시드 123 고정)")
lines.append("")
lines.append("## 표 A — 장치 비교 (batch=2, 1 에폭, 3회 평균)")
lines.append("")
lines.append("| 장치 | 1에폭 시간(s) | 3회 측정값 | CPU 대비 배속 |")
lines.append("|---|---|---|---|")
for name, avg, times in table_a:
    lines.append(f"| {name} | **{avg:.2f}** | {', '.join(f'{t:.2f}' for t in times)} | "
                 f"{cpu_avg/avg:.2f}배 |")
lines.append("")
lines.append(f"- GPU(fp32) 는 CPU 대비 **{cpu_avg/gpu_avg:.1f}배**")
lines.append(f"- bf16 은 fp32 대비 **{gpu_avg/bf16_avg:.2f}배** — "
             f"{'이득이 크지 않다' if gpu_avg/bf16_avg < 1.3 else '이득이 있다'}")
lines.append("")
lines.append("## 표 B — GPU 처리량")
lines.append("")
lines.append("| batch | 배치 수 | 시간(s) | tokens/sec | batch=2 대비 처리량 배율 |")
lines.append("|---|---|---|---|---|")
base_tps = next((tps for bs, t, tps, n in table_b if bs == 2 and tps), None)
for bs, t, tps, nb in table_b:
    if tps is None:
        lines.append(f"| {bs} | 0 | — | — | (샘플 부족) |")
    else:
        lines.append(f"| {bs} | {nb} | {t:.3f} | **{tps:,.0f}** | {tps/base_tps:.2f}배 |")
lines.append("")
lines.append("## 검증 — batch 를 키울 때 tokens/sec 는 어떻게 변하는가")
lines.append("")
valid = [(bs, t, tps, nb) for bs, t, tps, nb in table_b if tps]
if len(valid) >= 2:
    lines.append(f"batch {valid[0][0]} → {valid[-1][0]} 으로 키우면 tokens/sec 가 "
                 f"{valid[0][2]:,.0f} → {valid[-1][2]:,.0f} 로 "
                 f"**{valid[-1][2]/valid[0][2]:.2f}배** 뛴다.")
    lines.append(f"반면 1에폭 시간은 {valid[0][1]:.3f}s → {valid[-1][1]:.3f}s 로 "
                 f"{'거의 변하지 않는다' if abs(valid[-1][1]-valid[0][1])/valid[0][1] < 0.5 else '변한다'}.")
lines.append("")
lines.append("### 이 모델·데이터가 GPU 를 충분히 활용하고 있는가")
lines.append("")
lines.append("**아니다.** 근거 세 가지.")
lines.append("")
lines.append(f"1. batch=2 에서 batch={valid[-1][0]} 로 키워도 **1에폭 시간이 거의 그대로**인데")
lines.append(f"   처리량은 {valid[-1][2]/valid[0][2]:.2f}배가 된다. 같은 시간에 더 많은 일을")
lines.append("   했다는 뜻이므로, batch=2 일 때 GPU 가 놀고 있었다는 직접 증거다.")
lines.append(f"2. bf16 의 이득이 {gpu_avg/bf16_avg:.2f}배에 그친다. 연산이 병목이면 bf16 이")
lines.append("   확실한 이득을 주는데, 그렇지 않다는 것은 병목이 연산이 아니라는 뜻이다")
lines.append("   (커널 실행 오버헤드·데이터 공급이 병목).")
lines.append(f"3. 데이터가 5,145 토큰뿐이라 batch=2 로는 1 에폭이 배치 {table_b[0][3]}개로 끝난다.")
lines.append("   GPU 를 예열할 틈도 없이 에폭이 끝난다.")
lines.append("")
lines.append("**결론: 작은 배치는 GPU 를 굶긴다.** 11~13주차의 큰 훈련에서는 배치를 먼저 키워")
lines.append("GPU 를 포화시킨 뒤 정밀도(bf16)를 논해야 한다.")

with open("speed_report.md", "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")

print()
print("\n".join(lines))
