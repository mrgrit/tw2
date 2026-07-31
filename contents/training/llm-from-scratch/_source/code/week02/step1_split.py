r"""P2-1 — the-verdict.txt 를 교재 2장과 동일한 방식으로 토큰 분리.

정규식 r'([,.:;?_!"()\']|--|\s)' 로 분할하고, 양끝 공백 제거 후 빈 문자열을 제외한다.
"""
import re


def split_tokens(text):
    """교재 2.2절의 정규식 분리. 구두점·이중하이픈·공백을 캡처 그룹으로 두어
    분리 결과에 구분자 자체도 남게 한다(구두점을 독립 토큰으로 얻기 위함)."""
    preprocessed = re.split(r'([,.:;?_!"()\']|--|\s)', text)
    # 양끝 공백 제거 후 빈 문자열 제외 → 공백 구분자는 여기서 사라진다
    return [item.strip() for item in preprocessed if item.strip()]


if __name__ == "__main__":
    with open("the-verdict.txt", "r", encoding="utf-8") as f:
        raw_text = f.read()

    tokens = split_tokens(raw_text)

    print("전체 토큰 수:", len(tokens))
    print("처음 30개 토큰:")
    print(tokens[:30])
