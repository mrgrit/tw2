# W03 — IPS 기초 (Suricata): 탐지룰의 구조와 작성

> **이번 주 한 줄 요약**
>
> IPS 장비(`ssh ccc@10.20.31.2`)을 열어, Suricata 탐지룰이 **어떻게 생겼는지**(헤더 + 옵션) 분해해
> 보고, 직접 탐지룰을 작성해 **`local.rules` 에 넣고 reload**한 뒤, 공격을 재현해 **실제로 탐지되는 것을
> eve.json에서 확인**한다. 방화벽이 못 보던 "봉투 안의 내용물"을 IPS가 어떻게 잡는지 익힌다.

---

## 지난주 복습 (30초)

방화벽은 IP·포트(봉투 겉면)만 봅니다. 그래서 "정상 80포트로 들어오지만 안에 공격 문자열을 숨긴"
트래픽은 막지 못했습니다. 이번 주의 **IPS(Suricata)**가 바로 그 내용물을 검사합니다.

## 학습 목표

이번 주가 끝나면 여러분은 **장비에서 직접** 다음을 할 수 있어야 합니다.

1. IPS의 네트워크 구성(어느 인터페이스를 감시하는지)을 안다.
2. IPS의 주요 디렉토리·설정파일·로그(eve.json)가 어디 있는지 안다.
3. **탐지룰의 구조**(헤더 + 옵션)를 분해해 각 부분의 의미를 설명한다.
4. 탐지룰을 직접 작성해, 그 **Suricata rule을 확인하고** 적용·삭제한다.
5. 룰이 **정상 로딩됐는지**(loaded/failed) 즉시 확인한다.
6. 공격을 재현해 **eve.json에서 alert를 직접 확인**한다.
7. IPS를 SIEM(Wazuh)에 연동(이미 연동된 상태 확인).

---

## 1. IPS 장비 둘러보기

el34 호스트 브라우저에서 `ssh ccc@10.20.31.2`에 접속하면 7개 메뉴가 있습니다.

| 메뉴 | 하는 일 |
|------|---------|
| 📊 대시보드 | 가동 여부·로딩 룰 수·실패 수·eve 크기 |
| 🗂️ 구성·디렉토리 | HOME_NET·경로·룰/로그 디렉토리 |
| 🔬 룰 구조 분석기 | 룰을 붙여넣으면 헤더+옵션으로 분해 |
| 📜 탐지룰 관리 | 룰 만들기(미리보기→적용)+로딩 확인 |
| 📈 이벤트(eve.json) | 탐지/접속 이벤트 뷰어 |
| 🛰️ SIEM 연동 | eve.json → Wazuh |
| 🎯 침해대응 훈련 | 탐지룰 작성 시나리오 (다음 주 집중) |

---

## 2. IPS의 네트워크 구성

**구성·디렉토리** 메뉴를 엽니다. IPS(Suricata)는 통로(pipe)와 공개구역(dmz) 사이에 인라인으로
놓여, **지나가는 트래픽의 내용을 검사**합니다. el34의 IPS는 두 개의 다리를 가집니다.

| 다리 | 향하는 곳 | 역할 |
|------|-----------|------|
| pipe 쪽 (10.20.31.2) | 방화벽 쪽 | 방화벽을 통과한 트래픽이 들어오는 통로 — Suricata가 여기를 감시 |
| dmz 쪽 (10.20.32.1) | 웹서버 쪽 | dmz(웹서버·SIEM)로 나가는 쪽 |

또 하나 중요한 설정이 **HOME_NET**입니다. 구성 화면에서 보면:

```
HOME_NET = [192.168.0.0/16, 10.0.0.0/8, 172.16.0.0/12]
```

HOME_NET은 "우리가 지키는 내부망"의 정의입니다. 그런데 우리 실습망은 폐쇄망이라 **공격자
(192.168.0.202)도 10.0.0.0/8 안**에 있습니다. 즉 공격자도 HOME_NET입니다. 그래서 우리 룰은
출발지를 `$EXTERNAL_NET`(외부) 대신 **`any`(아무나)**로 둡니다.

