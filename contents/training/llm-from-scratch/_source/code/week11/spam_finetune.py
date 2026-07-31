"""P11-3 ~ P11-5 — 개조 수술, 베이스라인, 파인튜닝.

10주차 openai_load.py 를 그대로 재사용해 GPT-2 를 로드한 뒤
헤드를 갈아 끼우고 선택적으로 동결한다.
"""
import time

import tiktoken
import torch

import common  # noqa: F401
from common import WEEK10_WEIGHTS, device

import openai_load                       # 10주차 자산
openai_load.WEIGHTS_DIR = WEEK10_WEIGHTS  # 이미 받아 둔 가중치 재사용

from decoding import generate            # noqa: E402  (10주차)
from spam_data import build_loaders      # noqa: E402

SEED = 123
NUM_CLASSES = 2


def load_and_modify(model_name="gpt2-small (124M)", strategy="b", verbose=True):
    """GPT-2 로드 → 전체 동결 → 헤드 교체 → 전략별 동결 해제.

    strategy: "a" 새 헤드만 / "b" 헤드+마지막 블록+최종LN(교재) / "c" 전층
    """
    gpt, cfg, _ = openai_load.build(model_name)

    # 3. 전체 동결
    for p in gpt.parameters():
        p.requires_grad = False

    # 4. 헤드 교체 — 시드를 헤드 생성 '직전'에 고정해야 재현된다
    torch.manual_seed(SEED)
    gpt.out_head = torch.nn.Linear(cfg["emb_dim"], NUM_CLASSES)

    # 5. 전략별 동결 해제 (새 헤드는 nn.Linear 기본값이 requires_grad=True)
    if strategy == "b":
        for p in gpt.trf_blocks[-1].parameters():
            p.requires_grad = True
        for p in gpt.final_norm.parameters():
            p.requires_grad = True
    elif strategy == "c":
        for p in gpt.parameters():
            p.requires_grad = True

    gpt.to(device)

    if verbose:
        trainable = sum(p.numel() for p in gpt.parameters() if p.requires_grad)
        total = sum(p.numel() for p in gpt.parameters())
        print(f"  훈련 가능 파라미터: {trainable:,} / 전체 {total:,} "
              f"({trainable/total*100:.2f}%)")
    return gpt, cfg


def calc_loss_batch(input_batch, target_batch, model, device):
    """분류 손실 — 마지막 토큰 위치의 로짓만 쓴다."""
    input_batch = input_batch.to(device)
    target_batch = target_batch.to(device)
    logits = model(input_batch)[:, -1, :]      # [B, 2]
    return torch.nn.functional.cross_entropy(logits, target_batch)


def calc_loss_loader(data_loader, model, device, num_batches=None):
    total, n = 0.0, 0
    if len(data_loader) == 0:
        return float("nan")
    num_batches = len(data_loader) if num_batches is None \
        else min(num_batches, len(data_loader))
    for i, (x, y) in enumerate(data_loader):
        if i >= num_batches:
            break
        with torch.no_grad():
            total += calc_loss_batch(x, y, model, device).item()
        n += 1
    return total / n


def calc_accuracy_loader(data_loader, model, device, num_batches=None):
    model.eval()
    correct, total = 0, 0
    num_batches = len(data_loader) if num_batches is None \
        else min(num_batches, len(data_loader))
    for i, (x, y) in enumerate(data_loader):
        if i >= num_batches:
            break
        x, y = x.to(device), y.to(device)
        with torch.no_grad():
            logits = model(x)[:, -1, :]
        pred = torch.argmax(logits, dim=-1)
        correct += (pred == y).sum().item()
        total += pred.shape[0]
    return correct / total if total else float("nan")


def evaluate_model(model, train_loader, val_loader, device, eval_iter):
    model.eval()
    with torch.no_grad():
        tr = calc_loss_loader(train_loader, model, device, num_batches=eval_iter)
        va = calc_loss_loader(val_loader, model, device, num_batches=eval_iter)
    model.train()
    return tr, va


