# Week 01 판정 — 장비 개통과 하드닝

환경: DGX Spark (GB10 / aarch64 / CUDA 13.0 / 119GiB) · llm-course:v1 컨테이너 · 2026-07-30

## 프롬프트별 판정

| 프롬프트 | 판정 | 근거 |
|---|---|---|
| P1-0 (첫 인사·pwd) | **PASS** | 에이전트 능력 설명 + `pwd` 조회. 시스템 변경 없음. 정상 작동 |
| P1-1 (spec-report.md) | **PASS**(주의 1건) | 12개 항목 전부 확인 명령+출력 원문으로 수집. 단 한국어 로케일 함정 → 결함 #1 |
| V1-1 (교차 검증) | **PASS** | 7개 항목 모두 2차 명령으로 일치 확인 (uname/proc/nproc/nvidia-smi -L/proc/version/lsb_release) |
| P1-2 (SSH 키 전용) | **GATED** | 원격 세션 잠금 위험. 전제·절차·검증 명령은 모두 실행 가능함을 확인 |
| P1-3 (UFW/fail2ban/자동업데이트) | **부분 PASS + 결함** | fail2ban·unattended-upgrades 실제 설치·검증 완료. UFW는 GATED + 결함 #3 |
| V1-2 (하드닝 체크리스트) | **PASS** | 5열 표 생성, FAIL 3건을 고치지 않고 원인 분석만 수행 (제약 준수). 실제 노출(ollama) 발견 |
| P1-4 (골든 컨테이너·GPU) | **PASS** | nvidia-smi→GB10, torch 2.9.1+cu130 `True`, `NVIDIA GB10`. 재진입 명령 확인 |
| V1-3 (GPU 계층 진단) | **N/A** | "문제가 있을 때만" 조건부 프롬프트. GPU 정상이므로 미발동 (설계대로) |
| P1-5 (저장소 연결) | **BLOCKED** | GitHub Classroom URL 미제공. git config·교재 clone·week01 생성은 로컬 대체 검증 PASS |
| P1-6 (CLAUDE.md) | **PASS** | 6개 규칙 파일 생성. Claude Code가 세션마다 자동 로드하는 파일이 맞음 |
| P1-7 (스모크 테스트) | **FAIL → 결함 #4** | 교재 원문 명령으로는 **원리적으로 실패**. `--allow-errors` 필요 |
| V1-4 (재현성) | **PASS** | 2회 실행, 53개 코드 셀 출력 차이 **0개**. 완전 재현 |
| P1-8 (제출 마감) | **PASS** | 산출물 3종 + report 템플릿 + .gitignore + 커밋. `git log --oneline` / `git status` 확인 |

## 게이트 판정

