# TEST_MATRIX — Cohort 위계 + Assessor 연동 + cross-infra 커버리지 매트릭스

> 이번 업그레이드로 추가·변경된 **모든** 기능 ↔ 담당 테스트 매핑. 누락 0 을 증명한다.
> 실행: `bash scripts/dev.sh test` (= `pytest tests/ -v`) + e2e 3종(아래).

## 1. 데이터 모델 / 마이그레이션

| 기능 | 구현 | 테스트 |
|------|------|--------|
| `Cohort` 자기참조 트리 | `models.py:Cohort` | `test_cohort.py::test_cohort_tree_crud_parent_child` |
| `CohortMembership` 다대다 + unique(cohort,user) | `models.py:CohortMembership` | `test_cohort.py::test_membership_many_to_many_and_move` |
| `Battle.cohort_id` (nullable) | `models.py:Battle.cohort_id` | `test_cohort_views.py`, `test_cross_infra.py` |
| 기존 DB 호환 컬럼 보강(create_all 경로) | `schema_upgrade.py:ensure_added_columns` | 전 테스트의 `create_all` 부트스트랩 + `main.py` lifespan |

## 2. 미션 → check-spec 컴파일 (`check_compiler.py`)

| check type 매핑 | 테스트 |
|------|--------|
| file_exists | `test_check_compiler.py::test_direct_file_exists` |
| file_contains | `test_check_compiler.py::test_direct_file_contains` |
| process_running | `test_check_compiler.py::test_direct_process_running` |
| port_listening | `test_check_compiler.py::test_direct_port_listening` |
| command_ran (직접/추론) | `test_direct_command_ran`, `test_infer_command_ran_red_attacker`, `test_empty_expect_falls_back_to_command_token` |
| log_contains (output_contains 추론) | `test_infer_log_contains_from_output_contains` |
| wazuh_alert (rule_id 추출) | `test_infer_wazuh_alert_with_rule_id` |
| semantic→checks 캐시(mission.verify.checks) | `test_cache_checks_idempotent_and_reused`, `test_compile_side_caches_all` |
| target_vm 해석 전파 | `test_target_vm_resolution_propagates` |

## 3. Assessor 클라이언트 (`assessor_client.py`)

| 기능 | 테스트 |
|------|--------|
| URL 해석(80 포트 + Host) | `test_assessor_client.py::test_resolve_url_default_port_80` |
| `port_map['assessor']` 직접 포트 우선 | `test_resolve_url_direct_port_priority` |
| Host/X-API-Key 헤더 | `test_resolve_headers`, `test_assess_sends_battle_id_and_host` |
| `/assess` 호출·파싱 | `test_assess_success_parses_results` |
| 실패는 dict 반환(raise X) | `test_assess_bad_key_returns_dict_not_raise`, `test_assess_unreachable_returns_dict_not_raise` |
| Fake Assessor 픽스처 | `tests/assessor_fake.py` (mock ASGI 앱 + drop-in async) |

## 4. 자동 채점 — auto_monitor / grader / dry_run

| 기능 | 구현 | 테스트 |
|------|------|--------|
| Assessor 기반 blue 자동 채점 | `auto_monitor.py:_tick` | `test_auto_monitor_assessor.py::test_blue_auto_scored_via_assessor_bastion_llm0` |
| (side,order) dedupe | `auto_monitor._seen_hits` | `test_auto_monitor_assessor.py::test_dedupe_no_double_score` |
| fail → 미부여 | `grader.judge_checks` | `test_auto_monitor_assessor.py::test_failed_checks_no_score`, `test_grader_assessor.py::test_failed_check_not_matched` |
| heartbeat in-place collapse 유지 | `auto_monitor._emit_heartbeat` | `test_auto_monitor_assessor.py::test_heartbeat_collapse_in_place` |
| monitor=bastion → LLM 0 | `grader.judge_checks` | `test_grader_assessor.py::test_passed_checks_matched_llm0`, `test_bastion_ambiguous_still_llm0` |
| monitor=claude → 모호할 때만 LLM | `grader.judge_checks` | `test_grader_assessor.py::test_claude_ambiguous_calls_analyzer`, `test_claude_clear_evidence_is_llm0`; `test_auto_monitor_assessor.py::test_monitor_claude_ambiguous_calls_analyzer` |
| 결정론 check → LLM 0 | `grader._deterministic_checks_reasoning` | `test_grader_assessor.py`, `test_auto_monitor_assessor.py` (model=assessor, cost=0) |
| 판정 캐시 | `grader._judge_cache` | `test_grader_assessor.py::test_cache_reuse` |
| dry_run 실제 `/assess` reachability(≥0.7→validated) | `dry_run.assess_reachability` | `test_dry_run_assessor.py` (2건) |