def train_classifier_simple(model, train_loader, val_loader, optimizer, device,
                            num_epochs, eval_freq, eval_iter, use_bf16=False):
    train_losses, val_losses, train_accs, val_accs = [], [], [], []
    examples_seen, global_step = 0, -1

    for epoch in range(num_epochs):
        model.train()
        for x, y in train_loader:
            optimizer.zero_grad()
            if use_bf16:
                with torch.autocast(device_type="cuda", dtype=torch.bfloat16):
                    loss = calc_loss_batch(x, y, model, device)
            else:
                loss = calc_loss_batch(x, y, model, device)
            loss.backward()
            optimizer.step()
            examples_seen += x.shape[0]
            global_step += 1

            if global_step % eval_freq == 0:
                tr, va = evaluate_model(model, train_loader, val_loader,
                                        device, eval_iter)
                train_losses.append(tr)
                val_losses.append(va)
                print(f"에폭 {epoch+1} (스텝 {global_step:06d}): "
                      f"train 손실 {tr:.3f}, val 손실 {va:.3f}")

        tr_acc = calc_accuracy_loader(train_loader, model, device, num_batches=eval_iter)
        va_acc = calc_accuracy_loader(val_loader, model, device, num_batches=eval_iter)
        train_accs.append(tr_acc)
        val_accs.append(va_acc)
        print(f"  훈련 정확도 {tr_acc*100:.2f}% | 검증 정확도 {va_acc*100:.2f}%")

    return train_losses, val_losses, train_accs, val_accs, examples_seen


def classify_review(text, model, tokenizer, device, max_length=120,
                    pad_token_id=50256):
    """V11-2 — 실전 분류 함수."""
    model.eval()
    ids = tokenizer.encode(text)
    ids = ids[:max_length]
    ids += [pad_token_id] * (max_length - len(ids))
    tensor = torch.tensor(ids, device=device).unsqueeze(0)
    with torch.no_grad():
        logits = model(tensor)[:, -1, :]
    return "spam" if int(torch.argmax(logits, dim=-1)) == 1 else "not spam"


