# 콘텐츠 품질 하네스 (content_harness)

훈련 콘텐츠(`contents/training/<course>/lab_week*.yaml`, `lecture_week*.md`)가 **사람이 하는 방식**인지
**기계식 박스체크**인지 전수 점검한다. harness-engineering 원리: 열거→규칙별 판정→매니페스트.
**샘플링 금지** — 모든 명령/줄을 규칙에 통과시킨다. "완료"는 fail 0 + 실행 로그로만.

## 실행
```bash
# 정적 안티패턴 (모든 과목)
python3 scripts/content_harness/anti_patterns.py 'contents/training/attack/lab_week*.yaml'
# 라이브 기능검증 (el34 필요 — 명령을 실제 실행해 pass/fail)
python3 scripts/content_harness/verify_commands.py 'contents/training/attack/lab_week*.yaml'
```

## 점검하는 "사람 방식 위반" 전체 목록 (규칙은 anti_patterns.py CATS 에 계속 추가)

### 기능 버그 (F)
- **F-도달불가**: 외부 공격자(`ssh att@192.168.0.202`)가 내부 IP(10.20.30.x 등)로 curl → 도달 불가(000).
  → 자연 URL(`http://<vhost>.el34.lab/`, hosts 등록)로.
- **F-구IP**: `10.20.30.202`(구 내부 attacker) → `192.168.0.202`(외부 attacker 출처, el34 보존).
- **F-sudo 없는 root명령**: `ssh ccc@장비 'nft/suricatasc/apache2ctl/wazuh-control/...'` 에 sudo 누락 → 권한거부.

### 기계식 (M) — "사람이 하는 것처럼" 바꿔야
- **M-docker exec**: 남의 컨테이너를 `docker exec`로 조작 → 해당 장비에 `ssh ccc@<IP>` 직접 접속.
- **M-매직 -H Host+생IP**: `-H "Host: X" http://생IP/` 반복 → 자연 URL.
- **M-제어API curl**: GUI 콘솔/Assessor 등 **제어plane API**를 curl로 호출(기계) → 장비 SSH+CLI, 또는 Postman/Burp.
- **M-curl로 리버스프록시**: 웹 vhost(WAF 프록시 뒤)를 raw curl. **실제 사람은 그렇게 안 씀 → 브라우저/Burp/Postman.**
  ★고침 원칙: **curl 삭제 금지(CLI/채점/자동화 가치 있음) — 사람방식(브라우저/Burp)을 옆에 병기.** (sqlmap/dalfox 공격은 정당.)
- **M-python -c**: 그냥 명령이면 될 걸 python 스크립트 (예: base64 → `echo .. | base64 -d`). scapy(패킷크래프팅)는 정당.
- **M-cat<<EOF 보고서**: 미리 쓴 보고서 텍스트를 `cat <<EOF`로 출력 → 학생이 실제로 작성(편집기).
- **M-echo 캔드 해석**: 분석/결론을 `echo "→..."`로 박아 grep 통과 → 학생이 실제 데이터 보고 판단하게.
- **M-공격인데 -o /dev/null**: 익스플로잇 쏘고 응답 버림(코드만) → 해커는 화면 봄. 응답을 보게.
- **M-2>/dev/null 에러 숨김**: 실패를 성공처럼 → 제거하거나 의도 명시.
- **M-sleep / grep -c 숫자축소 / for seq 반복**: 인위적 타이밍·박스체크·반복 → 필요성 재검토, 도구 대체.

### 판단 원칙
맹목 삭제 금지 — **문맥**을 본다. 도달성 점검의 `-o /dev/null`은 정당, 익스플로잇의 것은 아님.
verify가 echo 키워드를 채점하면 박스체크(나쁨), 순수 주석이면 봐줄 만함. 규칙은 **후보를 플래그**할 뿐, 고칠지는 사람이 문맥으로 판정한다.
**★고침 방식 = 병기(annotate), 삭제 아님.** 이미 있는 명령(curl 등)은 두고, 사람이 하는 방식을 옆에 더한다.
