# SOC W10 — 웹쉘 침해: SQLi→웹쉘→콜백을 포렌식하고 헌팅해 끊어내기

> SOC 관제 트랙 10주차. 선행: W03(웹로그)·W07(osquery 개념)·W09(IR). 인프라: el34. 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 웹쉘은 끈질긴 발판

웹 침투의 흔한 결말 = **웹쉘(web shell)**. 공격자가 웹앱 취약점(SQLi/업로드)으로 서버에 작은 PHP/JSP
파일을 심으면, 그걸 통해 **언제든 명령을 실행**한다. 한 번 심으면 SQLi가 패치돼도 남는다.

```
 SQLi/업로드 → 웹쉘 파일 작성 → 웹쉘로 명령 실행 → 콜백(외부 연결)
   (침투)       (/var/www/shell.php)  (?c=id)          (C2 채널)
```

이번 주는 웹쉘 침해를 **웹 로그로 포렌식**하고 **호스트에서 헌팅**해 끊어낸다.

---

## 2. ① 웹 로그 포렌식 — 침투 경로 복원

Apache access + ModSec audit로 "어떻게 들어와서 무엇을 했나"를 복원:
- **침투**: SQLi/업로드 요청(942/업로드 경로).
- **웹쉘 작성**: 비정상 파일 생성(POST).
- **웹쉘 사용**: 의심 파일(.php)에 대한 반복 GET + 파라미터(?c=, ?cmd=).
```bash
docker exec el34-web sh -c 'sudo grep -aE "\.php\?(c|cmd|exec)=" /var/log/apache2/dvwa_access.log | tail'
```
웹쉘 접근 패턴(스크립트 파일 + 명령 파라미터)이 핵심 단서.

---

## 3. ② 웹쉘 헌팅 — 호스트에서

웹 로그가 가리키는 웹쉘 파일을 호스트에서 찾는다(osquery file) + 콜백 리스너(listening_ports).
```bash
docker exec el34-web osqueryi --json 'SELECT path,size,mtime FROM file WHERE path LIKE "/tmp/%shell%";'
docker exec el34-web osqueryi --json 'SELECT pid,port FROM listening_ports WHERE port>40000;'
```
- 최근 mtime의 .php/.jsp = 의심 웹쉘. 정상 웹 파일과 mtime/위치로 구분.
- 비표준 포트 리스너 = 콜백 채널.

---

## 4. ③④⑤ Contain → Eradicate → Recover

W09의 IR 절차를 웹쉘에 적용:
- **Contain**: 공격 출발지 격리(IDS sid 9510001), 웹쉘 포트 차단.
- **Eradicate**: 웹쉘 파일 제거(rm) + 콜백 프로세스 종료(kill) + osquery로 다른 웹쉘 없는지 재확인.
- **Recover**: 웹 서비스 정상 + 웹쉘 잔재 0 + (취약점 패치 권고).

---

## 5. 실습(lab) 형식 — 8 미션

1. **점검**: 웹 로그 + osquery
2. **웹쉘 침해 재현**: SQLi + 웹쉘 파일 + 콜백 리스너
3. **웹 로그 포렌식**: 침투 경로 복원(access/modsec)
4. **웹쉘 헌팅**: osquery file + 콜백 리스너
5. **Contain**: 출발지 격리(sid 9510001)
6. **Eradicate**: 웹쉘 제거 + 콜백 종료
7. **Recover**: 정상성 + 잔재 0
8. **웹 침해 IR 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서. 격리 룰/웹쉘은 self-clean(공유 인프라 보존).

---

## 6. 다음 주차 (W11) 예고 — 악성코드 C2 비콘

W10은 웹쉘 콜백을 다뤘다. W11은 악성코드 감염 — C2 비콘(주기적 외부 통신)을 IOC로 잡고 감염 호스트를
네트워크 격리하는 대응을 다룬다.
