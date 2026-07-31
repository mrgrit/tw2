"""P10-5 — OpenAI GPT-2 공개 가중치를 우리 구현에 이식한다.

순서: 124M 으로 절차를 검증한 뒤 355M 으로 확장 (작게 검증, 크게 실행).

[1차 경로 실패 기록]
교재 P10-5 는 "교재 저장소 ch05 의 가중치 다운로드 유틸"을 쓰라고 한다. 그 유틸
(`ch05/01_main-chapter-code/gpt_download.py`) 은 `import tensorflow` 로 시작한다.
llm-lab 골든 이미지에는 tensorflow 가 없어 ModuleNotFoundError 가 난다.
교재 10.12 트러블슈팅 표가 이 경우를 예고하고 있다:
  "다운로드 유틸의 tensorflow 의존 오류 → ch05 보너스의 대안 로더(TF 불필요) 사용"
그래서 `ch05/02_alternative_weight_loading/weight-loading-hf-safetensors.ipynb`
경로를 따른다 — HuggingFace 허브의 .safetensors 를 직접 받아 텐서만 읽는다.
"""
import os
import time

import requests
import tiktoken
import torch
from safetensors.torch import load_file

import common  # noqa: F401
from common import VERDICT, device, text_to_token_ids, token_ids_to_text
from decoding import generate
from gpt_model import GPTModel
from pretrain import build_loaders, calc_loss_loader

WEIGHTS_DIR = "gpt2_weights"
os.makedirs(WEIGHTS_DIR, exist_ok=True)

# OpenAI 원본 규약에 맞춘 config — 우리 GPT_CONFIG_124M 과 두 곳이 다르다
BASE_CONFIG = {
    "vocab_size": 50257,
    "context_length": 1024,   # 우리 실습은 256 이었지만 원본은 1024
    "drop_rate": 0.0,         # 추론만 하므로 dropout 0
    "qkv_bias": True,         # 원본 GPT-2 는 QKV 에 bias 가 있다
}
MODEL_CONFIGS = {
    "gpt2-small (124M)": {"emb_dim": 768, "n_layers": 12, "n_heads": 12},
    "gpt2-medium (355M)": {"emb_dim": 1024, "n_layers": 24, "n_heads": 16},
}
URL_DIR = {"gpt2-small (124M)": "gpt2", "gpt2-medium (355M)": "gpt2-medium"}


def download(model_name):
    """HuggingFace 허브에서 .safetensors 를 받아 경로를 돌려준다 (있으면 재사용)."""
    repo = URL_DIR[model_name]
    out = os.path.join(WEIGHTS_DIR, f"model-{repo}.safetensors")
    if os.path.exists(out):
        print(f"  [캐시] {out} ({os.path.getsize(out)/1e6:.0f} MB)")
        return out
    url = f"https://huggingface.co/openai-community/{repo}/resolve/main/model.safetensors"
    print(f"  다운로드: {url}")
    t0 = time.time()
    with requests.get(url, stream=True, timeout=120) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        done = 0
        with open(out, "wb") as f:
            for chunk in r.iter_content(chunk_size=1 << 20):
                f.write(chunk)
                done += len(chunk)
                if total:
                    print(f"\r    {done/1e6:7.0f} / {total/1e6:.0f} MB "
                          f"({done/total*100:5.1f}%)", end="")
    print(f"\n  완료 {time.time()-t0:.1f}초, {os.path.getsize(out)/1e6:.0f} MB")
    return out


def assign(left, right):
    """shape 를 대조한 뒤 nn.Parameter 로 감싸 돌려준다.

    shape 검사가 이식의 1차 방어선이다 — 전치를 빼먹거나 QKV 분할을 잘못하면
    여기서 즉시 걸린다.
    """
    if left.shape != right.shape:
        raise ValueError(f"shape 불일치: 우리 {left.shape} vs 원본 {right.shape}")
    return torch.nn.Parameter(right.clone().detach())


