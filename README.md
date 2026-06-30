# tubewar — 사이버 공방전 훈련 플랫폼
<img width="1347" height="1143" alt="image" src="https://github.com/user-attachments/assets/73a07b5a-efb2-4794-8cd2-771834cb52f9" />


**el34** 사이버 훈련 인프라 위에서 학생들의 **Red/Blue 공방전**을 시나리오·미션 단위로
관리·채점·시각화하는 중앙 플랫폼. (구 `6v6` 인프라 기반 `tubewar` 의 el34 이식판 = 레포 `tw2`)

- **api** — FastAPI (인증·인프라·배틀·시나리오·채점)
- **ui** — React + Vite (학생/강사/관리자)
- **DB** — SQLite (`.data/tw2.sqlite3`) · docker/postgres 불필요
- **인프라(el34)** — 단일 타깃 VM + 외부 공격자 VM (아래 토폴로지)

## 📖 매뉴얼

대상별 사용 설명서: **[docs/manuals.md](docs/manuals.md)**
([학생](docs/manual_student.md) · [교수](docs/manual_instructor.md) · [관리자](docs/manual_admin.md))
설계/운영: [아키텍처](docs/architecture.md) · [운영·배포](docs/operations.md) · [로드맵](docs/roadmap.md)

## 인프라 토폴로지 (el34)

```
        ┌──────────────────────────────────────────┐
        │              tw2 중앙 서버                  │
        │   api(FastAPI) · ui(React) · SQLite        │
        │   채점: claude CLI + el34 Assessor          │
        └───────────────┬────────────────────────────┘
                        │ HTTPS · Assessor API(.151:9201)
   외부 공격자 VM        ▼            타깃 VM (el34, .151)
  ┌──────────────┐   공격 .161   ┌───────────────────────────────┐
  │ 192.168.0.202│ ───────────▶ │ FW → IPS(Suricata) → WAF(ModSec)│
  │   (att/1)    │   출처 IP 보존 │      → 취약 웹앱 · Wazuh SIEM    │
  └──────────────┘              │ el34-{fw,ips,web,siem,           │
                                │  juiceshop,dvwa,neobank,         │
                                │  govportal,mediforum,...}        │
                                └───────────────────────────────┘
```

- **타깃** `192.168.0.80` (ssh ccc/1) — 패킷 흐름 FW→IPS→WAF→앱, 컨테이너 `el34-*`.
- **외부 공격자** `192.168.0.202` (att/1, 별도 VM) — 웹 진입 `192.168.0.161` 로 공격, **출처 IP가 전 계층(Suricata·ModSec·Wazuh)에 보존**.
- **Assessor** `192.168.0.80:9201` (헤더 `X-API-Key`) — RED/BLUE 결정론적 체크(파일/로그/포트/프로세스/Wazuh 경보).
- 취약 웹: dvwa·juiceshop·neobank·govportal·mediforum·adminconsole·aicompanion (vhost `*.el34.lab` 유지).

## 주요 기능

| 영역 | 설명 |
|------|------|
| 회원/인증 | 학생/강사/관리자 계정, JWT. (구글 로그인 옵션) |
| 인프라 등록 | 학생이 **타깃(el34, 역할=target)** 과 **외부 공격자(역할=attacker)** 2개를 등록 → 헬스체크. 미션 지시문의 IP는 등록 인프라로 **자동 치환** |
| 공방전 모드 | **solo**(혼자 Red+Blue) · **1v1(duel)**(Red vs Blue) · **ffa**(자율) |
| 코호트 | 강사가 코호트 트리 구성·학생 배치, 코호트 한정/교차 인프라 출제 |
| 시나리오/미션 | YAML 카탈로그 → DB 자동 import. RED/BLUE 미션 + 채점 기준 |
| 채점 | **claude CLI**(의미 채점) + **Assessor**(결정론 체크). 근거 펼쳐보기 |
| 워크북 | 시나리오별 학생 워크북(.docx) 자동 생성 (`scripts/gen_workbooks.py`) |
| 상황판/리더보드 | 참가자·Red·Blue 점수, 채점 상세, 배틀별·누적 리더보드 |
| 관리자 | 통계·진행중 배틀 강제종료/삭제·사용자 role·시나리오 archive |

## 콘텐츠 (시나리오 128개)

9개 트랙 + 호환 레거시 2개. 모두 el34 인프라에 맞춰 적응·라이브 검수 완료.

| 트랙 | 주차 | 트랙 | 주차 |
|------|------|------|------|
| soc / soc-adv | 15 / 15 | attack / attack-adv | 15 / 15 |
| web-vuln | 15 | compliance | 15 |
| cloud-container | 15 | secuops | 15 |
| secuops-easy | 6 | (legacy 호환) | 2 |

채점 한계는 [contents/battle-scenarios/GRADING-LIMITATIONS.md](contents/battle-scenarios/GRADING-LIMITATIONS.md) 참고
(el34 미보유 텔레메트리: SSH 인증실패·Windows/Sysmon·엔드포인트).

## 배포 (초기 리눅스 → 한방 구축)

```bash
git clone https://github.com/mrgrit/tw2
cd tw2
sudo bash scripts/bootstrap.sh          # 패키지+venv+UI빌드+.env+DB시드+systemd 자동
```

옵션: `--no-systemd`(nohup) · `--demo-users`(데모 학생) · `--dev-ui` ·
`TW2_API_PORT=` / `TW2_UI_PORT=` / `TW2_ADMIN_PASSWORD=` override.

> 미션 지시문의 IP는 콘텐츠에 하드코딩되지 않고 플레이스홀더(`{{TARGET_IP}}`/`{{WEB_ENTRY}}`/`{{ATTACKER_IP}}`)로
> 저장되어, 학생이 **등록한 인프라**로 런타임 치환된다. 미등록 시 폴백 기준 IP는 `.env` 의
> `TUBEWAR_REF_TARGET_IP` / `TUBEWAR_REF_WEB_ENTRY` / `TUBEWAR_REF_ATTACKER_IP` 로 배포마다 설정(기본=el34 기준 랩).

접속: UI `http://<host>:5173` · API `http://<host>:9200` (health `/health`).
관리자 비번은 `.admin-credentials.txt` 에 생성됨. 상세 [docs/operations.md](docs/operations.md).

> ⚠️ 자동 채점은 `claude` CLI(+`TUBEWAR_ANALYZER_MODEL`)가 PATH에 있어야 동작.
> 없으면 플랫폼은 정상이나 채점은 보류(review)됨. 인프라(타깃/공격자)는 배포 환경마다 UI/API로 등록.

## 개발

```bash
bash scripts/bootstrap.sh --no-systemd --dev-ui   # 또는 수동:
python3 -m venv .venv && . .venv/bin/activate && pip install -e "apps/api[dev]"
( cd apps/ui && npm install )
.venv/bin/uvicorn app.main:app --port 9200 --app-dir apps/api     # API
( cd apps/ui && npm run dev )                                     # UI(vite)
```

테스트: `bash scripts/dev.sh test` · 시나리오 검증: `python scripts/validate_scenarios.py`

## 라이선스

MIT.