> **초보자 필수 — 왜 `any`인가:** 실무에서는 보통 외부→내부 방향인 `$EXTERNAL_NET -> $HOME_NET`을
> 쓰지만, 폐쇄 실습망에서는 공격자도 HOME_NET 안에 있어 `$EXTERNAL_NET`(=`!$HOME_NET`)에 해당하지
> 않습니다. 그래서 출발지를 `any`로 둬야 공격자 트래픽이 룰에 걸립니다. 이 차이를 아는 것이 중요합니다.

---

## 3. 주요 디렉토리 · 설정파일 · 로그파일

| 항목 | 위치 | 설명 |
|------|------|------|
| 설정파일 | `/etc/suricata/suricata.yaml` | Suricata의 모든 설정(HOME_NET, 감시 IF, 출력 등) |
| 룰 디렉토리 | `/etc/suricata/rules/` | 탐지룰 파일들이 모인 곳 |
| 내 룰 파일 | `/etc/suricata/rules/local.rules` | 우리가 만드는 룰이 쌓이는 파일 |
| 이벤트 로그 | `/var/log/suricata/eve.json` | 모든 이벤트(alert/http/dns/tls/flow)가 JSON 한 줄씩 |
| 빠른 로그 | `/var/log/suricata/fast.log` | alert만 간단히 한 줄씩 |

> **장비가 만드는 룰의 약속:** 직접 작성한 학생 룰은 `local.rules`에 **sid 9000000 이상**으로
> 쌓입니다. 미리 깔려 있는 기본 룰(sid 1000000번대)과 섞이지 않게 분리한 것입니다.

---

## 4. 탐지룰의 구조 — 헤더 + 옵션

이번 주의 핵심입니다. Suricata 룰 한 줄을 봅시다.

```
alert http any any -> any any (msg:"el34 Bot UA - sqlmap"; flow:to_server; http.user_agent; content:"sqlmap"; nocase; sid:1000003; rev:2;)
```

이 룰은 크게 **두 부분**으로 나뉩니다.

### 4.1 헤더 (괄호 앞)

```
alert   http   any any   ->   any any
 ①       ②       ③       ④      ⑤
```

| 번호 | 부분 | 뜻 | 예 |
|------|------|----|----|
| ① | action | 매칭되면 무엇을 할까 | `alert`(경보), `drop`(차단, IPS 모드), `pass`(통과) |
| ② | protocol | 어떤 프로토콜인가 | `http`, `tcp`, `udp`, `dns`, `tls` |
| ③ | 출발지 + 포트 | 어디서 오는가 | `any any`(아무 곳, 아무 포트) |
| ④ | 방향 | 트래픽 방향 | `->`(단방향), `<>`(양방향) |
| ⑤ | 목적지 + 포트 | 어디로 가는가 | `any any` |

### 4.2 옵션 (괄호 안, 세미콜론으로 구분)

| 옵션 | 뜻 |
|------|----|
| `msg:"..."` | 사람이 읽는 설명(경보에 표시됨) |
| `flow:to_server` | 클라이언트→서버 방향의 트래픽만 |
| `http.user_agent` | **탐지 버퍼** — User-Agent 헤더만 검사 (이 다음의 content가 여기에 적용) |
| `content:"sqlmap"` | 그 버퍼 안에서 이 **문자열**을 찾아라 |
| `nocase` | 대소문자 무시(SqlMap도 잡힘) |
| `sid:1000003` | 룰의 고유 번호(Signature ID) — 중복 불가 |
| `rev:2` | 룰의 버전(수정할 때마다 +1) |

> **가장 중요한 개념 — 탐지 버퍼(sticky buffer):** Suricata는 트래픽을 부위별로 나눠 봅니다.
> URL은 `http.uri`, User-Agent는 `http.user_agent`, 요청 본문은 `http.request_body`,
> DNS 질의는 `dns.query` … 처럼요. **버퍼를 먼저 지정하고 그다음 `content`를 쓰면**, content가
> 그 부위에서만 검색됩니다. 룰의 sticky buffer(http.uri 등)가 바로 이것입니다.

### 4.3 룰 구조 분석기로 직접 분해하기

**룰 구조 분석기** 메뉴에 룰을 붙여넣고 "분석"을 누르면, 위 표처럼 헤더와 옵션이 카드로
분해됩니다. 처음 보는 룰을 만났을 때, 이 분석기로 "이 룰이 무엇을 어디서 어떻게 잡는지"를 빠르게
파악할 수 있습니다. **모르는 룰은 분석기에 넣어 보세요.**