def load_weights_into_gpt(gpt, params):
    """OpenAI 체크포인트(params)를 우리 GPTModel(gpt)에 옮겨 싣는다."""
    gpt.pos_emb.weight = assign(gpt.pos_emb.weight, params["wpe.weight"])
    gpt.tok_emb.weight = assign(gpt.tok_emb.weight, params["wte.weight"])

    for b in range(len(gpt.trf_blocks)):
        # --------------------------------------------------------------
        # (a) 합쳐진 QKV 행렬을 셋으로 분할하는 이유
        # --------------------------------------------------------------
        # 원본 GPT-2 는 Q·K·V 를 각각 따로 두지 않고 `c_attn` 이라는
        # [emb_dim, 3*emb_dim] 짜리 **한 장의 행렬**로 들고 있다. 입력 x 를
        # 한 번만 곱해 [T, 3*emb] 를 얻은 뒤 잘라 쓰는 방식이다 —
        # 행렬 곱 3번을 1번으로 줄이는 속도 최적화다.
        # 우리 구현(5주차 MultiHeadAttention)은 W_query/W_key/W_value 를
        # 별도 nn.Linear 로 두었으므로, 마지막 축(-1)을 3등분해야 한다.
        # 순서는 원본 규약대로 Q → K → V 다. 이 순서를 틀리면 shape 는
        # 통과하지만 손실이 10 근처로 치솟는다(= V10-3 의 3번 게이트가 잡는다).
        q_w, k_w, v_w = torch.chunk(params[f"h.{b}.attn.c_attn.weight"], 3, axis=-1)

        # --------------------------------------------------------------
        # (b) Linear 가중치를 전치(.T)하는 이유  — 4주차 연습문제 3.1과 같은 문제
        # --------------------------------------------------------------
        # 원본은 TensorFlow 규약을 따라 가중치를 [in_features, out_features]
        # 로 저장한다. 반면 PyTorch nn.Linear 는 y = x @ W.T + b 를 계산하므로
        # weight 를 [out_features, in_features] 로 들고 있다. 즉 두 규약은
        # 서로 전치 관계다. 4주차에 SelfAttention_v1(nn.Parameter, [d_in,d_out])
        # → v2(nn.Linear, [d_out,d_in]) 로 옮길 때 `.T` 를 붙였던 그 상황이
        # 여기서 그대로 재현된다. 이것이 "가중치 이식 = 규약 맞추기"다.
        gpt.trf_blocks[b].att.W_query.weight = assign(
            gpt.trf_blocks[b].att.W_query.weight, q_w.T)
        gpt.trf_blocks[b].att.W_key.weight = assign(
            gpt.trf_blocks[b].att.W_key.weight, k_w.T)
        gpt.trf_blocks[b].att.W_value.weight = assign(
            gpt.trf_blocks[b].att.W_value.weight, v_w.T)

        # bias 는 1차원 벡터라 전치가 필요 없다. 분할만 한다.
        q_b, k_b, v_b = torch.chunk(params[f"h.{b}.attn.c_attn.bias"], 3, axis=-1)
        gpt.trf_blocks[b].att.W_query.bias = assign(
            gpt.trf_blocks[b].att.W_query.bias, q_b)
        gpt.trf_blocks[b].att.W_key.bias = assign(
            gpt.trf_blocks[b].att.W_key.bias, k_b)
        gpt.trf_blocks[b].att.W_value.bias = assign(
            gpt.trf_blocks[b].att.W_value.bias, v_b)

        gpt.trf_blocks[b].att.out_proj.weight = assign(
            gpt.trf_blocks[b].att.out_proj.weight,
            params[f"h.{b}.attn.c_proj.weight"].T)
        gpt.trf_blocks[b].att.out_proj.bias = assign(
            gpt.trf_blocks[b].att.out_proj.bias, params[f"h.{b}.attn.c_proj.bias"])

        gpt.trf_blocks[b].ff.layers[0].weight = assign(
            gpt.trf_blocks[b].ff.layers[0].weight, params[f"h.{b}.mlp.c_fc.weight"].T)
        gpt.trf_blocks[b].ff.layers[0].bias = assign(
            gpt.trf_blocks[b].ff.layers[0].bias, params[f"h.{b}.mlp.c_fc.bias"])
        gpt.trf_blocks[b].ff.layers[2].weight = assign(
            gpt.trf_blocks[b].ff.layers[2].weight, params[f"h.{b}.mlp.c_proj.weight"].T)
        gpt.trf_blocks[b].ff.layers[2].bias = assign(
            gpt.trf_blocks[b].ff.layers[2].bias, params[f"h.{b}.mlp.c_proj.bias"])

        # LayerNorm 은 우리가 scale/shift 라 부르고 원본은 weight/bias 라 부른다.
        # 이름만 다르고 역할은 같다 — 규약 차이의 가장 얌전한 사례.
        gpt.trf_blocks[b].norm1.scale = assign(
            gpt.trf_blocks[b].norm1.scale, params[f"h.{b}.ln_1.weight"])
        gpt.trf_blocks[b].norm1.shift = assign(
            gpt.trf_blocks[b].norm1.shift, params[f"h.{b}.ln_1.bias"])
        gpt.trf_blocks[b].norm2.scale = assign(
            gpt.trf_blocks[b].norm2.scale, params[f"h.{b}.ln_2.weight"])
        gpt.trf_blocks[b].norm2.shift = assign(
            gpt.trf_blocks[b].norm2.shift, params[f"h.{b}.ln_2.bias"])

    gpt.final_norm.scale = assign(gpt.final_norm.scale, params["ln_f.weight"])
    gpt.final_norm.shift = assign(gpt.final_norm.shift, params["ln_f.bias"])
    # 가중치 묶기(weight tying) — 원본도 출력 헤드가 토큰 임베딩과 같은 행렬이다
    gpt.out_head.weight = assign(gpt.out_head.weight, params["wte.weight"])


