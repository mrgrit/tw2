"""V11-2 — 실전 분류 함수 판정과 한국어 입력 관찰."""
import tiktoken
import torch

import common  # noqa: F401
from common import device
from spam_finetune import classify_review, load_and_modify

tokenizer = tiktoken.get_encoding("gpt2")

model, cfg = load_and_modify("gpt2-small (124M)", strategy="b", verbose=False)
model.load_state_dict(torch.load("spam_classifier.pth", map_location=device))
model.to(device)
model.eval()
print("spam_classifier.pth 로드 완료\n")

EX_A = ("You are a winner you have been specially selected to receive "
        "$1000 cash or a $2000 award.")
EX_B = ("Hey, just wanted to check if we're still on for dinner tonight? "
        "Let me know!")

print("=" * 72)
print("2. 교재 예문 2개 판정")
print("=" * 72)
for tag, txt, expect in (("a", EX_A, "spam"), ("b", EX_B, "not spam")):
    got = classify_review(txt, model, tokenizer, device, max_length=120)
    print(f"  [{tag}] {txt[:60]}...")
    print(f"      판정 = **{got}**  (기대 {expect})  → "
          f"{'PASS' if got == expect else 'FAIL'}")

print()
print("=" * 72)
print("4. [관찰] 한국어 문자 메시지 — 판정을 신뢰할 수 있는가")
print("=" * 72)

KO = [
    ("정상", "엄마 오늘 저녁에 집에 몇 시에 와? 밥 차려놓을게."),
    ("스팸풍", "[Web발신] 축하합니다! 고객님께서 1등 당첨되셨습니다. "
              "지금 바로 링크를 눌러 300만원 상금을 수령하세요 http://bit.ly/xxx"),
]
EN_REF = [
    ("정상(영어)", "Mom what time are you coming home tonight? I'll set the table."),
    ("스팸풍(영어)", "Congratulations! You are the 1st prize winner. "
                    "Click the link now to claim your 3000 dollar prize http://bit.ly/xxx"),
]

print(f"{'구분':<14}{'토큰수':>7}{'문자수':>7}{'토큰/문자':>10}  판정")
print("-" * 62)
for tag, txt in KO + EN_REF:
    n_tok = len(tokenizer.encode(txt))
    got = classify_review(txt, model, tokenizer, device, max_length=120)
    print(f"{tag:<14}{n_tok:>7}{len(txt):>7}{n_tok/len(txt):>10.2f}  {got}")

# 로짓까지 뽑아 확신도를 본다
print()
print("--- 로짓과 확률 (모델이 얼마나 확신하는가) ---")


def probs(text):
    ids = tokenizer.encode(text)[:120]
    ids += [50256] * (120 - len(ids))
    with torch.no_grad():
        lg = model(torch.tensor(ids, device=device).unsqueeze(0))[:, -1, :]
    return torch.softmax(lg, dim=-1)[0].tolist()


for tag, txt in KO + EN_REF:
    p = probs(txt)
    print(f"  {tag:<14} P(ham)={p[0]:.4f}  P(spam)={p[1]:.4f}")

print(f"""
[논평] 이 판정을 신뢰할 수 있는가 — **아니다.** 두 가지 이유가 겹친다.

첫째, 2주차에서 본 토큰 비효율이다. 한국어 문장은 문자당 토큰 수가 영어의
몇 배다(위 표). 같은 내용을 담아도 한국어는 토큰을 훨씬 많이 쓰므로,
max_length=120 안에서 실제로 담기는 '의미의 양'이 영어보다 적다.
긴 한국어 문자는 판단이 끝나기 전에 잘려 나간다.

둘째, 더 근본적인 문제는 분포 밖 입력이라는 점이다. 이 분류기는
영어 SMS 1,045건으로 훈련됐다. 훈련 데이터에 한국어는 **한 글자도** 없었다.
GPT-2 의 BPE 는 한국어를 바이트 단위로 쪼개므로, 모델이 보는 것은
의미 있는 서브워드가 아니라 낯선 바이트 조각의 나열이다.
그런데도 softmax 는 반드시 둘 중 하나에 확률을 몰아준다 —
**모르겠다고 답할 방법이 이 구조에는 없다.**

위 확률표를 보면 한국어 입력에서도 모델이 제법 확신에 찬 값을 낸다.
이것이 가장 위험한 부분이다. 틀린 답을 자신 있게 내는 분류기는
헷갈려하는 분류기보다 나쁘다. **'돌아간다'와 '믿을 수 있다'는 다르다.**

실전 대응: ① 한국어 데이터로 재훈련하거나 ② 입력 언어를 먼저 감지해
지원 언어가 아니면 거부하거나 ③ 최대 확률이 임계값 미만이면
'판정 보류'로 돌리는 장치가 필요하다.""")
