# tubewar 아키텍처

## 한 줄 정의

학생마다 1세트 배포된 **6v6 인프라** (단일 VM Docker-Compose, 13 컨테이너) 위에서
**시나리오 기반 Red/Blue 공방전** 을 운영하는 중앙 플랫폼.

## 기본 모델

```
                ┌──────────── tubewar 중앙 ──────────────┐
                │                                       │
   학생 (브라우저) │  React UI ──HTTP──▶ FastAPI ─SQL──▶ PG │
   관리자        │                       │                │
                │                       │ httpx + ssh    │
                └───────────────────────┼────────────────┘
                                        │
                  ┌─────────────────────┼─────────────────────┐
                  ▼                     ▼                     ▼
              학생 A 6v6           학생 B 6v6           학생 C 6v6
              (VM, 13 cont.)       (VM, 13 cont.)       (VM, 13 cont.)
```

학생 각자의 6v6 인프라는 **학생이 직접 운영**한다 (학생 PC 의 VMware Bridge VM).
tubewar 는 **외부에서 이 6v6 의 공개 포트만 본다**:

| 포트 | 용도 |
|------|------|
| 80, 443 | 7개 vhost (juice, dvwa, neobank, govportal, mediforum, admin, ai) |
| 2204 | bastion SSH 점프 |
| 2202 | attacker SSH (pentest 도구 + 공격 발사대) |
| 8000 | portal (관리 대시보드) |
| 5601 | siem-lite (Wazuh alert viewer) |
| 9100 | Bastion API (`X-API-Key` 인증) |

이 표면(surface) 만 사용한다 → 6v6 가 버전업되어도 tubewar 는 외부 API 만 보면 동작.

## 데이터 모델 (Phase 1)

```
User (id, email, name, role: student|admin, ...)
 └ Infra (id, owner_id, name, vm_ip, ssh_user, ssh_pwd_enc, bastion_api_key,
          status, last_smoke_at, last_smoke_result)

Scenario (id, title, description, source: admin|claude|bastion-scrap,
          mission_red, mission_blue, scoring, time_limit_sec, status)

Battle (id, scenario_id, mode: solo|duel|ffa, status, monitor: bastion|claude,
        started_at, ended_at, time_limit_sec)
 ├ BattleParticipant (battle_id, user_id, infra_id, role: red|blue|observer|admin, score)
 └ BattleEvent (battle_id, actor_user_id, event_type, target, description,
                detail JSONB, points, ts)

ScrapPost (id, source, source_url, title, summary, relevance JSONB,
           status: pending|approved|rejected, decided_by, spawned_scenario_id)
```

## 공방전 모드

| 모드 | 참가자 | 인프라 매핑 | 비고 |
|------|--------|-------------|------|
| **solo** | 1명 (red+blue 둘 다 본인) | 자기 6v6 1세트 | 학습/연습. 미션 양쪽 다 직접 수행. |
| **duel** | 2명 (A=red, B=blue) | A 의 6v6 ↔ B 의 6v6 | 1:1 대전. attacker→상대 web/portal/siem 로 공격, 본인 secu/siem 로 방어. |
| **ffa** | n명 (자율) | 각자 6v6 | 각자 공격 + 방어 동시. 점수 = 공격 성공 + 방어 성공 합산. |

## 주요 흐름 (Phase 2 이후 구현)

### Battle 생성
```
admin → POST /admin/battles { scenario_id, mode, participants[] }
          → Battle row + BattleParticipant rows
          → status: pending
```

### Battle 시작
```
admin → POST /battles/{id}/start
          → status: active, started_at = now
          → for each participant.infra_id:
              · 6v6 Bastion API 에 mission spec 전달 (Phase 2 미구현)
              · attacker 컨테이너에 RoE 게시
          → start monitor task (bastion | claude)
```

### Monitor (서버 측)
```
periodic (1~5초):
  · 각 참가자 infra 의 Bastion API GET /run-history (또는 Wazuh alert)
  · scoring rule 평가:
      red — exploit 성공, persistence, exfil
      blue — detect, block, alert ack
  · BattleEvent 추가 + score reflect
  · timeout 또는 mission complete 시 status: completed
```

### 시나리오 자동 생성 (Phase 4)
```
admin UI → "course3 1~3주차로 공방전" 자연어
   → backend → Claude Code SDK 호출 (CCC 의 contents/education/course3/week01..03 컨텍스트 첨부)
   → Scenario row INSERT (source=claude, status=draft)
   → Claude Code 가 6v6 에서 dry-run → 미션이 실제 수행 가능한지 검증 + 채점 기준 자동 기술
   → status: validated → admin 이 활성화 → status: active
```

### Bastion 스크랩 (Phase 5)
```
Bastion (CCC 의 KG-augmented agent) → 외부 RSS/feed 수집 → KG 와 매칭
   → relevance 판정 → ScrapPost INSERT (status=pending)
admin UI → 게시판에서 검토 → 승인 → POST /admin/scrap/{id}/approve
   → 자동으로 Scenario draft 생성 (Phase 4 흐름 재사용)
```

## 인증

- **학생/관리자**: bcrypt + JWT (HS256). 토큰 12h. 새로고침 정책 Phase 6 에서.
- **6v6 ↔ tubewar**: 학생이 등록 시 입력한 `X-API-Key` 를 그대로 호출에 사용. 학생이 6v6
  를 다시 띄울 때 키가 바뀌면 재등록.

## 보안 노트 (Phase 1 → Phase 2 마이그레이션 항목)

- [ ] `Infra.ssh_password_enc` 가 현재 평문. Phase 2 에서 Fernet/age 로 envelope 암호화.
- [ ] CORS 가 dev origin (5173) 만. prod 배포 시 화이트리스트 정확화.
- [ ] CSRF: 현재 JWT in-localStorage. Phase 2 에서 httpOnly cookie 검토.
- [ ] Rate limiting (signup/login brute) — Phase 2.
- [ ] Audit log — Phase 6.