| 게이트 | 주장 | 실측 | 판정 |
|---|---|---|---|
| W01-G1 | `aarch64` | `aarch64` | ✅ PASS |
| W01-G2 | 약 128GB (119GiB 내외) | `MemTotal 125484316 kB` = 119.7GiB | ✅ PASS |
| W01-G3 | `NVIDIA GB10` | `GPU 0: NVIDIA GB10` | ✅ PASS |
| W01-G4 | Ubuntu 기반 DGX OS | `Ubuntu 24.04.4 LTS` + `/etc/dgx-release: DGX_NAME="DGX Spark"` (SW 7.2.3 / OTA 7.4.0) | ✅ PASS |
| W01-G5 | UFW active + 22 ALLOW | 미적용 (`상태: 비활성`) — 절차는 `--dry-run` 검증 | ⛔ GATED |
| W01-G6 | fail2ban sshd `Currently banned: 0` | `Currently banned: 0` / `Total banned: 0` | ✅ PASS |
| W01-G7 | 5항목 전부 PASS | 2 PASS / 3 FAIL (2건 의도적 미적용, 1건 실제 노출) | ⛔ GATED |
| W01-G8 | GB10 + torch True + 장치명 | 전부 확인 | ✅ PASS |
| W01-G9 | CLAUDE.md 자동 적용 | 파일 생성 확인. Claude Code의 문서화된 동작 | ✅ PASS |
| W01-G10 | ch02 노트북 2회 무결 실행 | 원문 명령 실패 / `--allow-errors` 시 53/53 셀 + 2회 재현 | ❌ **FAIL** (결함 #4) |

---

# 발견된 결함

## 결함 #1 — 한국어 로케일에서 `lscpu` 파싱 실패 (경미, 환경차이)

**위치**: Week1-2 교재 1.3절 P1-1

**증상**: DGX Spark 기본 로케일이 `LANG=ko_KR.utf8` 이다. `lscpu` 가 한국어 라벨을 출력하므로
에이전트가 흔히 쓰는 `lscpu | grep Architecture` 가 **빈 결과**를 반환한다.

```
$ lscpu | head -3
아키텍처:                         aarch64
CPU 동작 모드:                    64-bit
바이트 순서:                      Little Endian

$ lscpu | grep Architecture      ← 아무것도 안 나옴
$ LC_ALL=C lscpu | grep '^Architecture'
Architecture:  aarch64
```

**분류**: 환경차이. 교재 잘못은 아니지만 학생이 첫 미션에서 막힌다.

**권고**: P1-1의 `[제약]` 에 한 줄 추가 —
`[제약] 이 장비 로케일은 ko_KR 이다. 명령 출력을 파싱할 때는 LC_ALL=C 로 로케일을 고정할 것`

## 결함 #2 — (오판 정정) auth.log 부재는 문제가 아니다

검증 중 `/var/log/auth.log` 가 없어 fail2ban sshd jail이 실패할 것으로 의심했으나, Ubuntu 24.04
fail2ban 패키지는 `/etc/fail2ban/jail.d/defaults-debian.conf` 에서 `backend = systemd` 를 기본값으로
쓴다. 실제 확인: `Journal matches: _SYSTEMD_UNIT=sshd.service + _COMM=sshd` → journald에서 읽으므로
정상. **결함 아님.**

## 결함 #3 — `ufw enable` 이 대화형 확인을 요구 (중간, 교재-프롬프트결함)

**위치**: Week1-2 교재 1.4.2절 P1-3 1번 항목

**증상**: 에이전트가 `sudo ufw enable` 을 비대화형으로 실행하면 프롬프트에서 멈춘다.

```
$ sudo ufw --dry-run enable
명령은 존재하는 ssh 연결에 피해를 줄 수 있습니다. 이 작업과 함께 진행하시겠습니까(y|n)? 중지되었습니다
```

**분류**: 교재-프롬프트결함. 프롬프트가 이 확인 단계를 예고하지 않는다.

**권고**: P1-3에 두 줄 추가 —
- `ufw enable 은 대화형 확인을 요구한다. 확인 문구를 나에게 그대로 보여주고 내 승인을 받은 뒤 --force 로 실행할 것`
- **추가 경고 박스**: Docker가 게시한 포트는 UFW를 우회한다(`DOCKER-USER` 체인). "UFW active"
  만으로 안전을 결론내면 오판이다. 이 장비에서 실제로 `*:11434`(Ollama)가 전 인터페이스에
  노출되어 있음을 확인했다.

## 결함 #4 — P1-7 스모크 테스트가 원리적으로 실패 (**중대**, 교재-수치오류)

**위치**: Week1-2 교재 1.7절 P1-7 + 예상 결과 + 통과 기준, 그리고 V1-4

**증상**: 교재는 이렇게 지시한다.

> 2. `jupyter nbconvert --to notebook --execute` 로 처음부터 끝까지 실행
> **예상 결과:** 정상이라면 오류 없이 완료. 오류가 난다면 대부분 패키지 누락/버전 문제이며 …
> **통과 기준:** 2회 연속 무결 실행.

그런데 대상 노트북 `ch02/01_main-chapter-code/ch02.ipynb` 에는 **교재 저자가 의도적으로 넣은
실패 셀**이 있다. 저장소 원본의 저장된 출력을 세어보면:

```
총 셀 139개 (코드 53개)
원본 저장 출력에 error 가 들어있는 셀: 1개
  code cell #17: KeyError: 'Hello'
     source: tokenizer = SimpleTokenizerV1(vocab)  text = "Hello, do you like tea. ...
```

이 셀은 2주차 P2-4 "의도된 실패"(OOV 시연) 그 자체다. 따라서:

- `--execute` 만으로는 **어떤 환경에서도 100% 실패**한다 (실측: cell #17에서 5.157s 만에 중단)
- 교재의 원인 진단 안내("패키지 누락/버전 문제", "aarch64/CUDA/버전")는 **학생을 엉뚱한 방향으로
  보낸다**. 실제 원인은 환경이 아니라 노트북 자체다
- "2회 연속 무결 실행" 통과 기준은 **달성 불가능**

**정정 후 실측**: `--allow-errors` 추가 시

| 항목 | 결과 |
|---|---|
| 실행 시간 | 10.119s |
| 코드 셀 / 실행된 셀 | 53 / 53 |
| 마지막 셀 execution_count | 53 |
| 오류 셀 | 1개 (의도된 KeyError만) |
| 2회 실행 출력 차이 | **0개** |

**권고 (교재 수정안)**:

P1-7의 2번 항목을 다음으로 교체.
```
 2. jupyter nbconvert --to notebook --execute --allow-errors 로 처음부터 끝까지 실행
    (--allow-errors 를 붙이는 이유: 이 노트북에는 교재가 의도적으로 넣은 실패 셀이 1개 있다.
     2주차에서 배울 OOV 시연 셀이다. 이것 때문에 멈추면 나머지 셀을 검사할 수 없다)
 3. 성공 판정: 마지막 코드 셀까지 execution_count 가 채워졌고, 오류 셀이 '의도된 KeyError' 1개
    뿐일 것. 그 외 오류가 있으면 그것이 환경 문제다
```

예상 결과를 다음으로 교체.
```
**예상 결과:** 코드 셀 53개가 모두 실행되고, 오류는 code cell #17의 KeyError: 'Hello' 단 1개다.
이 하나는 정상이다(교재가 심어둔 OOV 시연). 그 외 오류가 뜬다면 그때가 패키지 누락/버전 문제이며,
에이전트의 원인 분석에서 "aarch64", "CUDA", "버전" 같은 단어가 왜 등장하는지 1.1절과 연결해 보라.
```

통과 기준을 `2회 연속, 의도된 KeyError 1건 외 오류 없이 마지막 셀까지 실행` 으로 교체.
