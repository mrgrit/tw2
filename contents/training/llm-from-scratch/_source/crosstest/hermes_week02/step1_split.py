import re

# 텍스트 읽기
with open('the-verdict.txt', 'r', encoding='utf-8') as f:
    text = f.read()

# 정규식 토큰 분리 패턴 (교재 2장과 동일)
pattern = r'([,.:;?_!"()\']|--|\s)'

# 분할 및 필터링
tokens = re.split(pattern, text)
tokens = [t.strip() for t in tokens if t and not t.isspace()]
tokens = [t for t in tokens if t]  # 빈 문자열 제외

# 결과 출력
print(f"전체 토큰 수: {len(tokens)}")
print(f"\n처음 30 개 토큰:")
for i, token in enumerate(tokens[:30], start=1):
    print(f"{i:2d}: {token!r}")
