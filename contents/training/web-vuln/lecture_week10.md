# 웹취약점 W10 — 전송 보안(TLS): 약한 프로토콜/cipher/인증서 점검 vs 전송 강화

> 웹취약점 트랙 10주차. 선행: W01–W09. 인프라: el34 (web 443). 플랫폼: tw2. WSTG-CRYP.

---

## 1. 이번 주의 통찰 — 데이터는 선(線) 위에서 샌다

A02 Cryptographic Failures. 앱이 아무리 견고해도 전송 구간이 약하면 중간자(MITM)가 평문/세션을
가로챈다. TLS 점검 = 프로토콜 버전, cipher 강도, 인증서 신뢰.

```
 점검 3축
 ① 프로토콜: TLS1.0/1.1(폐기) 거부, TLS1.2/1.3만 허용
 ② Cipher:   약한 cipher(RC4/3DES/NULL/EXPORT) 배제, AEAD(GCM) 선호
 ③ 인증서:   유효 CA 서명, 호스트명 일치, 만료 전, 자체서명 금지
```

---

## 2. 프로토콜/cipher 점검 — openssl

```bash
# 협상된 프로토콜/cipher
echo | openssl s_client -connect 10.20.30.1:443 -servername dvwa.el34.lab 2>/dev/null | grep -iE 'Protocol|Cipher'
# 폐기 프로토콜(TLS1.1) 시도 → 거부되어야 정상
echo | openssl s_client -connect 10.20.30.1:443 -tls1_1 2>&1 | grep -iE 'no protocols|alert|handshake'
```
- el34 web: **TLSv1.3 / TLS_AES_256_GCM_SHA384**(강력 AEAD). TLS1.1은 협상 불가(거부).

---

## 3. cipher 강도 — nmap ssl-enum-ciphers

```bash
nmap --script ssl-enum-ciphers -p 443 10.20.30.1
```
- 각 cipher에 등급(A~F) 부여, `least strength` 가 전체 약점. el34: **TLSv1.2 least strength A**(강함).

---

## 4. 인증서 점검 — 자체서명/호스트명/만료

```bash
echo | openssl s_client -connect 10.20.30.1:443 -servername dvwa.el34.lab 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates
```
- **subject == issuer 이면 자체서명**(브라우저 경고, MITM 식별 불가). el34: `CN=*.6v6.lab` 자체서명 →
  실서비스라면 결함. 또 호스트명(el34.lab)과 인증서(*.6v6.lab) 불일치도 점검 대상.

---

## 5. 방어 — 전송 강화

- TLS1.2/1.3만, 약한 cipher 비활성, AEAD 선호.
- 유효 CA 인증서(자체서명 금지), 호스트명 일치, 만료 모니터링·자동 갱신(ACME).
- **HSTS**(`Strict-Transport-Security`)로 HTTPS 강제, HTTP→HTTPS 리다이렉트.

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: HTTPS 도달
2. **프로토콜/cipher**: openssl s_client → TLSv1.3
3. **cipher 강도**: nmap ssl-enum → least strength
4. **인증서**: 자체서명 탐지(subject==issuer)
5. **폐기 프로토콜**: TLS1.1 거부 확인
6. **영향**: 자체서명/약한 TLS → MITM
7. **방어**: TLS1.2+/AEAD/CA인증서/HSTS
8. **전송 보안 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-attacker` 로. 인가된 실습만.
> 신규 도구 설치 없음 — openssl/nmap 모두 el34-attacker 기본 탑재.

---

## 7. 다음 주차 (W11) 예고 — 에러/정보 노출

W10은 전송 보안이었다. W11은 에러 메시지·스택트레이스·디버그 정보 노출(정보 누출)을 다룬다.
