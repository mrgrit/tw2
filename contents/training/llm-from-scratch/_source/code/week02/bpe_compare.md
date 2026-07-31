# bpe_compare.md — SimpleTokenizerV2 vs GPT-2 BPE (P2-6 산출물)

비교 문장: `Hello, do you like tea? <|endoftext|> In the sunlit terraces of the palace.`

| 비교 항목 | SimpleTokenizerV2 | tiktoken gpt2 BPE |
|---|---|---|
| 어휘 크기 | 1132 | 50257 |
| 어휘 구성 | the-verdict.txt 고유 토큰 1,130 + `<\|endoftext\|>` + `<\|unk\|>` | 바이트 256 + 병합 50,000 + `<\|endoftext\|>` 1 |
| OOV 처리 방식 | 미등록 단어를 `<\|unk\|>` 하나로 **뭉갠다**(정보 손실) | 서브워드로 **분해**한다(정보 보존, OOV 원리적 부재) |
| 위 문장의 토큰 수 | 16 | 19 |
| Hello 의 처리 결과 | `<\|unk\|>` (ID 1131) 로 치환 — 원문 복구 불가 | `Hello` → ID 15496 그대로, 복원 가능 |
| palace 의 처리 결과 | `<\|unk\|>` 로 치환 | ['pal', 'ace'] 조각으로 분해 후 정확 복원 |
| decode 원문 복원 | X — `<|unk|>, do you like tea? <|endoftext|> In the sunlit terraces of the <|unk|>.` | O — 원문과 완전 일치 |

## 검증 — BPE decode 결과에 `<|unk|>` 가 등장하지 않음

```
BPE decode: Hello, do you like tea? <|endoftext|> In the sunlit terraces of the palace.
<|unk|> 포함? False
원문과 일치? True
```

BPE 는 `<|unk|>` 토큰 자체를 **가지고 있지 않다**. 어휘에 바이트 256개가 모두 들어 있으므로
어떤 입력이든 최악의 경우 바이트 단위로 쪼개서 표현할 수 있다 — 그래서 OOV 가 원리적으로 없다.