---

## 5. 탐지룰 만들기 — 장비가 Suricata rule을 만들어 주는 과정

**탐지룰 관리** 메뉴를 엽니다.

### 5.1 첫 룰 — SQL Injection(UNION) 탐지

상황: 웹 요청 URL에 `UNION SELECT`가 보이는 SQL Injection.

**작성할 룰 (직접 입력):** action `alert`, 프로토콜 `http`, 출발지/목적지 `any`, 탐지 버퍼 `http.uri`,
content `UNION`, **nocase 체크**, flow `to_server`, msg `EDU SQLi UNION`.

**① 룰 미리보기** → 화면에:

```
alert http any any -> any any (msg:"EDU SQLi UNION"; flow:to_server; http.uri; content:"UNION"; nocase; sid:9000001; rev:1;)
```

**② 적용 + reload**를 누르면 — 장비가 이 룰을 `local.rules`에 추가하고 `suricatasc -c reload-rules`로
Suricata에 즉시 반영합니다. 그리고 **로딩 결과**를 보여 줍니다.

### 5.2 로딩 성공/실패를 즉시 확인 (초보자 필수)

reload 직후 suricatasc 가 {"return": "OK"} 를 주고, 로딩 실패면 에러를 알려 줍니다. 만약 룰 문법이
틀리면 `failed`가 올라가고 경고합니다. **즉, 잘못 쓴 룰은 즉시 피드백을 받습니다.** 이것이 룰 작성을
빠르게 배우는 비결입니다.

> **실제 사례 — 잘못된 룰의 위험:** 잘못된 문법(예: `!src_ip`처럼 헤더가 아닌 곳에서 소스 제한)의
> 룰이 하나라도 있으면 Suricata가 룰셋 로딩에 실패(loaded 0)해 **IPS가 아무것도 탐지하지 못하는
> 상태**가 될 수 있습니다. **문법 하나가 전체 방어를 무력화**할 수 있으니, loaded/failed 확인은
> 습관이 되어야 합니다.

---

## 6. 공격 재현 → eve.json에서 탐지 확인

룰을 만들었으면 진짜로 잡히는지 봐야 합니다.

### 6.1 공격 재현

공격자(el34-attacker)에서 sqlmap 흉내 요청을 보냅니다.

```bash
ssh att@192.168.0.202 "curl -A 'sqlmap/1.7' http://juice.el34.lab/?id=1"
```

이 요청은 방화벽(80 허용)을 통과해 IPS가 감시하는 통로를 지나 웹서버로 갑니다. IPS는 지나가는
이 요청의 User-Agent에서 `sqlmap`을 발견합니다.

### 6.2 eve.json에서 확인

**이벤트(eve.json)** 메뉴를 열고 필터를 `alert`로 둡니다. 방금 공격이 alert로 잡혀 있습니다.

```
alert | el34 Bot UA - sqlmap | sid 1000003 | category Web
```

각 alert에는 **signature(설명), sid(룰 번호), category, severity**가 담깁니다. 이벤트 뷰어에서
event_type 필터(alert/http/dns/tls/flow)로 원하는 종류만 골라 볼 수 있습니다.

> **eve.json의 8가지 event_type:** alert(경보) 외에도 http(웹 요청), dns(도메인 질의), tls(암호화
> 연결), flow(연결 흐름), fileinfo(파일), stats(통계), anomaly(이상)이 있습니다. 평소에는 http/flow가
> 가장 많고, 공격이 있을 때 alert가 늘어납니다.

---

## 7. IPS 운영과 로그 분석

운영자는 **대시보드**와 **이벤트** 화면에서 IPS의 건강과 탐지 현황을 봅니다.

- **대시보드:** 가동 여부, **로딩 룰 수**(0이면 큰일), **실패 수**(0이어야 정상), eve.json 크기.
- **이벤트:** event_type 분포로 트래픽 양상 파악. alert가 급증하면 공격 진행 신호.

**로그 분석 3단계(W2와 동일한 습관):** ① **무엇이 보이나**(어떤 sid의 alert가 늘었나?) →
② **무슨 의미인가**(그 signature가 어떤 공격인가 — SQLi? 스캐너? 경로탐색?) → ③ **무엇을 할까**
(출발지 차단(방화벽)? 룰 정밀화? SIEM 경보 확인?).

