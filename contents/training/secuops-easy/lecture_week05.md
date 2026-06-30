# W05 — WAF 기초 (ModSecurity): SecRule 의 구조와 작성

> **이번 주 한 줄 요약**
>
> WAF 콘솔(`192.168.136.145:8083`)을 열어, ModSecurity의 탐지룰인 **SecRule**이 어떻게 생겼는지
> (변수 + 연산자 + 액션) 분해해 보고, 콘솔의 폼으로 **직접 SecRule을 만들어 적용**한다. 적용 전
> **configtest**로 문법을 검사해 잘못된 룰이 웹서버를 죽이지 못하게 한다. IPS가 "패킷 문자열"로
> 보던 같은 웹 공격을, WAF는 "**HTTP의 의미**"(파라미터·헤더·본문)로 잡는다.

---

## 지난주 복습 (30초)

IPS(Suricata)는 트래픽 내용에서 **문자열 패턴**을 찾았습니다. WAF(ModSecurity)는 한 걸음 더
나아가 **HTTP 요청을 이해**합니다. "이 값은 URL 파라미터다", "이건 User-Agent 헤더다", "이건
요청 본문이다"를 구분해서, 그 의미에 맞게 검사합니다. 같은 SQLi라도 WAF는 "ARGS(파라미터 값)에
union"으로 잡습니다.

## 학습 목표

이번 주가 끝나면 여러분은 **콘솔만으로** 다음을 할 수 있어야 합니다.

1. WAF의 위치(dmz 웹서버 앞단)와 동작 모드(On/DetectionOnly)를 안다.
2. WAF의 설정파일·CRS·audit 로그가 어디 있는지 안다.
3. **SecRule의 구조**(변수 + 연산자 + 액션)를 분해해 설명한다.
4. 콘솔 폼으로 SecRule을 만들어, 생성되는 **SecRule을 확인하고** 적용한다.
5. **configtest 보호**의 의미를 이해한다(잘못된 룰은 거부, 웹서버 보존).
6. **transform(변환)**으로 인코딩 우회를 막는다.
7. audit 로그에서 **차단·anomaly score·룰 ID**를 읽는다.
8. WAF를 SIEM(Wazuh)에 연동(상태 확인).

---

## 1. WAF 콘솔 둘러보기

el34 호스트 브라우저에서 `http://192.168.136.145:8083/`에 접속하면 7개 메뉴가 있습니다.

| 메뉴 | 하는 일 |
|------|---------|
| 📊 대시보드 | Apache·ModSec·CRS·엔진모드·audit 크기 |
| 🗂️ 구성·CRS | ModSec 설정 + CRS 룰 패밀리 |
| 🔬 SecRule 분석기 | SecRule 분해 + CRS 예시 보기 |
| 📜 SecRule 관리 | 룰 만들기(미리보기→configtest→적용) |
| 📈 audit 로그 | 차단/탐지 이벤트 뷰어 |
| 🛰️ SIEM 연동 | audit.log → Wazuh |
| 🎯 침해대응 훈련 | SecRule 작성 시나리오 (다음 주 집중) |

---

## 2. WAF의 위치와 동작 모드

**대시보드**를 엽니다. WAF는 dmz의 **웹서버(Apache, 10.20.32.80)** 안에서 동작합니다. 외부 요청이
방화벽·IPS를 지나 웹서버에 닿으면, **앱에 전달되기 직전**에 ModSecurity가 검사합니다.

핵심 설정 **SecRuleEngine** 모드:

| 모드 | 동작 | 쓰임 |
|------|------|------|
| `On` | 공격 탐지 시 **실제 차단(403)** | 운영(보호) |
| `DetectionOnly` | 탐지만 하고 통과 | 학습/튜닝(오탐 확인) |
| `Off` | 검사 안 함 | 비활성 |

우리 실습 웹서버는 대부분의 vhost가 `On`(차단) 모드입니다(예: dvwa). juice처럼 학습용으로
`DetectionOnly`인 사이트도 있습니다 — **모드에 따라 같은 공격이 막히기도, 통과하기도** 합니다.
대시보드에는 **OWASP CRS** 버전(3.3.2)도 보입니다. CRS는 다음 절에서 다룹니다.

---

## 3. 주요 설정파일 · CRS · 로그

