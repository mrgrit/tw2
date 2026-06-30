# tw2 아키텍처

## 한 줄 정의

학생들이 공유하는 **el34 인프라** (단일 타깃 VM + 별도 외부 공격자 VM) 위에서
**시나리오 기반 Red/Blue 공방전** 을 운영·채점·시각화하는 중앙 플랫폼.

## 기본 모델

```
                ┌──────────────── tw2 중앙 ──────────────────┐
                │                                            │
   학생 (브라우저) │  React UI ──HTTP──▶ FastAPI ─SQL──▶ SQLite │
   관리자        │                       │                    │
                │                       │ httpx + ssh        │
                └───────────────────────┼────────────────────┘
                                        │  X-API-Key
                                        ▼
                          ┌───────── el34 인프라 ──────────┐
                          │  타깃 VM      외부 공격자 VM     │
                          │  192.168.0.80  192.168.0.202  │
                          │  (el34-* 컨테이너)  (att/1)     │
                          │  웹 진입 192.168.0.161          │
                          │  FW→IPS(Suricata)→WAF→앱        │
                          └────────────────────────────────┘
```

el34 인프라는 **공유 실습장**이다. 타깃은 단일 VM `192.168.0.80`(ssh `ccc/1`) 의
`el34-*` 컨테이너 묶음이고, 외부 공격자는 **별도 VM** `192.168.0.202`(att/1) 에서 공개
포트 + Host 헤더만으로 침입한다. 웹 진입점은 `192.168.0.161`. tw2 는 이 인프라의
**Assessor API + 공개 포트**만 본다 → 인프라가 버전업되어도 tw2 는 외부 표면만 보면 동작.

| 표면 | 용도 |
|------|------|
| 80, 443 | 7개 vhost (`*.el34.lab`: juiceshop, dvwa, neobank, govportal, mediforum, adminconsole, aicompanion) |
| 9201 | **Assessor API** (`X-API-Key: ccc-api-key-2026`) — 결정론 RED/BLUE 체크 |
| bastion SSH | 점프 호스트 (el34-bastion) |
| 외부 공격자 SSH | 192.168.0.202 (att/1) — pentest 도구 + 공격 발사대 |
| Wazuh (el34-siem) | manager + indexer (SIEM) |
| MISP / OpenCTI | 위협 인텔 컨테이너 |

**패킷 흐름**: `FW → IPS(Suricata) → WAF(Apache+ModSecurity) → 앱`. 내부망은
`10.20.30/31/32/40.x`. 외부 공격자의 **출처 IP 가 Suricata/ModSec/Wazuh 전 계층에 보존**되어
타깃 인프라의 공격 흔적만으로도 출처 상관(correlation)이 가능하다.

## 데이터 모델

저장소는 **SQLite** (`.data/tw2.sqlite3`). 앱 startup(lifespan)이
`Base.metadata.create_all` + 신규 컬럼 보강(`schema_upgrade`) + 관리자 시드 + 시나리오
자동 import 를 수행하므로 별도 마이그레이션 도구 없이 부팅만으로 스키마가 맞춰진다.

```
User (id, email, name, role: student|admin, ...)
 └ Infra (id, owner_id, name, vm_ip, ssh_user, ssh_pwd_enc, bastion_api_key,
          status, last_smoke_at, last_smoke_result)

Scenario (id, title, description, source: admin|claude|bastion-scrap,
          mission_red, mission_blue, scoring, time_limit_sec, status)

Battle (id, scenario_id, mode: solo|duel|ffa, status, monitor, cohort_id,
        started_at, ended_at, time_limit_sec)
 ├ BattleParticipant (battle_id, user_id, infra_id, role: red|blue|observer|admin, score)
 └ BattleEvent (battle_id, actor_user_id, event_type, target, description,
                detail JSON, points, ts)

Cohort (id, kind, name, parent_id, course_ref)
 └ CohortMembership (cohort_id, user_id)

ScrapPost (id, source, source_url, title, summary, relevance JSON,
           status: pending|approved|rejected, decided_by, spawned_scenario_id)
```