---

## 8. SIEM(Wazuh) 연동

**SIEM 연동** 메뉴를 엽니다. Suricata의 `eve.json`은 ips의 Wazuh 에이전트가 **이미 감시(tail)**하도록
되어 있습니다(연동: 켜짐). 그러면 IPS의 alert가 SIEM 매니저(10.20.32.100)로 전송되어, Wazuh
대시보드에서 방화벽·WAF의 기록과 함께 시간순으로 볼 수 있습니다.

- Suricata alert → Wazuh의 rule.id(예: 86601 "Suricata Alert")로 매핑됩니다.
- 연동이 꺼져 있으면 "연동 확인/켜기"로 eve.json을 localfile로 추가합니다.

> 이렇게 방화벽(W2)·IPS(이번 주)·WAF(W5)가 모두 SIEM 한 곳으로 모이면, 한 번의 공격이 세 장비에
> 어떻게 다르게 보였는지 한 화면에서 비교할 수 있습니다. 이것이 통합 관제의 힘입니다.

### 8.1 네트워크 탐지(IPS)가 못 보는 곳 — 호스트 가시화로 보충

IPS는 **네트워크 트래픽**을 봅니다. 그래서 통로를 지나는 공격 패턴은 잘 잡지만, **서버 안에서
일어나는 일**(어떤 프로세스가 실행됐는지, 어떤 파일이 만들어졌는지)은 네트워크 선로에 안 보입니다.

이 사각지대는 **호스트 가시화(Sysmon)**가 보충합니다. el34는 `el34-sysmon-host`로 호스트 수준의
프로세스 생성·네트워크 연결·파일 변경을 기록합니다. 그러면 분석가는 한 화면에서:

- **IPS alert**(네트워크에서 본 공격 패턴) +
- **호스트 이벤트**(그 결과 실제로 실행된 프로세스)

를 **시간순으로 연결(상관분석)**할 수 있습니다. 예: "IPS가 의심 요청을 탐지 → 같은 시각 호스트에서
이상 프로세스 실행을 Sysmon이 기록". 네트워크와 호스트를 함께 봐야 공격의 전모가 보입니다.

---

## 9. 이번 주 정리

- IPS(Suricata)는 통로(pipe)와 dmz 사이에서 지나가는 트래픽의 **내용물**을 검사한다.
- 룰 = **헤더**(action/proto/src/dir/dst) + **옵션**(msg/buffer/content/nocase/sid/rev).
- **탐지 버퍼**(http.uri, http.user_agent, dns.query …)를 먼저 지정하고 content로 문자열을 찾는다.
- 장비가 폼을 **Suricata rule**로 변환해 local.rules에 적용하고 reload한다.
- 적용 직후 **loaded/failed**로 룰이 살았는지 확인(문법 오류 즉시 피드백).
- 공격 재현 → **eve.json의 alert**로 실제 탐지를 확인.
- IPS의 eve.json은 **SIEM(Wazuh)**으로 모인다(rule.id 86601).

## 다음 주 예고 (W4 — IPS 침해대응)

다음 주에는 **침해대응 훈련** 메뉴의 시나리오를 본격적으로 풉니다. SQLi·XSS·경로탐색·스캐너·
포트스캔 등 다양한 공격을 각각 탐지하는 룰을 직접 작성하고, 공격을 재현해 잡히는지 확인합니다.
이번 주에 배운 "헤더 + 버퍼 + content"가 무기가 됩니다.

---

## 과제 (제출)

1. 기본 룰(sid 1000003, sqlmap)을 **룰 구조 분석기**에 넣고, 헤더 5부분 + 옵션 각각의 의미를
   표로 정리하세요.
2. 장비에서(sudo) **SQLi UNION 탐지 룰**을 만들어 적용하고, loaded/failed 수를 캡처하세요.
3. sqlmap 공격을 재현한 뒤 **eve.json의 alert** 화면을 캡처하고, signature·sid·category를 적으세요.
4. "탐지 버퍼(`http.uri` vs `http.user_agent`)를 왜 지정해야 하는가"를 3문장으로 설명하세요.
5. (생각) "우리 실습망에서 룰의 출발지를 `$EXTERNAL_NET`이 아니라 `any`로 두는 이유"를 HOME_NET
   개념과 함께 설명하세요.