# ===========================================================================
if __name__ == "__main__":
    import matplotlib.pyplot as plt

    tokenizer = tiktoken.get_encoding("gpt2")
    train_loader, val_loader, test_loader, *_ = build_loaders(batch_size=8)

    print("=" * 74)
    print("P11-3 — 개조 수술")
    print("=" * 74)

    # 1. 로드
    gpt, cfg, _ = openai_load.build("gpt2-small (124M)")
    print(f"GPT-2 124M 로드 (ctx {cfg['context_length']}, "
          f"qkv_bias {cfg['qkv_bias']})")

    # 2. [개조 전 관찰] 프롬프트로 시켜보기
    from common import device as dev
    from openai_load import text_to_token_ids, token_ids_to_text
    prompt = ("Is the following text 'spam'? Answer with 'yes' or 'no':"
              " 'You are a winner you have been specially selected to receive"
              " $1000 cash.'")
    ids = text_to_token_ids(prompt, tokenizer).to(dev)
    out = generate(gpt, ids, max_new_tokens=30,
                   context_size=cfg["context_length"], temperature=0.0)
    full = token_ids_to_text(out, tokenizer)
    continuation = full[len(prompt):]
    print()
    print("--- [개조 전 관찰] 프롬프트로 시켜보면 ---")
    print(f"프롬프트: {prompt}")
    print(f"이어 쓴 30토큰: {continuation!r}")
    first_word = continuation.strip().split()[0].strip(".,!?'\"").lower() \
        if continuation.strip() else ""
    print(f"첫 단어: {first_word!r}  → yes/no 인가: {first_word in ('yes', 'no')}")
    del gpt
    torch.cuda.empty_cache()

    # 3~6. 개조
    print()
    print("--- 개조 (전체 동결 → 헤드 교체 → 마지막 블록+최종LN 해제) ---")
    model, cfg = load_and_modify("gpt2-small (124M)", strategy="b")

    print()
    print("--- 훈련 가능 파라미터 산식 분해 (7주차 분해표 재사용) ---")
    blk = sum(p.numel() for p in model.trf_blocks[-1].parameters())
    ln = sum(p.numel() for p in model.final_norm.parameters())
    head = sum(p.numel() for p in model.out_head.parameters())
    print(f"  마지막 트랜스포머 블록 : {blk:>10,}")
    print(f"  최종 LayerNorm         : {ln:>10,}  (scale {cfg['emb_dim']} + shift {cfg['emb_dim']})")
    print(f"  새 분류 헤드           : {head:>10,}  "
          f"({cfg['emb_dim']}x{NUM_CLASSES} + {NUM_CLASSES})")
    print(f"  {'-'*38}")
    print(f"  합계                   : {blk+ln+head:>10,}")
    total = sum(p.numel() for p in model.parameters())
    print(f"  전체 대비              : {(blk+ln+head)/total*100:.2f}%")

    # ---------------- P11-4 ----------------
    print()
    print("=" * 74)
    print("P11-4 — 훈련 전 베이스라인 (각 10배치 표본)")
    print("=" * 74)
    base = {}
    for name, ld in (("train", train_loader), ("val", val_loader),
                     ("test", test_loader)):
        acc = calc_accuracy_loader(ld, model, device, num_batches=10)
        base[name] = acc
        print(f"  {name:<6} 정확도: {acc*100:6.2f}%")
    print(f"\n  세 분할 모두 50% 안팎(동전 수준)인가: "
          f"{all(0.3 <= a <= 0.7 for a in base.values())}")

    print("""
[검증] 왜 마지막 토큰만 쓰는가 — 5주차 인과성 테스트와의 연결

5주차 test_causal_invariance 는 "위치 t 의 출력은 t+1 이후 토큰을 바꿔도
변하지 않는다"를 통과시켰다. 코잘 마스크가 미래를 -inf 로 가려 놓았기 때문이다.
그 성질을 뒤집어 읽으면, **시퀀스 전체를 볼 수 있는 위치는 마지막 하나뿐**이다.

첫 토큰의 로짓을 쓰면 모델은 문장의 첫 단어 하나만 보고 스팸 여부를 판단하는
셈이 된다. "Free" 로 시작하면 스팸, "Hey" 로 시작하면 정상 — 이것은 분류기가
아니라 첫 단어 사전이다. 5주차 인과성 테스트가 통과했다는 사실 자체가
"첫 토큰은 뒤를 못 본다"의 증명이므로, 첫 토큰 사용은 원리적으로 틀렸다.

마지막 토큰 위치의 벡터는 어텐션을 통해 앞의 모든 토큰을 가중 평균한 결과다.
분류에 필요한 '문장 전체의 요약'이 거기에 있다. 그래서 model(x)[:, -1, :] 다.""")

    # ---------------- P11-5 ----------------
    print()
    print("=" * 74)
    print("P11-5 — 파인튜닝 실행 (AdamW lr=5e-5, wd=0.1, 5 에폭)")
    print("=" * 74)
    torch.manual_seed(SEED)
    optimizer = torch.optim.AdamW(model.parameters(), lr=5e-5, weight_decay=0.1)
    t0 = time.time()
    tr_losses, va_losses, tr_accs, va_accs, seen = train_classifier_simple(
        model, train_loader, val_loader, optimizer, device,
        num_epochs=5, eval_freq=50, eval_iter=5,
    )
    elapsed = time.time() - t0
    print(f"\n훈련 시간 {elapsed:.1f}초, 본 예제 {seen:,}개")

    # 전체 정확도
    print()
    print("--- 훈련 후 전체 정확도 ---")
    final = {}
    for name, ld in (("train", train_loader), ("val", val_loader),
                     ("test", test_loader)):
        acc = calc_accuracy_loader(ld, model, device)
        final[name] = acc
        print(f"  {name:<6}: **{acc*100:.2f}%**")

    print()
    print("--- 재현 게이트 (교재 값 ±1%p) ---")
    REF = {"train": 97.21, "val": 97.32, "test": 95.67}
    for name in ("train", "val", "test"):
        d = final[name] * 100 - REF[name]
        mark = "PASS" if abs(d) <= 1.0 else "FAIL"
        star = " ← 재현 게이트" if name == "test" else ""
        print(f"  {name:<6}: 교재 {REF[name]:.2f}% / 실측 {final[name]*100:.2f}% "
              f"/ 차이 {d:+.2f}%p → {mark}{star}")

    torch.save(model.state_dict(), "spam_classifier.pth")
    print("\n[저장] spam_classifier.pth")

    # 곡선
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.5))
    xs = torch.linspace(0, 5, len(tr_losses))
    axes[0].plot(xs, tr_losses, label="훈련 손실")
    axes[0].plot(xs, va_losses, linestyle="-.", label="검증 손실")
    axes[0].set_xlabel("에폭"); axes[0].set_ylabel("손실")
    axes[0].set_title("분류 손실"); axes[0].legend(); axes[0].grid(alpha=0.3)
    ep = range(1, len(tr_accs) + 1)
    axes[1].plot(ep, [a*100 for a in tr_accs], marker="o", label="훈련 정확도")
    axes[1].plot(ep, [a*100 for a in va_accs], marker="s", linestyle="-.",
                 label="검증 정확도")
    axes[1].axhline(50, color="gray", linestyle=":", label="동전(50%)")
    axes[1].set_xlabel("에폭"); axes[1].set_ylabel("정확도 (%)")
    axes[1].set_title("분류 정확도"); axes[1].legend(); axes[1].grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig("acc_curve.png", dpi=130)
    print("[저장] acc_curve.png")

    # ---- 혼동행렬과 오분류 사례 ----
    print()
    print("--- 테스트셋 혼동행렬 ---")
    import pandas as pd
    test_df = pd.read_csv("test.csv")
    model.eval()
    preds, trues = [], []
    for x, y in test_loader:
        x = x.to(device)
        with torch.no_grad():
            p = torch.argmax(model(x)[:, -1, :], dim=-1)
        preds.extend(p.cpu().tolist())
        trues.extend(y.tolist())

    TP = sum(1 for p, t in zip(preds, trues) if p == 1 and t == 1)
    FP = sum(1 for p, t in zip(preds, trues) if p == 1 and t == 0)
    FN = sum(1 for p, t in zip(preds, trues) if p == 0 and t == 1)
    TN = sum(1 for p, t in zip(preds, trues) if p == 0 and t == 0)
    print(f"  TP {TP} | FP {FP} | FN {FN} | TN {TN}")
    prec = TP / (TP + FP) if TP + FP else 0
    rec = TP / (TP + FN) if TP + FN else 0
    print(f"  정밀도 {prec*100:.2f}% / 재현율 {rec*100:.2f}% / "
          f"F1 {2*prec*rec/(prec+rec)*100:.2f}%")

    wrong = [(i, trues[i], preds[i], test_df.iloc[i]["Text"])
             for i in range(len(preds)) if preds[i] != trues[i]]
    print(f"  오분류 {len(wrong)}건 / {len(preds)}건")

    lines = ["# confusion.md — 테스트셋 혼동행렬과 오분류 사례 (P11-5 산출물)", ""]
    lines.append(f"모델: GPT-2 124M + 분류 헤드, 동결 전략 (b) / 5 에폭 / "
                 f"test {len(preds)}건")
    lines.append("")
    lines.append("## 혼동행렬")
    lines.append("")
    lines.append("| | 예측 spam | 예측 ham |")
    lines.append("|---|---|---|")
    lines.append(f"| **실제 spam** | TP {TP} | FN {FN} |")
    lines.append(f"| **실제 ham** | FP {FP} | TN {TN} |")
    lines.append("")
    lines.append(f"- 정확도 {(TP+TN)/len(preds)*100:.2f}% "
                 f"({TP+TN}/{len(preds)})")
    lines.append(f"- 정밀도 {prec*100:.2f}% · 재현율 {rec*100:.2f}% · "
                 f"F1 {2*prec*rec/(prec+rec)*100:.2f}%")
    lines.append("")
    lines.append("## 오분류 사례")
    lines.append("")
    for k, (i, t, p, txt) in enumerate(wrong[:3], 1):
        kind = "FN (스팸을 놓침)" if t == 1 else "FP (정상을 스팸 처리)"
        lines.append(f"### {k}. {kind}")
        lines.append("")
        lines.append("```")
        lines.append(str(txt))
        lines.append("```")
        lines.append("")
        lines.append("**한 줄 평가:** (아래 판정 참고)")
        lines.append("")
    with open("confusion.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("[저장] confusion.md")

    print()
    print("--- 오분류 사례 3개 원문 ---")
    for k, (i, t, p, txt) in enumerate(wrong[:3], 1):
        kind = "FN(스팸을 놓침)" if t == 1 else "FP(정상을 스팸 처리)"
        print(f"\n[{k}] {kind}")
        print(f"    {txt}")