def build(model_name, qkv_bias=True, context_length=1024):
    """설정 조정 → 모델 생성 → 가중치 이식."""
    cfg = dict(BASE_CONFIG, **MODEL_CONFIGS[model_name])
    cfg["qkv_bias"] = qkv_bias
    cfg["context_length"] = context_length
    path = download(model_name)
    params = load_file(path)
    gpt = GPTModel(cfg)
    load_weights_into_gpt(gpt, params)
    gpt.to(device)
    gpt.eval()
    return gpt, cfg, params


if __name__ == "__main__":
    tokenizer = tiktoken.get_encoding("gpt2")
    with open(VERDICT, "r", encoding="utf-8") as f:
        text_data = f.read()
    train_loader, val_loader, _, _ = build_loaders(text_data)

    START = "Every effort moves you"
    results = {}

    for name in ("gpt2-small (124M)", "gpt2-medium (355M)"):
        print("=" * 74)
        print(f"{name} 이식")
        print("=" * 74)
        gpt, cfg, params = build(name)
        n_params = sum(p.numel() for p in gpt.parameters())
        print(f"  config : emb {cfg['emb_dim']}, layers {cfg['n_layers']}, "
              f"heads {cfg['n_heads']}, ctx {cfg['context_length']}, "
              f"qkv_bias {cfg['qkv_bias']}")
        print(f"  파라미터: {n_params:,} "
              f"(weight tying 제외 시 {n_params - gpt.out_head.weight.numel():,})")
        print(f"  원본 텐서 {len(params)}개 전부 이식 완료 (shape 검사 통과)")

        ids = text_to_token_ids(START, tokenizer).to(device)
        out = generate(gpt, ids, max_new_tokens=25,
                       context_size=cfg["context_length"], temperature=0.0)
        text = token_ids_to_text(out, tokenizer)
        print(f"\n  [greedy 25토큰]\n  {text!r}")

        tr = calc_loss_loader(train_loader, gpt, device)
        va = calc_loss_loader(val_loader, gpt, device)
        print(f"\n  the-verdict 손실: train {tr:.4f} / val {va:.4f}")
        results[name] = {"text": text, "train": tr, "val": va,
                         "params": n_params, "cfg": cfg}

        del gpt, params
        torch.cuda.empty_cache()
        print()

    # ---------------- 4모델 비교표 ----------------
    print("=" * 74)
    print("4모델 비교표 — 무작위 / 10에폭 / 124M / 355M")
    print("=" * 74)

    from gpt_model import GPT_CONFIG_124M
    OUR_CFG = dict(GPT_CONFIG_124M, context_length=256)

    # ① 7주차 무작위 초기화 모델
    torch.manual_seed(123)
    rnd = GPTModel(OUR_CFG).to(device)
    rnd.eval()
    ids256 = text_to_token_ids(START, tokenizer).to(device)
    rnd_text = token_ids_to_text(
        generate(rnd, ids256, 25, OUR_CFG["context_length"], temperature=0.0),
        tokenizer)
    rnd_tr = calc_loss_loader(train_loader, rnd, device)
    rnd_va = calc_loss_loader(val_loader, rnd, device)
    del rnd
    torch.cuda.empty_cache()

    # ② 9주차 10에폭 모델
    from common import MODEL_10EP
    ours = GPTModel(OUR_CFG)
    ours.load_state_dict(torch.load(MODEL_10EP, map_location="cpu"))
    ours.to(device).eval()
    our_text = token_ids_to_text(
        generate(ours, ids256, 25, OUR_CFG["context_length"], temperature=0.0),
        tokenizer)
    our_tr = calc_loss_loader(train_loader, ours, device)
    our_va = calc_loss_loader(val_loader, ours, device)
    del ours
    torch.cuda.empty_cache()

    rows = [
        ("① 7주차 무작위 초기화", 163_009_536, rnd_tr, rnd_va, rnd_text),
        ("② 9주차 10에폭 (the-verdict)", 163_009_536, our_tr, our_va, our_text),
        ("③ OpenAI GPT-2 124M", results["gpt2-small (124M)"]["params"],
         results["gpt2-small (124M)"]["train"], results["gpt2-small (124M)"]["val"],
         results["gpt2-small (124M)"]["text"]),
        ("④ OpenAI GPT-2 355M", results["gpt2-medium (355M)"]["params"],
         results["gpt2-medium (355M)"]["train"], results["gpt2-medium (355M)"]["val"],
         results["gpt2-medium (355M)"]["text"]),
    ]

    print(f"{'모델':<30}{'train':>9}{'val':>9}")
    for nm, npar, tr, va, _ in rows:
        print(f"{nm:<30}{tr:>9.4f}{va:>9.4f}")

    lines = ["# compare_generation.md — 4모델 비교 (P10-5 최종 산출)", ""]
    lines.append(f"같은 프롬프트 `\"{START}\"` 에 greedy 25토큰. "
                 f"손실은 the-verdict.txt 를 9주차 로더(max_length=256, stride=256)로 "
                 f"잰 값이라 네 모델이 **완전히 같은 조건**에서 비교된다.")
    lines.append("")
    lines.append("## 손실 비교")
    lines.append("")
    lines.append("| 모델 | 파라미터 | train 손실 | val 손실 | val 퍼플렉시티 |")
    lines.append("|---|---|---|---|---|")
    import math
    for nm, npar, tr, va, _ in rows:
        lines.append(f"| {nm} | {npar:,} | {tr:.4f} | **{va:.4f}** | {math.exp(va):,.1f} |")
    lines.append("")
    lines.append("## 생성문")
    lines.append("")
    for nm, npar, tr, va, tx in rows:
        lines.append(f"**{nm}**")
        lines.append("")
        lines.append("```")
        lines.append(tx)
        lines.append("```")
        lines.append("")
    lines.append("## 한 학기의 서사")
    lines.append("")
    lines.append(f"①→②: 이 소설로 10 에폭을 돌려 train 손실이 "
                 f"{rnd_tr:.2f} → {our_tr:.2f} 로 떨어졌다. 그러나 val 손실은 "
                 f"{rnd_va:.2f} → {our_va:.2f} 로 **거의 그대로**다. "
                 f"train 만 떨어지고 val 이 안 떨어지는 것 — 이것이 과적합의 정의다.")
    lines.append("")
    v124 = results["gpt2-small (124M)"]["val"]
    lines.append(f"②→③: **이 소설을 한 번도 본 적 없는** GPT-2 124M 의 val 손실이 "
                 f"{v124:.4f} 다. 이 소설로 훈련한 우리 모델({our_va:.4f})을 "
                 f"{our_va - v124:.2f} 낮은 손실로 압도한다. 퍼플렉시티로는 "
                 f"{math.exp(our_va):,.0f} → {math.exp(v124):,.0f}, "
                 f"약 {math.exp(our_va)/math.exp(v124):.0f}배 차이다. "
                 f"**아키텍처는 같다. 파라미터 수도 같은 급이다. 다른 것은 오직 데이터의 양이다.**")
    lines.append("")
    v355 = results["gpt2-medium (355M)"]["val"]
    lines.append(f"③→④: 355M 은 val {v355:.4f} 로 124M({v124:.4f})보다 "
                 f"{v124 - v355:.2f} 더 낮다. 같은 데이터에서 모델을 키운 이득이며, "
                 f"②→③ 의 격차({our_va - v124:.2f})보다 훨씬 작다. "
                 f"**데이터가 먼저고 모델 크기가 나중이다.**")
    lines.append("")
    lines.append("이 표가 13주차 파인튜닝의 전제다 — 우리는 남이 큰 데이터로 만든 "
                 "일반화 능력을 출발점으로 빌려 쓰고, 우리 목적에 맞게 조정만 한다.")

    with open("compare_generation.md", "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print("\n[저장] compare_generation.md")