| 항목 | 위치 | 설명 |
|------|------|------|
| 메인 설정 | `/etc/modsecurity/modsecurity.conf` | SecRuleEngine, audit 설정 등 |
| 내 룰 파일 | `/etc/modsecurity/edu_rules.conf` | 콘솔이 만드는 룰이 쌓이는 파일 |
| CRS 룰 | `/usr/share/modsecurity-crs/rules/` | OWASP 표준 룰셋(941 XSS, 942 SQLi …) |
| audit 로그 | `/var/log/apache2/modsec_audit.log` | 검사 결과 JSON 한 줄씩 |

> **콘솔이 만드는 룰의 약속:** 콘솔로 만든 학생 룰은 `edu_rules.conf`에 **id 9000000 이상**으로
> 쌓입니다. CRS와 겹치지 않게 분리한 것입니다.

### OWASP CRS — 미리 만들어진 표준 룰셋

여러분이 룰을 하나도 안 만들어도 WAF는 이미 수백 개의 CRS 룰로 일반적인 공격을 막습니다.
**구성·CRS** 메뉴에서 패밀리별 룰 수를 볼 수 있습니다.

| 패밀리 | 막는 것 |
|--------|---------|
| REQUEST-941 | **XSS** |
| REQUEST-942 | **SQL Injection** |
| REQUEST-930 | LFI(로컬 파일 인클루전) |
| REQUEST-932 | RCE(원격 명령 실행) |
| REQUEST-913 | 스캐너 탐지 |
| REQUEST-949 | **anomaly 평가**(차단 결정) |

**anomaly scoring(점수 누적) 모델:** CRS는 룰마다 점수를 매깁니다(CRITICAL=5, ERROR=4 …).
한 요청이 여러 룰에 걸려 점수가 임계치(기본 5)를 넘으면 949 룰이 **차단**합니다. 즉 "작은 의심
여러 개가 모이면 차단"하는 방식입니다. 우리가 만드는 룰은 더 단순하게 `deny`(즉시 차단)나
`pass`(탐지만)를 직접 씁니다.

---

## 4. SecRule 의 구조 — 변수 + 연산자 + 액션

이번 주의 핵심입니다. SecRule 한 줄을 봅시다.

```
SecRule ARGS "@rx (?i)union\s+select" "id:942100,phase:2,t:none,t:lowercase,deny,status:403,msg:'SQLi',severity:'CRITICAL'"
```

세 부분으로 나뉩니다.

### 4.1 변수 (무엇을 검사할까)

| 변수 | 검사 대상 |
|------|-----------|
| `ARGS` | 모든 요청 **파라미터의 값** (?q=… 의 …) |
| `REQUEST_URI` | 요청 **URL 전체** |
| `REQUEST_HEADERS:User-Agent` | **특정 헤더**(여기선 User-Agent) |
| `REQUEST_HEADERS` | 모든 요청 헤더 |
| `REQUEST_BODY` | 요청 **본문**(POST 데이터) |
| `REQUEST_COOKIES` | 쿠키 값 |

IPS의 "탐지 버퍼"와 같은 개념입니다. **신호가 있는 부위의 변수**를 골라야 잡힙니다.

### 4.2 연산자 (어떻게 검사할까)

| 연산자 | 뜻 | 예 |
|--------|----|----|
| `@rx` | 정규식 매칭 | `@rx union.+select` |
| `@contains` | 부분 문자열 포함 | `@contains sqlmap` |
| `@pm` | 여러 문구 중 하나(고속) | `@pm sqlmap nikto nmap` |
| `@beginsWith` | 접두어 | `@beginsWith /admin` |

### 4.3 액션 (걸리면 무엇을 할까)

| 액션 | 뜻 |
|------|----|
| `id:9000001` | 룰 고유 번호(필수, 중복 불가) |
| `phase:2` | 검사 단계(1=헤더, 2=본문/파라미터) |
| `t:lowercase` | **변환** — 입력을 소문자로 만든 뒤 검사(대소문자 우회 차단) |
| `t:urlDecodeUni` | **변환** — URL 인코딩을 디코딩한 뒤 검사(인코딩 우회 차단) |
| `deny` | 즉시 차단 |
| `status:403` | 차단 시 응답 코드 |
| `pass` | 통과(로그만) — 탐지 전용 |
| `msg:'...'` | 설명 |
| `severity:'CRITICAL'` | 심각도 |

