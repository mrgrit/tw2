"""P9-2 + P9-3 — train/val 분리, 로더 구성, 훈련 루프, 10 에폭 사전 훈련."""
import math
import time

import matplotlib.pyplot as plt
import tiktoken
import torch

from common import device, text_to_token_ids, token_ids_to_text
from dataset import create_dataloader_v1
from generate import generate_text_simple
from gpt_model import GPT_CONFIG_124M, GPTModel

CFG = dict(GPT_CONFIG_124M, context_length=256)
TRAIN_RATIO = 0.90


def build_loaders(text, batch_size=2, max_length=256, stride=256):
    """P9-2 — 90:10 문자 기준 분할 후 로더 2개."""
    split_idx = int(TRAIN_RATIO * len(text))
    train_data, val_data = text[:split_idx], text[split_idx:]

    train_loader = create_dataloader_v1(
        train_data, batch_size=batch_size, max_length=max_length,
        stride=stride, shuffle=True, drop_last=True, num_workers=0,
    )
    val_loader = create_dataloader_v1(
        val_data, batch_size=batch_size, max_length=max_length,
        stride=stride, shuffle=False, drop_last=False, num_workers=0,
    )
    return train_loader, val_loader, train_data, val_data


def calc_loss_batch(input_batch, target_batch, model, device):
    """입력·타깃을 device 로 이동한 뒤 손실 계산."""
    input_batch = input_batch.to(device)
    target_batch = target_batch.to(device)
    logits = model(input_batch)
    return torch.nn.functional.cross_entropy(
        logits.flatten(0, 1), target_batch.flatten()
    )


def calc_loss_loader(data_loader, model, device, num_batches=None):
    """로더 평균 손실 (eval_iter 지원)."""
    total_loss = 0.0
    if len(data_loader) == 0:
        return float("nan")
    num_batches = len(data_loader) if num_batches is None \
        else min(num_batches, len(data_loader))
    for i, (inp, tgt) in enumerate(data_loader):
        if i >= num_batches:
            break
        with torch.no_grad():
            total_loss += calc_loss_batch(inp, tgt, model, device).item()
    return total_loss / num_batches


def evaluate_model(model, train_loader, val_loader, device, eval_iter):
    model.eval()
    with torch.no_grad():
        tr = calc_loss_loader(train_loader, model, device, num_batches=eval_iter)
        va = calc_loss_loader(val_loader, model, device, num_batches=eval_iter)
    model.train()
    return tr, va


def generate_and_print_sample(model, tokenizer, device, start_context,
                              max_new_tokens=50):
    model.eval()
    context_size = model.pos_emb.weight.shape[0]
    encoded = text_to_token_ids(start_context, tokenizer).to(device)
    with torch.no_grad():
        token_ids = generate_text_simple(
            model=model, idx=encoded,
            max_new_tokens=max_new_tokens, context_size=context_size,
        )
    text = token_ids_to_text(token_ids, tokenizer)
    model.train()
    return text.replace("\n", " ")


def train_model_simple(model, train_loader, val_loader, optimizer, device,
                       num_epochs, eval_freq, eval_iter, start_context, tokenizer):
    """P9-3 — 훈련 루프."""
    train_losses, val_losses, track_tokens_seen, epoch_samples = [], [], [], []
    tokens_seen, global_step = 0, -1

    for epoch in range(num_epochs):
        model.train()
        for input_batch, target_batch in train_loader:
            optimizer.zero_grad()
            loss = calc_loss_batch(input_batch, target_batch, model, device)
            loss.backward()
            optimizer.step()
            tokens_seen += input_batch.numel()
            global_step += 1

            if global_step % eval_freq == 0:
                tr, va = evaluate_model(model, train_loader, val_loader,
                                        device, eval_iter)
                train_losses.append(tr)
                val_losses.append(va)
                track_tokens_seen.append(tokens_seen)
                print(f"에폭 {epoch+1} (스텝 {global_step:06d}): "
                      f"train {tr:.3f}, val {va:.3f}")

        sample = generate_and_print_sample(model, tokenizer, device, start_context)
        epoch_samples.append((epoch + 1, sample))
        print(f"  [에폭 {epoch+1} 생성] {sample}")

    return train_losses, val_losses, track_tokens_seen, epoch_samples


