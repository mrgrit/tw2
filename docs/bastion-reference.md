# Bastion 아키텍처 레퍼런스 (autonomous-security/systems 강의 정합 기준)

> 출처: https://github.com/mrgrit/bastion (면밀 분석). autonomous-security·autonomous-systems 과목의
> **bastion 관련 서술은 반드시 이 문서에 맞춘다.** bastion 업데이트 시 이 문서부터 갱신.

## 한 줄 정의
**Bastion = 자연어 프롬프트로 보안 인프라를 운영하는 "실행 에이전트"**. LLM이 Skill/Playbook을 선택하고
각 VM의 SubAgent에 A2A로 명령을 실행시킨다. "설명해줘"는 Q&A로 빠지고 "실행해줘/확인해줘"가 실제 작업.

## 3단계 처리 (단일 요청, agent.py)
1. **PLANNING** — 4단계 fallback:
   1) 정적 **Playbook** 매칭(`_select_playbook`) → 2) 멀티 **Skill** 선택(`_select_skills_multi`, tool_calls/JSON)
   → 3) **동적 Playbook** 생성(`_generate_dynamic_playbook`) → 4) **Q&A** 직접 답변.
2. **EXECUTING** — 파라미터 자동완성 → `_pre_check`(health_check) → `_assess_risk`(high면 approval_callback Y/n)
   → `execute_skill` → `run_command(ip, script)` → SubAgent A2A → Evidence 기록.
3. **VALIDATING** — 실행 결과를 LLM으로 스트리밍 분석 → EvidenceDB 저장.

## SubAgent · A2A (bastion/__init__.py)
- 각 VM에 **SubAgent** 상주(SSH 온보딩으로 설치). 포트 **8002**.
- `GET /health` (health_check) · `POST /a2a/run_script {"script":...}` → `{stdout,stderr,returncode}`.
- run_command = SubAgent A2A(또는 docker exec/ssh)로 자산에 작용.

## 하니스 엔지니어링 (harness.py · harness_gen.py · orchestrator.py)
- **하니스 = 다중 페르소나 팀 + 단계(phase) 워크플로 + 도구 경계 + 의존순서(depends_on) + 생성-검증 루프 + 무발화 리더.**
- **페르소나 = 논리적 서브에이전트(매니저 측)** — 컨테이너에 안 묶임, execute_skill→run_command로 자산에 작용.
  페르소나 예: `soc-lead`(무발화 리더/검증자), `soc-triage-analyst`, `threat-hunter`, `siem-log-analyst`,
  `network-firewall-analyst`, `vuln-asset-manager`, `forensics-malware-analyst`, `ai-security-analyst`,
  `red-team-operator`. 각 페르소나 `model_tier`(reasoning/execution/attack) + 필요 자산(PERSONA_ASSET_REQ).
- **orchestrator.run_harness() = 6단계**: P0 입력수집 → P1 팀생성 → P2 위상정렬 태스크배치 →
  P3 fan-out(동시성 상한, 페르소나 스코프 ReAct) → P4 생성-검증 루프(≤max_retries) → P5 통합·영속화.
- **harness_gen(자동생성)**: discovery(인프라 발견) + Experience Graph → HarnessSpec 합성. SOC 라이프사이클
  템플릿(트리아지→조사→봉쇄·탐지→(퍼플)→보고)을 존재하는 자산·페르소나로 파라미터화.

## Skill · Playbook
- **Skill** = 원자 도구(skills.py `SKILLS`). 카테고리: recon(probe_host/scan_ports/web_scan/cve_lookup…),
  defense(check_suricata/check_wazuh/check_modsecurity/analyze_logs), response(configure_nftables/deploy_rule/
  enroll_wazuh_agent), attack/RED(attack_simulate/password_attack), forensic(forensic_collect/ioc_export),
  ai-security(prompt_fuzz/garak_probe/model_isolate/rag_corpus_check), compliance(compliance_scan/secret_scan),
  history(anchor/narrative), shell(fallback). 각 Skill: description·params·target_vm.
- **Playbook** = YAML 워크플로(contents/playbooks/): incident_response, hardening, vuln_scan, security_audit,
  log_investigation, wazuh_health, attack_simulation, probe_all. 정적(YAML) + 동적(LLM 생성).

## 지식·경험·기억 (E.G 아님 — 실제 구성)
- **Knowledge Graph** (graph.py): 노드 = Playbook·Experience·Skill·Error·Recovery·Asset·Concept. 원칙
  "동일 작업=동일 방법: **playbook이 법, experience는 보조 노트**". 정적 lookup 대신 **그래프 traversal**.
- **Experience Learning** (experience.py): **오버피팅 방지** — 카테고리 일반화, **3회+ 성공** 승격, **70%+ 성공률**,
  부정(실패) 경험 경고, LRU 100개, 시간 감쇠.
- **EvidenceDB** (SQLite, evidence-first): evidence(skill/playbook_id/params/output/success/analysis/stage/
  exit_code/session/course/lab_id/step_order) + assets(role/ip/status/last_seen).
- **KG Context Builder** (kg_context.py): 모든 LLM 호출이 KG 검색을 system prompt에 자동 주입(tier-aware,
  모델별 token budget: gemma 1500 / gpt-oss 4000).
- **history + compaction**: 최근 12턴 유지, 초과 시 오래된 6턴 LLM 요약 압축. **RAG**(rag.py) 지식 인덱스.

## 감사 (audit.py)
- **Append-only + Hash chain** — 각 row가 직전 row 해시 포함 → 한 줄 변경 시 이후 전부 깨짐(변조 즉시 감지).
- 1 chat = 1 row: request_id·user_prompt(전문)·final_answer·approval_mode·lookup{decision,playbook_id,confidence}·
  turns[ReAct trace]. 외부 SIEM 포워딩 가능.

## LLM 티어
- **Manager AI** = `gpt-oss:120b` (분석·계획·피드백·CTF 생성, reasoning tier).
- **SubAgent/챗봇** = `gemma3:4b` (경량 실행 tier). LLM_BASE_URL=ollama.

## VM 토폴로지 (bastion 기준)
attacker(공격 도구) · secu(방화벽/IDS) · web(웹서버) · siem(SIEM/로그) · manager(AI/관리). 각 VM에 SubAgent(:8002).
(주의: el34 토폴로지 fw/ips/web/siem/bastion 과는 별개 — bastion 자체는 secu/web/siem/attacker/manager 기준.)

## 운영 규칙 (CCC.md)
파괴적 작업(rm -rf /, DROP TABLE) 금지 · 학생 데이터 삭제 금지 · 서비스 중지/재시작은 사용자 확인 · 배포 전 git status.
장기 기억/지침 = CCC.md(시작 시 system prompt 주입), 학습 내용 = .ccc/memory/.