> **WAF의 슈퍼파워 — transform(변환):** 공격자는 `%3Cscript%3E`(인코딩)나 `UnIoN`(대소문자)으로
> 룰을 피하려 합니다. WAF는 **검사 전에 입력을 정규화**할 수 있습니다. `t:urlDecodeUni`로 먼저
> 디코딩하고 `t:lowercase`로 소문자로 만든 뒤 비교하면, 이런 우회가 무력화됩니다. IPS의 nocase보다
> 강력한 무기입니다.

### 4.4 SecRule 분석기로 직접 분해

**SecRule 분석기**에 룰을 붙여넣고 "분석"을 누르면 변수·연산자·패턴·액션이 카드로 분해됩니다.
**CRS 예시 보기**로 941(XSS)·942(SQLi) 같은 실제 표준 룰도 꺼내 볼 수 있습니다. 처음엔 CRS 룰이
복잡해 보이지만, "변수 + 연산자 + 액션" 골격은 똑같습니다.

---

## 5. SecRule 만들기 + configtest 보호

**SecRule 관리** 메뉴를 엽니다.

### 5.1 첫 SecRule — sqlmap 스캐너 차단

폼에서 — 변수 `REQUEST_HEADERS:User-Agent`, 연산자 `@contains`, 패턴 `sqlmap`, transform
`lowercase` 체크, action `deny`, phase `1`, severity `CRITICAL`, msg `EDU sqlmap block`.

**① SecRule 미리보기** → 화면에:

```
SecRule REQUEST_HEADERS:User-Agent "@contains sqlmap" "id:9000001,phase:1,t:lowercase,deny,status:403,log,msg:'EDU sqlmap block',severity:'CRITICAL'"
```

**② 적용(configtest+reload)**을 누르면: ① 콘솔이 이 룰을 `edu_rules.conf`에 추가하고 ②
**`apache2ctl configtest`**로 문법을 검사합니다. ③ **Syntax OK**면 graceful reload → 룰이 살아납니다.
④ 문법 오류면 → **즉시 직전 상태로 되돌리고** 오류를 보여 줍니다(웹서버는 멈추지 않습니다).

> **configtest 보호의 중요성 (초보자 필수):** 방화벽·IPS와 달리 WAF는 웹서버(Apache)의 일부입니다.
> 잘못된 룰을 그냥 reload하면 **웹서버 전체가 죽습니다.** 그래서 콘솔은 적용 전 반드시 configtest를
> 돌리고, 통과할 때만 반영합니다. 실수해도 안전하게 연습할 수 있는 이유입니다.

### 5.2 deny vs pass — 차단할까 탐지만 할까

새 룰을 바로 `deny`(차단)로 넣으면 정상 사용자가 막힐 위험이 있습니다. 그래서 실무에서는 **새 룰을
`pass`(탐지/로그만)로 먼저 넣어 오탐을 관찰**한 뒤, 안전이 확인되면 `deny`로 바꿉니다. 콘솔의
action 선택이 이 차이를 만듭니다.

---

## 6. audit 로그 분석 — 운영자의 눈

**audit 로그** 메뉴를 엽니다. 각 검사 결과가 한 줄씩 보입니다.

| 항목 | 의미 |
|------|------|
| status | 응답 코드. **403**이면 차단됨 |
| client_ip | 요청을 보낸 출발지(공격자/내부 클라이언트) |
| uri | 어떤 요청이었나 |
| rules | 어떤 룰 ID가 걸렸나(예: 941100 XSS) |
| anomaly score | CRS 점수 합계(임계치 넘으면 차단) |

"차단(403)만" 필터를 켜면 실제로 막힌 요청만 봅니다. 예를 들어 XSS 요청은:

```
차단 403 | GET /?q=<script>... | [941100,941110,949110] | score 15
```

941100·941110(XSS 탐지)이 점수를 쌓아 15가 되고, 949110(anomaly 평가)이 임계치 초과로 차단한
것입니다. 운영자는 이 로그로 "무엇이, 왜 막혔는지"를 정확히 압니다.

**로그 분석 3단계(반복):** ① 무엇이 차단됐나(uri/룰ID) → ② 왜(어떤 공격, 점수) → ③ 무엇을 할까
(룰 정밀화? 오탐이면 예외? 출발지 차단?).

---

## 7. SIEM(Wazuh) 연동

