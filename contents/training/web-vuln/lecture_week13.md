# 웹취약점 W13 — 자동화 스캐닝: nuclei/dalfox 템플릿 점검 vs 자동화의 한계

> 웹취약점 트랙 13주차. 선행: W01–W12. 인프라: el34 (juice/dvwa). 플랫폼: tw2.
> 도구: nuclei(v3.3.5), dalfox, httpx — el34-attacker 탑재. **템플릿은 별도 설치(§2.1)**.

---

## 1. 이번 주의 통찰 — 빠른 대량 점검, 그러나 만능 아님

수동 점검(W01~W12)은 정밀하나 느리다. nuclei 같은 템플릿 스캐너는 수천 개 알려진 패턴(CVE,
오설정, 노출)을 **수 분에 대량 점검**한다. 단, **로직/인가 취약점(BOLA·비즈니스 로직)은 못 잡는다** —
자동화는 수동 점검을 보완할 뿐 대체하지 못한다.

```
 nuclei: 템플릿(YAML) 기반 — CVE/오설정/노출/기술탐지 수천 개
 dalfox: XSS 특화 스캐너 — 파라미터 자동 변이/검증
 httpx:  대량 호스트 프로빙(상태/타이틀/기술)
```

---

## 2. nuclei 기본

```bash
nuclei -u http://10.20.30.1 -H 'Host: juice.el34.lab' \
  -t /root/nuclei-templates/http/technologies/tech-detect.yaml \
  -t /root/nuclei-templates/http/misconfiguration/http-missing-security-headers.yaml -silent -nc
```
- el34 실결과: `tech-detect:google-font-api`, `http-missing-security-headers:strict-transport-security`(HSTS
  누락), `content-security-policy`(CSP 누락) 등 9건.

### 2.1 설치 과정 — nuclei 템플릿 (el34-attacker 인터넷 차단 우회)

nuclei **바이너리는 이미 탑재**(`/usr/local/bin/nuclei`)되어 있으나 **템플릿이 비어 있다**. 보통
`nuclei -update-templates` 로 자동 내려받지만, **el34-attacker 컨테이너는 내부망 전용이라 인터넷이
차단**(github 도달 실패, curl 000)되어 자동 다운로드가 불가능하다. 따라서 **인터넷이 되는 el34 호스트에서
받아 컨테이너로 복사**한다.

```bash
# (el34 호스트, ssh ccc@192.168.0.151)
# 1) 호스트에서 템플릿 얕은 클론(인터넷 O)
cd ~ && git clone --depth 1 https://github.com/projectdiscovery/nuclei-templates
#   → http/ 하위 약 10,964개 .yaml

# 2) 컨테이너로 복사 (docker cp 는 dest 존재 시 그 안에 중첩되므로 평탄화)
docker cp ~/nuclei-templates el34-attacker:/root/nuclei-templates
docker exec el34-attacker sh -c \
  'mv /root/nuclei-templates/nuclei-templates /root/nt; rm -rf /root/nuclei-templates; mv /root/nt /root/nuclei-templates'

# 3) 확인
docker exec el34-attacker sh -c 'find /root/nuclei-templates/http -name "*.yaml" | wc -l'   # 10964
```

**왜 이렇게?** 내부망 침투 호스트(attacker)는 의도적으로 외부 통신이 막혀 있다(현실의 침해 발판도 종종
egress 제한). 도구 자체는 오프라인으로 동작하므로, **시그니처/템플릿만 신뢰 경로(호스트)에서 주입**하는
것이 표준 패턴이다. 같은 방식으로 nuclei 템플릿은 주기적으로 갱신(호스트 `git pull` 후 재복사)한다.

### 2.2 dalfox / httpx

- `dalfox` (XSS 특화), `httpx` (대량 프로빙) 는 별도 템플릿이 필요 없어 **추가 설치 없이 즉시 사용**.

---

## 3. dalfox — XSS 자동 점검

```bash
dalfox url "http://10.20.30.1/?q=test" -H 'Host: dvwa.el34.lab' --silence
```
- el34 dvwa는 ModSec(941)이 XSS를 차단 → dalfox 무탐. **"무탐 = 안전"이 아니라 "이 스캐너·이 표면에서
  못 찾음"** — WAF가 가린 것일 수도, 다른 파라미터일 수도.

---

## 4. 자동화의 한계

- **로직/인가 취약점**(BOLA·권한상승·비즈니스 로직)은 템플릿화 불가 → 자동 스캐너가 못 잡음(W12 BOLA).
- **오탐/미탐**: 컨텍스트 모름. WAF 뒤·인증 뒤 표면 누락.
- **결론**: 자동화로 넓게 훑고(빠름), 수동으로 깊게 검증(정밀). 둘은 보완 관계.

---

## 5. 방어 — 스캐너 결과 활용

- nuclei가 짚은 누락 보안 헤더(CSP/HSTS/Referrer-Policy) 추가.
- CVE 템플릿 정기 스캔 → 알려진 취약 버전 패치 추적.
- 스캐너를 CI/CD에 통합(배포 전 회귀 점검), 단 수동 점검과 병행.

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: 대상
2. **기술 탐지**: nuclei tech-detect
3. **보안 헤더 누락**: nuclei missing-security-headers
4. **HSTS 누락 확정**: strict-transport-security
5. **XSS 자동화**: dalfox (WAF 차단 관찰)
6. **자동화 한계**: 로직/인가 미탐
7. **방어**: 보안 헤더/CVE 패치
8. **자동화 스캐닝 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec el34-attacker` 로. 인가된 실습만.

---

## 7. 다음 주차 (W14) 예고 — 취약점 보고/위험 평가

W13은 자동화 스캐닝이었다. W14는 발견 취약점의 위험 평가(CVSS)와 전문 보고서 작성을 다룬다.
