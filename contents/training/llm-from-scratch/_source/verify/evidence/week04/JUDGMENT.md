# Week 04 판정 — 어텐션은 어디를 보는가

환경: llm-lab 컨테이너 (torch 2.9.1+cu130) · 2026-07-30

## 프롬프트별 판정

| 프롬프트 | 판정 | 근거 |
|---|---|---|
| P4-0 (입력 텐서) | **PASS** | 교재 ch03.ipynb cell #1 과 6행 전부 일치 |
| P4-1 (3단계 추적) | **PASS** | 점수·가중치·z2 모두 정답지와 소수 4자리 일치 |
| V4-1 (softmax 교차) | **PASS** | torch vs 수식 allclose, 합 1.0, 오버플로 실증(`nan`) |
| P4-2 (전체 행렬화) | **PASS** | 루프==행렬 allclose, 행 합 전부 1, 2행==z2 |
| P4-3 (히트맵) | **PASS**(환경 수정 필요) | png 생성 + 관찰 3가지. 한글 폰트 결함 #7 → 수정 완료 |
| P4-4 (SelfAttention_v1) | **PASS** | 두 번째 행 `[0.3061, 0.8210]` 정확 일치 |
| P4-5 (연습 3.1 이식) | **PASS** | 전치 필요 이유 규명, 이식 후 오차 **0.000e+00** |
| V4-2 (pytest 3개) | **PASS** | `3 passed` (전치 누락 시 실패하는 반례까지 포함) |
| P4-6 (스케일링 실험) | **PASS** | 분산 ≈ d, 스케일링 없으면 최댓값 1.000000 |
| P4-7 (제출) | **PASS** | 6개 필수 산출물 존재 |

## 게이트 판정

| 게이트 | 주장 | 실측 | 판정 |
|---|---|---|---|
| W04-G1 | 교재 ch03 에 동일 inputs 텐서 | cell #1, 6행 완전 일치 | ✅ PASS |
| W04-G2 | 점수 `[0.9544, 1.4950, 1.4754, 0.8434, 0.7070, 1.0865]` | `[0.9544, 1.4950, 1.4754, 0.8434, 0.7070, 1.0865]` | ✅ PASS |
| W04-G3 | 가중치 `[0.1385, 0.2379, 0.2333, 0.1240, 0.1082, 0.1581]`, 합 1.0 | 동일, 합 1.0000 | ✅ PASS |
| W04-G4 | z2 `[0.4419, 0.6515, 0.5683]` | `[0.4419, 0.6515, 0.5683]` | ✅ PASS |
| W04-G5 | 손계산 0.43×0.55+0.15×0.87+0.89×0.66 = 0.9544 | 0.9544 (일치 True) | ✅ PASS |
| W04-G6 | 수동 softmax == torch, 합 1 | allclose True, 합 1.0 | ✅ PASS |
| W04-G7 | 루프==행렬, 행 합 1, 2행==z2 | 3항목 전부 True | ✅ PASS |
| W04-G8 | 히트맵 + 관찰 3가지 | png 생성, 그림·수치 대조 확인 | ✅ PASS |
| W04-G9 | v1 두 번째 행 `[0.3061, 0.8210]` | `[0.3061, 0.8210]` | ✅ PASS |
| W04-G10 | 전치 필요, 이식 후 allclose | `(3,2)` vs `(2,3)` 확인, allclose True 오차 0 | ✅ PASS |
| W04-G11 | `3 passed` | `3 passed` | ✅ PASS |
| W04-G12 | 내적 분산 ≈ d | 8→8.02, 64→63.89, 512→528.26 (측정/이론 1.002/0.998/1.032) | ✅ PASS |
| W04-G13 | 스케일링 없는 d=512 는 원-핫에 가까움 | 최댓값 **1.000000**, 엔트로피 **0.0000** vs 스케일 후 0.4739 / 1.4332 | ✅ PASS |

**Week 04 게이트 13개 전부 PASS.** 교재 수치 정확도가 매우 높다.

## 히트맵 관찰 3가지 (사람 눈 검증 완료)

1. 가장 큰 가중치 0.2379 — `journey → journey`. 대각선 제외 최대는 0.2369 (`starts → journey`)
2. 대각선 `[0.2098, 0.2379, 0.2326, 0.1462, 0.1879, 0.1896]` — 6개 행 중 **자기 자신이 1등인
   행은 2개뿐**. 학습 전이므로 "자기 자신 주목"이 보장되지 않는다
3. `journey ↔ starts` 상호 가중치 0.2333 / 0.2369 (최상위권). 두 입력 벡터의 **코사인 유사도
   0.999676** — 이 단계의 주목은 의미가 아니라 벡터 유사도다 (교재 4.5절 서술과 정확히 부합)

---

# 발견된 결함

## 결함 #7 — 골든 이미지에 한글 폰트 부재로 그래프 한글이 □ 로 깨짐 (**중간**, 환경차이)

**영향 범위**: 4주차 P4-3, 6주차 P6-2, 9주차 P9-3, 10주차 P10-1, 11주차 P11-5, 12주차 P12-5,
13주차 P13-1/P13-3 — **그래프를 요구하는 모든 미션**

**증상**: 컨테이너에 한글 폰트가 0개다.
```
$ fc-list | grep -icE "nanum|noto.*cjk"
0
$ python3 -c "import matplotlib.font_manager as fm; print([f.name for f in fm.fontManager.ttflist if 'Nanum' in f.name])"
[]      (전체 폰트 40개, 한글 0개)
```
결과: 축 라벨 `Query (주목하는 토큰)` 이 `Query (□□□□ □□)` 로 렌더링된다.
한국어 교재인데 그래프에 한글을 못 쓴다.

**해결 (적용 완료)**: 골든 이미지에 폰트 설치 + matplotlib 기본값 고정.

```dockerfile
RUN apt-get install -y --no-install-recommends \
        fonts-nanum fonts-nanum-coding fontconfig \
    && fc-cache -fv

# 패키지 기본 matplotlibrc 를 수정하면 Duplicate key 경고가 나므로 별도 파일 + 환경변수
RUN mkdir -p /opt/mplconfig && printf '%s\n' \
        'backend: Agg' \
        'font.family: NanumGothic' \
        'axes.unicode_minus: False' \
        'figure.dpi: 110' \
    > /opt/mplconfig/matplotlibrc
ENV MATPLOTLIBRC=/opt/mplconfig/matplotlibrc \
    MPLCONFIGDIR=/tmp/mplcache
```

적용 후 확인:
```
backend: Agg
font.family: ['NanumGothic']
Nanum 폰트: ['NanumBarunGothic','NanumGothic','NanumGothicCoding','NanumMyeongjo',
             'NanumSquare','NanumSquare Bold','NanumSquareRound', ...]
```
히트맵 재생성 → 축 라벨 `Query (주목하는 토큰)` / `Key (참고 대상 토큰)` 정상 렌더링 확인.

**부수 항목**: `backend: Agg` 도 함께 고정했다. 컨테이너에는 디스플레이가 없으므로
`plt.savefig` 전에 `matplotlib.use("Agg")` 를 빼먹으면 백엔드 경고가 난다. 골든 이미지에서
기본값으로 잡아두면 학생이 이 문제를 만나지 않는다.

**교재 반영 권고**: 1주차 P1-4 골든 이미지 설명에 "한글 폰트(fonts-nanum)와 matplotlib
Agg 백엔드가 포함되어 있다"를 한 줄 추가. 그래프 미션들의 트러블슈팅 표에
"그래프 한글이 □ 로 나온다 → 골든 이미지 버전 확인(조교 문의)" 행 추가.
