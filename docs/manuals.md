# tubewar 매뉴얼 모음

대상별 사용 설명서입니다.

| 대상 | 문서 | 내용 |
|------|------|------|
| 학생 | [manual_student.md](manual_student.md) | 가입·인프라 등록·smoke·공방전 참가·자동/수동 채점·힌트·받은 피드백·리더보드 |
| 교수(강사) | [manual_instructor.md](manual_instructor.md) | 코호트 구성·학생 배치/이동·공방전 출제(cohort-bound/cross-infra)·실습 모니터링·학생 피드백·코호트 리더보드·중앙 SIEM 육안 확인 |
| 관리자 | [manual_admin.md](manual_admin.md) | 설치·환경변수·부트스트랩·관리 콘솔 전 기능·6v6 Assessor 연동·중앙 SIEM 구축·룰 무장(옵션)·운영/장애 대응·테스트·보안 수칙 |

> 시스템 권한은 `student`/`admin` 2단계입니다. 교수 기능(코호트/모니터링/피드백/출제)은 `admin`
> 권한으로 수행하므로, 교수 계정은 관리자에게 admin 권한을 부여받습니다(교수 매뉴얼 권한 안내).

관련 문서: [architecture.md](architecture.md) · [roadmap.md](roadmap.md) ·
[rebuild_prompt_250603.md](rebuild_prompt_250603.md) · 루트 [TEST_MATRIX.md](../TEST_MATRIX.md)