**SIEM 연동** 메뉴를 엽니다. `modsec_audit.log`(JSON)는 web의 Wazuh 에이전트가 **이미 감시(tail)**
합니다. Wazuh의 decoder가 로그 메시지에서 `[id "941100"]` 같은 룰 ID를 뽑아내 alert로 만듭니다.
그러면 WAF의 차단 기록이 SIEM 매니저(10.20.32.100)로 모여, 방화벽·IPS의 기록과 함께 한 화면에서
보입니다.

### 7.1 WAF가 보는 것 — 외부 공격 + 내부 클라이언트의 위험 노출

지금까지 WAF는 "외부 공격자가 웹 앱을 공격하는 것"을 막았습니다. 그런데 audit 로그의 `client_ip`를
보면, WAF는 **요청을 보낸 모든 출발지**를 기록합니다. 공격자(10.20.30.202)뿐 아니라, 어떤 내부
클라이언트가 위험한 요청(예: XSS 페이로드가 섞인 URL)을 보냈다면 그 출발지도 함께 남습니다.

이게 왜 중요한가요? 같은 한 번의 웹 공격이라도 세 장비가 다른 각도로 봅니다:
- **IPS**가 그 트래픽의 페이로드 패턴을 검사하고(네트워크 시그니처),
- **WAF**가 그 HTTP 요청의 의미에서 공격 패턴을 보고(파라미터·헤더),
- **호스트 가시화(Sysmon, el34-sysmon-host)**가 그 결과로 서버에서 실행된 동작을 기록합니다.

셋 다 같은 SIEM으로 모이므로, 분석가는 "**어떤 출발지가 어떤 트래픽을 흘렸고(IPS), 어떤 웹 요청을
했고(WAF), 그 뒤 호스트에서 무슨 일이 있었나(Sysmon)**"를 한 타임라인으로 봅니다. WAF는 외부 공격
차단뿐 아니라 **위험한 요청의 출발지를 식별**하는 창(窓)이기도 합니다. (W6 종합에서 이 흐름을 직접 봅니다.)

---

## 8. 이번 주 정리

- WAF(ModSecurity)는 dmz 웹서버 앞단에서 **HTTP의 의미**를 검사한다(On=차단/DetectionOnly=탐지).
- **SecRule = 변수**(ARGS/REQUEST_URI/REQUEST_HEADERS:…) + **연산자**(@rx/@contains/@pm) +
  **액션**(id/phase/transform/deny|pass/msg/severity).
- **transform**(t:lowercase, t:urlDecodeUni)으로 인코딩·대소문자 우회를 막는다(WAF의 슈퍼파워).
- 콘솔은 적용 전 **configtest**로 문법을 검사해 웹서버를 보호한다(실패 시 자동 복원).
- audit 로그로 **차단·anomaly score·룰 ID**를 분석한다. CRS는 점수 누적으로 차단한다.
- WAF의 audit.log는 **SIEM(Wazuh)**으로 모인다.

## 다음 주 예고 (W6 — WAF 침해대응 30 + 종합)

다음 주에는 **침해대응 훈련** 30개 SecRule 작성 시나리오를 풉니다(SQLi·XSS·LFI·RCE·스캐너·
SSRF 등). 그리고 마지막 종합으로, 같은 공격이 **방화벽·IPS·WAF 세 장비에서 어떻게 다르게
탐지·차단되는지**를 비교하며 6주 특강을 마무리합니다.

---

## 과제 (제출)

1. CRS 942(SQLi) 룰 하나를 **SecRule 분석기**에 넣고(또는 CRS 예시 보기에서 꺼내), 변수·연산자·
   액션을 표로 정리하세요.
2. 콘솔에서 **sqlmap 차단 SecRule**을 만들어 적용하고, 미리보기에 나온 SecRule을 그대로 적으세요.
3. **configtest 보호 실험**: 일부러 잘못된 패턴/액션으로 룰을 적용해 보고, "거부됨 + 웹서버 정상"
   메시지를 캡처하세요. (왜 이 보호가 중요한지 2문장)
4. **transform 실험**: `t:urlDecodeUni`가 있는 룰과 없는 룰로 인코딩된 공격(`%3Cscript%3E`)을
   각각 시도해, 결과(차단/통과)가 어떻게 다른지 설명하세요.
5. audit 로그에서 차단(403)된 요청 1건을 골라, uri·룰ID·anomaly score를 해석하세요.