## 5. cross-infra 듀얼

| 기능 | 구현 | 테스트 |
|------|------|--------|
| assess_target 해석(self/opponent) | `battlefield.resolve_target_infra` | `test_cross_infra.py::test_resolve_target_infra_duel`, `test_resolve_target_infra_solo`, `test_normalize_assess_target` |
| red=opponent → 상대 infra 채점 | `auto_monitor._tick` | `test_cross_infra.py::test_red_opponent_assessed_on_blue_infra` + `e2e_cohort_cross_infra.sh` |
| red=self → 본인 infra 채점 | `auto_monitor._tick` | `test_cross_infra.py::test_red_self_assessed_on_own_infra` |
| 권한: 본인 infra 만 등록 | `battle_service.create_battle` | `test_cross_infra.py::test_register_only_own_infra_enforced` |
| red 미션 solved 표기 | `battles.py:_solved_orders` | `test_cross_infra.py` (이벤트 detail), `e2e_cohort_cross_infra.sh` |

## 6. Cohort 라우터 + 필터 뷰

| 엔드포인트 | 테스트 |
|------|--------|
| `POST/GET/PATCH/DELETE /cohorts`, `/cohorts/tree`, `/cohorts/{id}/subtree` | `test_cohort.py::test_cohort_tree_crud_parent_child` |
| 사이클 방지 | `test_cohort.py` (parent→자손 이동 400) |
| `POST/GET/DELETE /cohorts/{id}/members`, `/cohorts/members/move` | `test_cohort.py::test_membership_many_to_many_and_move` |
| admin-only 권한 | `test_cohort.py::test_cohort_admin_only` |
| `BattleCreateIn.cohort_id` 저장/검증 | `test_cohort_views.py::test_battle_create_rejects_unknown_cohort` |
| `/leaderboard/users?cohort_id=` 서브트리 필터 | `test_cohort_views.py::test_cohort_subtree_filter_views_and_identity_only` |
| `/admin/stats?cohort_id=` 스코프 | 〃 |
| `/admin/battles?cohort_id=` 필터 | 〃 |
| 신원-only(null cohort) 정상 | 〃 + `test_cohort_views`, `e2e_identity_only.sh` |
| `POST /admin/battles/{id}/monitor-tick` | `e2e_cohort_cross_infra.sh` (new_events 검증) |

## 7. UI

| 기능 | 구현 | 검증 |
|------|------|------|
| Admin 코호트 탭(트리 편집·배치·이동) | `apps/ui/src/pages/Admin.tsx:CohortsTab` | `npm run build` (tsc strict) green |
| 배틀 생성 cohort 선택 | `Battle.tsx:LobbyCreateDialog` | 〃 |
| Leaderboard/Admin cohort 필터 | `Leaderboard.tsx`, `Admin.tsx:StatsTab/BattlesTab` | 〃 |

## 8. 회귀 (기존 테스트 그대로 green)

`test_smoke` · `test_battle` · `test_lobby` · `test_battle_options` · `test_admin` · `test_audit` · `test_rate_limit` · `test_profile` → 전부 통과 유지.

## 9. 실습 모니터링 (`/activity` → 진도·병목)

| 기능 | 구현 | 테스트 |
|------|------|--------|
| `/activity` pull + 파싱 | `assessor_client.activity` | `test_assessor_client.py::test_activity_pull_parses_lists`, `test_activity_unreachable_returns_empty_lists` |
| 타임라인 적재(dedupe) + cohort 태깅 | `lab_monitor.pull_activity_once` | `test_lab_monitoring.py::test_activity_ingest_timeline_and_cohort_tag`, `test_activity_dedupe_no_double_ingest` |
| 진도(step 통과율) 계산 | `lab_monitor.compute_progress` | `test_lab_monitoring.py::test_progress_computation` |
| 병목 결정론 신호(LLM 0) → 막힌 학생만 CC | `lab_monitor._bottleneck_flags`/`run_lab_tick` | `test_lab_monitoring.py::test_bottleneck_triggers_feedback_only_for_stuck`, `test_no_bottleneck_no_feedback` |
| 신원-only 정상 | `lab_monitor` | `test_lab_monitoring.py::test_identity_only_lab_monitor` |
| 진도 대시보드/타임라인/lab-tick 엔드포인트 | `routers/monitoring.py` | `e2e_cohort_cross_infra.sh` (STEP 10) |

