# 컴플라이언스 W04 — 접근통제 컴플라이언스

> 컴플라이언스 트랙 4주차. 선행: W01–W03. 인프라: el34. 플랫폼: tw2. 표준: ISMS-P 2.5, PCI-DSS 7·8, CIS.

---

## 1. 이번 주의 통찰 — 누가 무엇에 접근하는가

접근통제는 모든 프레임워크의 핵심 통제다. **계정(식별·인증) → 권한(인가) → 정책(암호·세션) → 검토**의
전 주기를 컴플라이언스가 점검한다. 한 곳이라도 느슨하면 침해의 발판이 된다.

```
 식별: 계정 = 사람:계정 1:1, 공유계정 금지
 인증: 강한 암호 정책 + MFA
 인가: 최소권한 + 직무분리
 검토: 주기적 권한 재검토 + 만료
```

---

## 2. 계정 식별

```bash
docker exec el34-web sh -c "awk -F: '\$3==0{print \"UID0:\"\$1}' /etc/passwd; grep -c bash /etc/passwd"
```
- UID 0(root) 계정은 단 하나여야 한다(다중 UID0 = 백도어 의심).

---

## 3. 암호 정책 점검 (PCI-DSS 8 / CIS)

```bash
docker exec el34-web sh -c "grep -E '^PASS_MAX_DAYS|^PASS_MIN_LEN' /etc/login.defs"
```
- el34-web: `PASS_MAX_DAYS 99999` → **암호 무기한(만료 없음)**. PCI-DSS 8.3.9/CIS는 **≤90일** 권고 →
  **갭**. 암호가 영구 유효하면 유출 시 무기한 악용된다.

---

## 4. 파일 권한 (민감 파일 보호)

```bash
docker exec el34-web sh -c "stat -c '%n %a' /etc/shadow /etc/passwd /etc/sudoers"
```
- `/etc/shadow` 640(root:shadow), `/etc/passwd` 644, `/etc/sudoers` 440 → CIS 준수. shadow가
  world-readable(644)면 해시 유출 = 치명 갭.

---

## 5. 최소권한·직무분리

```
 최소권한(Least Privilege): 업무에 필요한 최소 권한만
 직무분리(SoD): 요청자≠승인자, 개발≠운영 (단독 악용 방지)
 권한 재검토: 인사이동·퇴사 시 즉시, 정기 재인증
```

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: 대상
2. **계정 식별**: UID0/계정 수
3. **암호 정책**: PASS_MAX_DAYS 갭
4. **파일 권한**: shadow/sudoers
5. **최소권한·직무분리**
6. **갭 도출**: 암호 만료
7. **방어**: 암호 정책/MFA/재검토
8. **접근통제 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-X` 로. 신규 도구 설치 없음.

---

## 7. 다음 주차 (W05) 예고 — 암호화 컴플라이언스

W04는 접근통제였다. W05는 암호화 컴플라이언스(전송 TLS·저장 암호화, PCI-DSS 4)를 다룬다.
