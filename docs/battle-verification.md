# 공방전 배틀 검증·배포 가이드

시나리오(YAML)를 **실제 배틀로 실행 → 실인프라 채점 → 결과표** 까지 재현하는 방법.
새 서버에 배포할 때 이 문서대로 하면 채점이 정상 동작한다.

## 채점 구조 (무엇이 어디서 도는가)

```
학생/하니스 제출 ──▶ tw2 API(:9200)
                         ├─ 결정론 체크(file/log/port/process/wazuh) ──▶ el34 Assessor(:9201)  ── docker exec ──▶ el34-web/ips/siem …
                         └─ semantic 채점 ──▶ claude(라이브)
공격 실행 ──▶ 외부 공격자 VM ──▶ el34 웹진입(:161) ── 흔적 ──▶ ModSec/Suricata/Wazuh (Assessor 가 grep 으로 검증)
```

- **Assessor 는 el34 컴포넌트**다. tw2 레포에 `scripts/el34_assessor.py` 로 **실제 구현**을 포함한다
  (`scripts/mock_assessor.py` 는 무조건 pass 찍는 테스트 stub — 실검증에 쓰지 말 것).
- Assessor 는 el34 **도커 호스트**(`TUBEWAR_REF_TARGET_IP`, 예 `192.168.0.211`)에서 root 로 실행해야
  `docker exec el34-*` 로 로그/포트/프로세스를 검사할 수 있다.

## 1) Assessor 배포 (el34 도커 호스트)

```bash
# el34 호스트(.211)에서:
sudo mkdir -p /opt/tw2
sudo cp scripts/el34_assessor.py /opt/tw2/el34_assessor.py
sudo cp deploy/el34-assessor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now el34-assessor
sudo systemctl status el34-assessor        # active 확인, 0.0.0.0:9201 LISTEN
```

빠른 임시 기동(테스트):
```bash
sudo systemd-run --unit=el34-assessor --collect /usr/bin/python3 /opt/tw2/el34_assessor.py
```

동작 확인(어디서든):
```bash
curl -s http://<el34_ip>:9201/health          # {"ok":true,"assessor":"el34-real"}
# 실 흔적은 PASS, 없는 패턴은 MISS 로 구분되어야 진짜(mock 아님):
curl -s http://<el34_ip>:9201/assess -X POST -H 'content-type: application/json' \
  -d '{"checks":[{"id":"p","type":"port_listening","target":"web","params":{"port":"80"}}]}'
```

> el34 웹진입 IP(`.161`)가 도커 호스트(`.211`)의 로컬 alias 면 `0.0.0.0:9201` 바인딩으로 둘 다 닿는다.
> 별도 호스트면 방화벽/프록시로 `:9201` 을 노출하거나 infra.port_map 을 실제 주소로 맞춘다.

## 2) tw2 쪽 인프라 배선

각 학생 infra 레코드가 Assessor 를 찾도록 `port_map['assessor']` 를 지정한다.
(`assessor_client.resolve_base`: `port_map['assessor']` 있으면 `http://{vm_ip}:{port}`, 없으면 80+Host 헤더.)

```bash
# 예: infra 1,2 를 :9201 로 연결
.venv/bin/python - <<'PY'
import asyncio, sys; sys.path.insert(0,'apps/api')
from sqlalchemy import select
from app.db import SessionLocal
from app.models import Infra
async def m():
    async with SessionLocal() as s:
        for i in (await s.execute(select(Infra))).scalars():
            if i.kind=="target":
                i.port_map={**(i.port_map or {}), "assessor":9201}
        await s.commit()
asyncio.run(m())
PY
```

## 3) 외부 공격자 VM

`.env` 의 `TUBEWAR_REF_ATTACKER_IP` 를 실제 공격자 VM 으로 맞추고, 하니스에는 계정을 넘긴다.
공격자 VM 에는 `curl nmap python3` 가 필요하다(없으면 `sudo apt-get install -y curl nmap`).

```bash
VH_ATT_IP=<공격자IP> VH_ATT_USER=<계정> VH_ATT_PASS=<비번> \
  .venv/bin/python scripts/play_scenario.py <scenario_id> solo
```

## 4) 배틀 실행

단건:
```bash
VH_ATT_IP=... VH_ATT_USER=... VH_ATT_PASS=... .venv/bin/python scripts/play_scenario.py ai-safety-w02 solo
```

전 과목 배치(재개 가능, 결과표 자동 생성 → `docs/battle-results.md`):
```bash
GH_PAT=<선택> VH_ATT_IP=... VH_ATT_USER=... VH_ATT_PASS=... \
  .venv/bin/python scripts/run_all_battles.py            # 전 시나리오
  # 또는 prefix 필터: ... run_all_battles.py ai-safety autonomous-security
```
- `.data/battle_results.json` 에 완료분 저장 → 중단돼도 재실행 시 이어서.
- `GH_PAT` 주면 6건마다 결과표를 커밋·push.

## 채점 해석 (중요)

- **결정론 체크**(log_contains/wazuh_alert/port…)는 Assessor 가 el34 에서 실검증 → 실흔적 있으면 PASS.
- **semantic 미션**(설계·방어)은 claude 가 보고서를 채점 → 좋은 보고서면 만점(예: 실측 battle 5 BLUE-2 25/25).
- `play_scenario` 자동 하니스가 **심는 보고서는 최소본**이라 semantic 만점이 어렵다 →
  RED/설계 미션이 **partial** 로 나오는 것은 정상(하니스 보고 품질 한계이지 시나리오·Assessor 결함 아님).
  실제 학생 제출은 서술이 풍부해 pass 가 나온다.
- **외부 공격자 `command_ran`** 은 6v6 원칙상 미수집 → 그 유형은 타깃 흔적/ semantic 으로 채점(설계상 한계).

## 트러블슈팅

| 증상 | 원인 | 조치 |
|---|---|---|
| 채점 피드백 "인프라 활동 수집 HTTP 404" | Assessor 다운/미배선 | 1)·2) 절 확인, `:9201/health` |
| `infra N not owned by user` | 하니스가 소유 안 한 infra 사용 | `vh.own_infra(email)` 가 소유 infra 자동 선택(적용됨) |
| 공격자 SSH 실패 | `TUBEWAR_REF_ATTACKER_IP`/계정 불일치 | `.env` + `VH_ATT_*` 확인 |
| 모든 미션 fail·증거 404 | Assessor 미배포 | Assessor 먼저 배포 |