## 10. 중앙 SIEM (코호트 인덱스/뷰/RBAC)

| 기능 | 구현 | 테스트 |
|------|------|--------|
| 코호트 stamp(student/infra/ts/kind/cohort_path/scenario_step) | `siem_export.stamp` | `test_central_siem.py::test_stamp_fields` |
| 물리 인덱스 = 큰 단위(교과목)·하위는 뷰 | `siem_export.physical_index_for` | `test_central_siem.py::test_cohort_path_and_physical_index`, `test_export_events_indexes_to_physical` |
| 데이터뷰/대시보드/RBAC 멱등 생성(reconcile) | `siem_export.ensure_cohort_objects` | `test_central_siem.py::test_ensure_cohort_objects_idempotent_and_rbac_scope` |
| 미설정 시 no-op | `siem_export` | `test_central_siem.py::test_disabled_client_is_noop` |
| 신원-only 인덱스 | `siem_export` | `test_central_siem.py::test_identity_only_index` |
| 딥링크(강사 RBAC 스코프) | `routers/monitoring.py::cohort_siem` | `e2e_cohort_cross_infra.sh` (STEP 10) |

## 11. CC 학생별 피드백

| 기능 | 구현 | 테스트 |
|------|------|--------|
| 피드백 생성(mock CC) + 근거 포함 | `feedback.generate_feedback` | `test_feedback.py::test_generate_feedback_service_manual` |
| 트리거: 병목(자동) | `feedback.bottleneck_feedback_cb` | `test_feedback.py::test_bottleneck_trigger_cb`, `e2e` STEP 10 |
| 트리거: 수동(강사 on-demand) | `routers/feedback.py` | `test_feedback.py::test_feedback_endpoints_and_permissions` |
| 트리거: 종료 | battles end → (옵션) | `test_feedback`(서비스 경로) |
| 저장·전달(student/instructor/both) + 권한 | `routers/feedback.py` | `test_feedback.py::test_feedback_endpoints_and_permissions` |
| 정답 통째 미제공(힌트 수준) | `feedback._SYSTEM`/fallback | `test_feedback`(mock CC 형식) |

## 12. (옵션) 룰 무장

| 기능 | 구현 | 테스트 |
|------|------|--------|
| `arm_rule` 시작 무장·종료 회수 | `provisioner.arm/withdraw_battle_rules` | `test_provisioner.py::test_enabled_arms_and_withdraws` |
| `SKIP_PROVISIONER` 기본 OFF=no-op | `provisioner.is_skipped` | `test_provisioner.py::test_skip_default_is_noop` |
| `/provision-rule` 클라이언트 | `assessor_client.provision_rule` | `test_assessor_client.py::test_provision_rule_arm` |
| Fake Assessor `/activity`·`/provision-rule` | `tests/assessor_fake.py` | 위 테스트들이 사용 |

## e2e (3종)

| 스크립트 | 커버 |
|------|------|
| `scripts/e2e_full_duel.sh` (기존 유지; `e2e_full_duel_run.sh` 부트스트랩) | 로비→join→풀 미션 보고→점수/근거/힌트/리더보드 |
| `scripts/e2e_cohort_cross_infra.sh` | cohort 트리→2학생+infra→cohort-bound cross-infra 듀얼→(mock)Assessor 자동 채점→cohort 필터 리더보드→**lab-tick(/activity→진도·병목)→피드백→SIEM 딥링크** |
| `scripts/e2e_identity_only.sh` | cohort 없이 solo 정상(cohort_id=null) |

> mock Assessor: `scripts/mock_assessor.py`. 실 el34 연동은 `ASSESSOR_LIVE=1` + 실 `vm_ip`(192.168.0.151:9201) 로 확장.
> 콘텐츠 라이브 검수는 `scripts/play_scenario.py` + `scripts/grind_track.py`(el34 실인프라 + claude 채점) 사용.
