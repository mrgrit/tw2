"""P11-0 — SMS Spam Collection 확보와 실태 파악."""
import os
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

URL = "https://archive.ics.uci.edu/static/public/228/sms+spam+collection.zip"
BACKUP = "https://f001.backblazeb2.com/file/LLMs-from-scratch/sms%2Bspam%2Bcollection.zip"
ZIP_PATH = "sms_spam_collection.zip"
EXTRACTED = "sms_spam_collection"
DATA_FILE = Path(EXTRACTED) / "SMSSpamCollection.tsv"


def download_and_unzip(url):
    if DATA_FILE.exists():
        print(f"{DATA_FILE} 가 이미 있어 다운로드를 건너뜁니다.")
        return
    with urllib.request.urlopen(url, timeout=120) as r:
        with open(ZIP_PATH, "wb") as f:
            f.write(r.read())
    with zipfile.ZipFile(ZIP_PATH, "r") as z:
        z.extractall(EXTRACTED)
    os.rename(Path(EXTRACTED) / "SMSSpamCollection", DATA_FILE)
    print(f"다운로드 완료 → {DATA_FILE}")


try:
    download_and_unzip(URL)
except Exception as e:
    print(f"기본 URL 실패: {e}. 백업 URL 시도")
    download_and_unzip(BACKUP)

df = pd.read_csv(DATA_FILE, sep="\t", header=None, names=["Label", "Text"])

print()
print("=" * 68)
print("1. 전체 건수와 레이블 분포")
print("=" * 68)
print(f"  전체: {len(df):,} 건")
counts = df["Label"].value_counts()
for lab in ("ham", "spam"):
    print(f"  {lab:<5}: {counts[lab]:>5,} 건 ({counts[lab]/len(df)*100:5.2f}%)")

print()
print("=" * 68)
print("2. 실제 메시지 예시")
print("=" * 68)
for lab in ("ham", "spam"):
    print(f"\n  [{lab}]")
    for i, t in enumerate(df[df["Label"] == lab]["Text"].head(2), 1):
        print(f"    {i}. {t[:150]}")

print()
print("=" * 68)
print("3. [검증] 정확도 지표가 왜 위험한가 — 바보 분류기")
print("=" * 68)
majority = counts.idxmax()
dumb_acc = counts.max() / len(df)
print(f'  바보 분류기: 입력을 보지 않고 무조건 "{majority}" 라고 답한다.')
print(f"  정확도 = {counts.max():,} / {len(df):,} = **{dumb_acc*100:.2f}%**")
print()
print(f"  → 아무것도 배우지 않은 분류기가 {dumb_acc*100:.1f}점을 받는다.")
print(f"    스팸 {counts['spam']:,}건을 **전부 놓치는데도** 그렇다.")
print(f"    이 데이터에서 '정확도 90%'는 바보보다 겨우 3%p 나은 것이고,")
print(f"    '정확도 86%'는 바보보다 **못한** 것이다.")
print(f"  → 균형화(ham 을 {counts['spam']:,}개로 언더샘플링)를 하면 바보 분류기의")
print(f"    정확도가 50% 로 내려가 지표가 정직해진다.")
