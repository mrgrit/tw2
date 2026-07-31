"""V12-2 — ignore_index(-100) 가 실제로 손실에서 그 위치를 제거함을 실증."""
import torch

torch.manual_seed(123)

# 1. 2토큰짜리 손실
logits_2 = torch.tensor([
    [-1.0, 1.0],      # 1번째 토큰 예측
    [-0.5, 1.5],      # 2번째 토큰 예측
])
targets_2 = torch.tensor([0, 1])
loss_2 = torch.nn.functional.cross_entropy(logits_2, targets_2)

print("=" * 70)
print("1. 2토큰 손실")
print("=" * 70)
print(f"  logits\n{logits_2}")
print(f"  targets  {targets_2.tolist()}")
print(f"  손실     **{loss_2.item():.10f}**")

# 2. 같은 로짓에 세 번째 토큰을 추가하고 그 타깃만 -100
logits_3 = torch.cat([logits_2, torch.tensor([[-0.5, 1.5]])])
targets_3 = torch.tensor([0, 1, 1])
loss_3_real = torch.nn.functional.cross_entropy(logits_3, targets_3)

targets_3_ign = torch.tensor([0, 1, -100])
loss_3_ign = torch.nn.functional.cross_entropy(logits_3, targets_3_ign)

print()
print("=" * 70)
print("2. 3토큰 손실 — 세 번째 타깃을 -100 으로")
print("=" * 70)
print(f"  logits\n{logits_3}")
print(f"  targets (진짜 라벨 1)  {targets_3.tolist()} → 손실 {loss_3_real.item():.10f}")
print(f"  targets (-100)         {targets_3_ign.tolist()} → 손실 "
      f"**{loss_3_ign.item():.10f}**")

print()
print("=" * 70)
print("3. 동일성 판정")
print("=" * 70)
print(f"  2토큰 손실        : {loss_2.item():.10f}")
print(f"  3토큰(-100) 손실  : {loss_3_ign.item():.10f}")
print(f"  차이              : {abs(loss_2.item() - loss_3_ign.item()):.2e}")
print(f"  torch.equal       : {torch.equal(loss_2, loss_3_ign)}")
print(f"  → 판정: {'PASS' if torch.equal(loss_2, loss_3_ign) else 'FAIL'}")
print()
print(f"  (대조) 세 번째를 진짜 라벨로 두면 : {loss_3_real.item():.10f} "
      f"— 2토큰 손실과 {abs(loss_3_real.item()-loss_2.item()):.4f} 만큼 다르다.")
print("   즉 세 번째 토큰이 '있는데 무시된' 것이지, 원래 없었던 게 아니다.")

print("""
[해석] cross_entropy 는 ignore_index(-100 기본값) 위치를 **분자에서도 분모에서도**
뺀다. reduction='mean' 이 나누는 개수가 3 이 아니라 2 가 된다는 뜻이다.
만약 분자에서만 빼고 분모는 3 이라면 손실이 2/3 로 줄어들어 두 값이 달랐을 것이다.
지금 두 값이 **비트 단위로 같으므로**, -100 위치는 손실 계산에서 완전히 없는 셈이다.

이것이 collate 최종 단계의 의미다 — 패딩 구간을 -100 으로 덮으면 모델은
"패딩 다음에 패딩" 이라는 무의미한 패턴을 배우지 않는다. 대신 첫 50256 하나는
남겨 두었으므로 "응답이 끝나면 <|endoftext|>" 는 배운다.""")
