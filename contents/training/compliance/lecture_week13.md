# 컴플라이언스 W13 — 제3자·공급망 위험

> 컴플라이언스 트랙 13주차. 선행: W01–W12. 인프라: el34 (web/juice). 플랫폼: tw2. 표준: ISMS-P 3.x, NIST SSDF, SBOM.

---

## 1. 이번 주의 통찰 — 내 보안은 가장 약한 협력사만큼

현대 시스템은 OS·라이브러리·CDN·SaaS·수탁사로 구성된다. **내가 통제하지 못하는 제3자 구성요소**가
침해 경로가 된다(SolarWinds·Log4Shell). 컴플라이언스는 **공급망 가시성(SBOM)과 제3자 위험관리**를
요구한다.

```
 공급망 위험
 ① 소프트웨어 의존성: 라이브러리/패키지 CVE (Log4Shell)
 ② 외부 서비스/CDN:   compromised CDN, malicious script
 ③ 수탁사/벤더:       위탁 처리자의 보안 수준
```

---

## 2. 소프트웨어 구성 식별 (SBOM의 기초)

```bash
docker exec el34-web sh -c "apache2 -v | head -1; openssl version; dpkg -l | grep -ciE 'apache2|openssl|libssl'"
```
- el34-web: Apache 2.4.52, OpenSSL 3.0.2 등. **무엇이 설치됐는지 목록화(SBOM)** 가 공급망 관리의 출발점 —
  목록 없이는 CVE 영향 평가 불가.

---

## 3. 외부 의존성 식별

```bash
curl -sk -H 'Host: juice.el34.lab' http://10.20.30.1/ | grep -oE 'https?://[a-z.]+' | grep -v el34
```
- el34 juice: **fonts.googleapis.com / fonts.gstatic.com**(Google Fonts CDN) 외부 의존. CDN 침해/변조 시
  앱에 악성 스크립트 주입 가능 = 제3자 위험.

---

## 4. 알려진 취약점 매핑

```
 구성요소 버전 → CVE 데이터베이스 대조(Apache 2.4.52 → 해당 CVE)
 SCA/SBOM 도구(nuclei CVE 템플릿, Trivy, Dependency-Check)로 자동 매핑
```

---

## 5. 공급망 통제

```
 SBOM: 구성요소 목록 유지·갱신
 의존성 고정: 버전 핀(pin) + 정기 업데이트
 무결성: SRI(Subresource Integrity)로 외부 스크립트 변조 탐지, 서명 검증
 벤더 실사: 수탁사 보안 점검·계약(SLA·감사권)
```

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: 대상
2. **소프트웨어 구성**: 버전/SBOM
3. **외부 의존성**: Google Fonts CDN
4. **취약점 매핑**: 버전→CVE
5. **제3자 위험 평가**
6. **공급망 통제**: SBOM/SRI/실사
7. **방어**: 공급망 보안
8. **공급망 위험 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-X` 로. 신규 설치 없음.

---

## 7. 다음 주차 (W14) 예고 — 감사·증적 수집

W13은 공급망이었다. W14는 감사·증적 수집(audit evidence, 내부감사/인증심사 준비)을 다룬다.