if __name__ == "__main__":
    tokenizer = tiktoken.get_encoding("gpt2")
    with open("the-verdict.txt", "r", encoding="utf-8") as f:
        text_data = f.read()

    # ---------------- P9-2 ----------------
    print("=" * 70)
    print("P9-2 — train/val 분리와 로더 구성")
    print("=" * 70)
    train_loader, val_loader, train_data, val_data = build_loaders(text_data)

    total_tokens = len(tokenizer.encode(text_data))
    train_tokens = len(tokenizer.encode(train_data))
    val_tokens = len(tokenizer.encode(val_data))
    print(f"전체 문자 {len(text_data):,} → train {len(train_data):,} / val {len(val_data):,}")
    print(f"전체 토큰 {total_tokens:,} → train {train_tokens:,} / val {val_tokens:,}")
    print()
    print(f"train 배치 수: {len(train_loader)}")
    for x, y in train_loader:
        print(f"  배치 shape: {tuple(x.shape)}, {tuple(y.shape)}")
        break
    print(f"val 배치 수  : {len(val_loader)}")
    for x, y in val_loader:
        print(f"  배치 shape: {tuple(x.shape)}, {tuple(y.shape)}")
        break

    cov_train = len(train_loader) * 2 * 256
    cov_val = len(val_loader) * 2 * 256
    print()
    print(f"커버 토큰 수: train {len(train_loader)} x 2 x 256 = {cov_train:,} / "
          f"val {len(val_loader)} x 2 x 256 = {cov_val:,}")

    print()
    print("--- 손계산 유도 (검증 항목) ---")
    n_train_samples = math.ceil((train_tokens - 256) / 256)
    n_val_samples = math.ceil((val_tokens - 256) / 256)
    print(f"  train 샘플 수 = ⌈({train_tokens} − 256) / 256⌉ = {n_train_samples}")
    print(f"    → batch_size=2, drop_last=True 이므로 배치 수 = "
          f"{n_train_samples} // 2 = {n_train_samples // 2}  (실측 {len(train_loader)})")
    print(f"  val 샘플 수   = ⌈({val_tokens} − 256) / 256⌉ = {n_val_samples}")
    print(f"    → batch_size=2, drop_last=False 이므로 배치 수 = "
          f"⌈{n_val_samples} / 2⌉ = {math.ceil(n_val_samples / 2)}  (실측 {len(val_loader)})")

    # 훈련 전 손실
    torch.manual_seed(123)
    model = GPTModel(CFG)
    model.to(device)
    print()
    print("--- 훈련 전 손실 (GPU) ---")
    model.eval()
    with torch.no_grad():
        tr0 = calc_loss_loader(train_loader, model, device)
        va0 = calc_loss_loader(val_loader, model, device)
    print(f"  train {tr0:.4f}  |  val {va0:.4f}")
    print(f"  미션 1 이론 예언 ln(50257)={math.log(50257):.4f} 와 같은 동네인가: "
          f"{abs(tr0 - math.log(50257)) < 1.0}")

    # ---------------- P9-3 ----------------
    print()
    print("=" * 70)
    print("P9-3 — 10 에폭 사전 훈련")
    print("=" * 70)
    torch.manual_seed(123)
    model = GPTModel(CFG)
    model.to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=4e-4, weight_decay=0.1)

    t0 = time.time()
    train_losses, val_losses, tokens_seen, epoch_samples = train_model_simple(
        model, train_loader, val_loader, optimizer, device,
        num_epochs=10, eval_freq=5, eval_iter=5,
        start_context="Every effort moves you", tokenizer=tokenizer,
    )
    elapsed = time.time() - t0
    print(f"\n훈련 시간: {elapsed:.1f}초")

    # 곡선
    fig, ax1 = plt.subplots(figsize=(9, 5))
    epochs_seen = torch.linspace(0, 10, len(train_losses))
    ax1.plot(epochs_seen, train_losses, label="훈련 손실")
    ax1.plot(epochs_seen, val_losses, linestyle="-.", label="검증 손실")
    ax1.set_xlabel("에폭")
    ax1.set_ylabel("손실")
    ax1.legend(loc="upper right")
    ax1.grid(True, alpha=0.3)

    # 두 곡선이 갈라지기 시작하는 지점: val 손실이 최소가 된 직후
    min_val_i = int(torch.tensor(val_losses).argmin())
    div_epoch = float(epochs_seen[min_val_i])
    ax1.axvline(div_epoch, color="red", linestyle=":", linewidth=1.5)
    ax1.annotate(f"val 최소 후 발산 시작\n(에폭 {div_epoch:.1f}, val {val_losses[min_val_i]:.2f})",
                 xy=(div_epoch, val_losses[min_val_i]),
                 xytext=(div_epoch + 1.2, val_losses[min_val_i] + 1.2),
                 arrowprops=dict(arrowstyle="->", color="red"), color="red")

    ax2 = ax1.twiny()
    ax2.plot(tokens_seen, train_losses, alpha=0)
    ax2.set_xlabel("본 토큰 수 (tokens seen)")
    ax1.set_title("사전 훈련 손실 곡선 (the-verdict.txt, 10 에폭)")
    fig.tight_layout()
    fig.savefig("loss_curve.png", dpi=130)
    print("loss_curve.png 저장")

    torch.save(model.state_dict(), "model_10ep.pth")
    print("model_10ep.pth 저장")

    print()
    print("=== 에폭별 생성 문장 변화 ===")
    for ep, s in epoch_samples:
        print(f"  에폭 {ep:2d}: {s[:110]}")

    print()
    print("=== 최종 손실 ===")
    print(f"  train {train_losses[-1]:.4f}  |  val {val_losses[-1]:.4f}")
    print(f"  train 1 미만인가: {train_losses[-1] < 1.0}")
    print(f"  val 6 초반대인가: {6.0 <= val_losses[-1] < 7.0}")
    print(f"  val 최소값 {min(val_losses):.4f} (에폭 {div_epoch:.1f}) → "
          f"최종 {val_losses[-1]:.4f}, 상승폭 {val_losses[-1]-min(val_losses):+.4f}")
    print(f"  train 퍼플렉시티: {math.exp(train_losses[-1]):.2f}")
    print(f"  val 퍼플렉시티  : {math.exp(val_losses[-1]):.2f}")
