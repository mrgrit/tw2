# 컴플라이언스 W10 — 변경관리와 파일 무결성 모니터링(FIM)

> 컴플라이언스 트랙 10주차. 선행: W01–W09. 인프라: el34 (web/siem). 플랫폼: tw2. 표준: PCI-DSS 11.5·6.4, ISMS-P 2.9.

---

## 1. 이번 주의 통찰 — 허가받지 않은 변경은 곧 침해의 신호

설정·바이너리·웹 파일의 **무단 변경**은 침해(웹셸 업로드·백도어)거나 통제 우회다. 컴플라이언스는
**모든 변경이 승인된 변경관리 절차를 거치고, 무단 변경은 FIM이 탐지**할 것을 요구한다.

```
 변경관리: 변경요청 → 영향평가 → 승인 → 테스트 → 배포 → 검증 → 기록
 FIM: 승인된 기준선(baseline) ↔ 현재 파일 상태 비교 → 무단 변경 탐지/알림
```

---

## 2. FIM 설정 확인 (Wazuh syscheck)

```bash
docker exec el34-web sh -c "grep -E '<directories' /var/ossec/etc/ossec.conf"
```
- el34-web: `/etc, /usr/bin, /bin, /boot`(정기) + **`/etc/apache2`, `/etc/modsecurity` (realtime,
  whodata)** 모니터링. 핵심 설정 디렉토리를 실시간 감시(준수).

---

## 3. FIM 작동 증적

```bash
docker exec el34-siem sh -c "tail -8000 /var/ossec/logs/alerts/alerts.json | grep -c syscheck"
```
- el34: 다수 syscheck 알림 = FIM이 실제 변경을 탐지·기록 중. (rule 550 변경/554 추가/555 삭제 등)

---

## 4. 무단 변경 탐지 (canary)

모니터링 디렉토리에 파일을 만들면 FIM이 변경으로 인지한다(whodata로 *누가* 까지).

```bash
docker exec el34-web sh -c "echo x > /etc/apache2/canary.txt; ls /etc/apache2/canary.txt; rm -f /etc/apache2/canary.txt"
```
- realtime 디렉토리의 생성/수정/삭제 → FIM 이벤트. 정상 변경관리 외의 변경은 즉시 가시화.

---

## 5. 변경관리 ↔ FIM 연계

```
 승인된 변경: 변경관리 기록 ↔ FIM 알림 매칭 → 정상
 무단 변경:   변경관리 기록 없음 + FIM 알림 → 조사 대상(침해/우회 의심)
 기준선(baseline): 승인 상태를 FIM baseline으로 등록, 이후 일탈을 탐지
```

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: 대상
2. **FIM 설정**: 모니터링 디렉토리
3. **FIM 작동**: syscheck 알림
4. **무단 변경 탐지**: canary
5. **변경관리 프로세스**: 요청~검증
6. **FIM↔변경관리 연계**: 정상/무단 구분
7. **방어**: 무결성 통제
8. **변경관리/FIM 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-X` 로. canary는 self-clean. 신규 설치 없음.

---

## 7. 다음 주차 (W11) 예고 — 사고대응 컴플라이언스

W10은 변경관리/FIM이었다. W11은 사고대응 컴플라이언스(IR 절차·증적·보고 의무)를 다룬다.
