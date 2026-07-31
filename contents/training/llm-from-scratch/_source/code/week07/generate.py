"""P7-3 — generate_text_simple 구현과 훈련 전 생성 관찰 (교재 4.7절)."""
import tiktoken
import torch

from gpt_model import GPT_CONFIG_124M, GPTModel


def generate_text_simple(model, idx, max_new_tokens, context_size):
    """greedy 생성 루프.

    ① 입력을 context_size 이내로 뒤에서 자름 ② 로짓 계산
    ③ 마지막 위치 로짓의 argmax ④ idx 뒤에 이어붙임
    """
    for _ in range(max_new_tokens):
        # ① 컨텍스트 초과분은 앞을 잘라낸다 (뒤에서 context_size 만큼만 남긴다)
        idx_cond = idx[:, -context_size:]

        with torch.no_grad():
            logits = model(idx_cond)

        # ② 마지막 위치의 로짓만 취한다 — 우리가 원하는 건 "다음" 토큰뿐이다
        logits = logits[:, -1, :]

        # ③ 가장 점수 높은 토큰 (greedy)
        idx_next = torch.argmax(logits, dim=-1, keepdim=True)

        # ④ 뒤에 붙이고 반복
        idx = torch.cat((idx, idx_next), dim=1)

    return idx


if __name__ == "__main__":
    tokenizer = tiktoken.get_encoding("gpt2")

    # 시드 → 모델 생성 → eval 순서를 반드시 지킨다
    torch.manual_seed(123)
    model = GPTModel(GPT_CONFIG_124M)
    model.eval()

    start_context = "Hello, I am"
    encoded = tokenizer.encode(start_context)
    print(f"시작 문자열   : {start_context!r}")
    print(f"인코딩된 토큰 : {encoded}  ({len(encoded)}개)")

    encoded_tensor = torch.tensor(encoded).unsqueeze(0)
    print(f"입력 텐서 shape: {tuple(encoded_tensor.shape)}")

    out = generate_text_simple(
        model=model,
        idx=encoded_tensor,
        max_new_tokens=6,
        context_size=GPT_CONFIG_124M["context_length"],
    )

    print()
    print(f"생성 후 토큰 수: {out.shape[1]}")
    print(f"생성 후 토큰 ID: {out[0].tolist()}")

    decoded = tokenizer.decode(out.squeeze(0).tolist())
    print()
    print(f"디코딩 결과: {decoded!r}")

    expected = "Hello, I am Featureiman Byeswickattribute argue"
    print()
    print("=== 정답지 대조 ===")
    print(f"교재: {expected!r}")
    print(f"실측: {decoded!r}")
    print(f"일치: {decoded == expected}")