## 공방전 모드

| 모드 | 참가자 | 인프라 매핑 | 비고 |
|------|--------|-------------|------|
| **solo** | 1명 (red+blue 둘 다 본인) | el34 타깃 | 학습/연습. 미션 양쪽 다 직접 수행. |
| **duel (1v1)** | 2명 (A=red, B=blue) | 공유 el34 타깃 | 1:1 대전. 외부 공격자 VM 으로 공격, 타깃 방어 아티팩트로 방어. |
| **ffa** | n명 (자율) | 공유 el34 타깃 | 각자 공격 + 방어 동시. 점수 = 공격 성공 + 방어 성공 합산. |

## 주요 흐름

### Battle 생성
```
admin → POST /admin/battles { scenario_id, mode, participants[], cohort_id? }
          → Battle row + BattleParticipant rows
          → status: pending
```

### Battle 시작
```
admin → POST /battles/{id}/start
          → status: active, started_at = now
          → for each participant.infra_id:
              · Assessor 에 RED/BLUE 미션 spec 전달 (필요 시 provisioner 로 룰 게시)
              · 외부 공격자 VM 에 RoE 게시
          → start monitor task (lab_monitor / auto_monitor)
```

### Monitor (서버 측)
```
periodic:
  · 각 참가자 infra 의 Assessor /activity pull (alert/fim/command/mission_check)
  · scoring rule 평가:
      red — 타깃 공격 흔적(ModSec/Suricata/Wazuh) + 출처 IP 상관
      blue — 방어 아티팩트(suricata/wazuh rule·yara·CDB·auditd) + 로그 분석
  · BattleEvent 추가 + score reflect
  · timeout 또는 mission complete 시 status: completed
```

### 시나리오 자동 생성
```
admin UI → "course3 1~3주차로 공방전" 자연어
   → backend → Claude CLI 호출 (교육 컨텍스트 첨부)
   → Scenario row INSERT (source=claude, status=draft)
   → dry-run 으로 미션 수행 가능성 검증(Assessor reachability) + 채점 기준 자동 기술
   → status: validated → admin 이 활성화 → status: active
```

### Bastion 스크랩
```
scrap_crawler → 외부 RSS/feed 수집 → 보안 키워드 매칭
   → relevance 판정 → ScrapPost INSERT (status=pending)
admin UI → 게시판에서 검토 → 승인 → POST /admin/scrap/{id}/approve
   → 자동으로 Scenario draft 생성 (시나리오 자동 생성 흐름 재사용)
```

## 채점

- **의미 채점**: `claude` CLI (`claude-sonnet-4-6`) 가 제출물의 의도/품질을 평가.
  claude 가 없으면 review 보류(자동 fail 하지 않음).
- **결정론 채점**: Assessor (`192.168.0.80:9201`) 의 RED/BLUE 체크 —
  `file_contains` / `log_contains` / `port_listening` / `process_running` / `wazuh_alert`.
- **RED**(공격) = 타깃 공격 흔적(ModSec/Suricata/Wazuh + 출처 IP). **BLUE**(방어) =
  방어 아티팩트(suricata/wazuh rule·yara·CDB·auditd) + 로그 분석.

## 인증

- **학생/관리자**: bcrypt + JWT (HS256). 관리자 계정은 startup 시 `ADMIN_EMAIL`/`ADMIN_PASSWORD`
  로 시드.
- **tw2 ↔ Assessor/인프라**: `X-API-Key`(기본 `ccc-api-key-2026`). 학생 infra 등록 시
  입력한 키를 그대로 호출에 사용.

## 보안 노트

- [x] `Infra.ssh_password_enc` Fernet 암호화 (`crypto.py`, `.data/fernet.key`).
- [ ] CORS 가 dev origin (5173) 만. prod 배포 시 화이트리스트 정확화.
- [ ] CSRF: 현재 JWT in-localStorage → httpOnly cookie 검토.
- [ ] Rate limiting (signup/login brute).
- [ ] Audit log.
