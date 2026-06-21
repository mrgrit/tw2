# 컴플라이언스 W05 — 암호화 컴플라이언스 (전송·저장)

> 컴플라이언스 트랙 5주차. 선행: W01–W04. 인프라: el34 (web 443). 플랫폼: tw2. 표준: PCI-DSS 4·3, ISMS-P 2.7.

---

## 1. 이번 주의 통찰 — 데이터는 두 곳에서 보호해야

데이터는 **이동 중(in transit)** 과 **저장 중(at rest)** 모두 암호화해야 한다. PCI-DSS는 카드 데이터의
전송 암호화(요구사항 4)와 저장 암호화(요구사항 3)를 명시한다. 컴플라이언스는 **강한 알고리즘 사용과
키 관리**를 증적으로 확인한다.

```
 전송(in transit): TLS1.2+ , 강한 cipher(AEAD), 유효 인증서
 저장(at rest):    DB/디스크 암호화(AES-256), 안전한 키 관리(KMS/HSM)
```

---

## 2. 전송 암호화 점검 (PCI-DSS 4)

```bash
echo | openssl s_client -connect 10.20.30.1:443 -servername neobank.el34.lab 2>/dev/null | grep -iE 'Protocol|Cipher'
```
- el34: **TLSv1.3 / TLS_AES_256_GCM_SHA384** → PCI-DSS 4.2.1(강한 암호) 준수. 단 W10에서 본 **자체서명
  인증서**는 신뢰 체인 결함(운영 환경이면 갭).

---

## 3. Cipher 강도 (nmap)

```bash
nmap --script ssl-enum-ciphers -p 443 10.20.30.1
```
- `least strength A` → 약한 cipher(RC4/3DES/EXPORT) 없음. C~F면 PCI 미달.

---

## 4. 폐기 프로토콜 차단

```bash
echo | openssl s_client -connect 10.20.30.1:443 -tls1_1 2>&1 | grep -iE 'no protocols|alert'
```
- PCI-DSS는 **TLS1.0/1.1 사용 금지**. 협상 불가(거부)가 준수.

---

## 5. 저장 암호화·키 관리 (PCI-DSS 3)

```
 저장: 카드/개인정보 = AES-256 등 강한 알고리즘으로 저장 암호화
 키 관리: 생성→배포→보관(KMS/HSM)→교체(주기적)→폐기, 데이터키≠마스터키 분리
```
- **키가 데이터 옆 평문으로 있으면 암호화 무의미**. 키 분리·접근통제가 핵심.

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: HTTPS 도달
2. **전송 암호화**: TLS1.2+ (PCI 4)
3. **cipher 강도**: least strength
4. **폐기 프로토콜**: TLS1.1 거부
5. **저장 암호화**: at rest 개념
6. **키 관리**: 생성~폐기
7. **방어**: PCI-DSS 4·3 정리
8. **암호화 컴플라이언스 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-attacker` 로. 신규 설치 없음(openssl/nmap 기본).

---

## 7. 다음 주차 (W06) 예고 — 로깅·모니터링 컴플라이언스

W05는 암호화였다. W06은 로깅·모니터링 컴플라이언스(PCI-DSS 10, 감사 추적)를 다룬다.
