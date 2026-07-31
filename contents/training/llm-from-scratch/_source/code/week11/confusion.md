# confusion.md — 테스트셋 혼동행렬과 오분류 사례 (P11-5 산출물)

모델: GPT-2 124M + 분류 헤드, 동결 전략 (b) / 5 에폭 / test 300건

## 혼동행렬

| | 예측 spam | 예측 ham |
|---|---|---|
| **실제 spam** | TP 141 | FN 10 |
| **실제 ham** | FP 3 | TN 146 |

- 정확도 95.67% (287/300)
- 정밀도 97.92% · 재현율 93.38% · F1 95.59%

## 오분류 사례

### 1. FN (스팸을 놓침)

```
thesmszone.com lets you send free anonymous and masked messages..im sending this message from there..do you see the potential for abuse???
```

**한 줄 평가:** (아래 판정 참고)

### 2. FN (스팸을 놓침)

```
Hello. We need some posh birds and chaps to user trial prods for champneys. Can i put you down? I need your address and dob asap. Ta r
```

**한 줄 평가:** (아래 판정 참고)

### 3. FN (스팸을 놓침)

```
Filthy stories and GIRLS waiting for your
```

**한 줄 평가:** (아래 판정 참고)

