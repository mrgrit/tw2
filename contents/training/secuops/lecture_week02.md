# Week 02 — 방화벽 운영 (nftables) — nft CLI + 침해대응

> **본 주차 한 줄 요약**
>
> 우리는 **방화벽을 만드는 엔지니어가 아니라 운영하는 사람** 의 시각으로 nftables 를 배운다.
> el34 의 fw 컨테이너에서 `nft` CLI 를 직접 다루며 — 룰 작성, 객체(그룹), NAT, stateful 연결추적,
> 카운터/로그 까지 — **공격 상황 7건** 을 직접 막아 보면서, 인프라(방화벽) 로 **공격에 대응** 하는
> 1차 관문을 익힌다. (엔드포인트 가시성의 빈틈은 **W06 osquery / W07 엔드포인트 IR / W11
> sysmon-for-linux** 에서 채운다.)

---

## 0. 학습 목표

본 주차가 끝나면 운영자(여러분)는 다음을 **`nft` CLI 로** 한다.

1. `ssh ccc@10.20.30.1 sudo nft list ruleset` 로 방화벽의 인터페이스, 테이블(`inet six_filter`/`ip six_nat`), 룰셋, 객체(set), conntrack 을 읽는다.
2. `nft` 명령으로 룰을 만들고 그 의미를 정확히 읽는다.
3. 룰 **평가 순서**(top vs bottom, accept 의 단락 효과)와 **rate limit / ct state / 객체 참조** 를 자유롭게 조합한다.
4. **DNAT/SNAT/MASQUERADE** 를 prerouting/postrouting 에 올바르게 배치한다. **web Apache(L7) 와 방화벽 NAT(L4) 의 역할 분담**을 이해한다.
5. **conntrack** 표를 읽어 stateful 의 의미와 운영 상황(NAT 끊김 4 패턴)을 진단한다.
6. **카운터(packets/bytes)** 와 **nft ruleset 상태** 를 침해 증거로 활용한다.
7. **침해대응 시나리오 7건** (악성 IP / 포트 스캔 / SSH brute / ICMP flood / 화이트리스트 / DNAT 위험 노출 / C2 egress 차단) 을 실제 `nft` 로 만들고 효과를 카운터로 증명한다.
8. **가시성의 한계** 를 안다 — 방화벽은 내부 엔드포인트 행위를 못 본다. 그래서 **호스트 가시화(osquery, sysmon-for-linux)** 와 함께 본다.

> **본 주차의 시선** — 방화벽 "벤더 엔지니어" 의 시선이 아니라 **"방화벽을 사서 운영하는 사람"** 의
> 시선이다. el34 의 fw 는 별도 GUI 콘솔 없이 **`nft` CLI** 로 운영한다. 명령을 통째로 외울 필요는
> 없지만 **읽고 쓸 줄은 알아야** 운영자다.

---

## 1. 용어 8개 (꼭 알아야 할 것만)

| 용어 | 뜻 | 운영자에게 의미 |
|------|----|----------------|
| nftables | 리눅스 커널의 방화벽 도구 (iptables 후속) | 우리 el34 방화벽의 엔진 |
| 테이블 / 체인 / 룰 | 룰의 컨테이너 / 트리거 지점 / 매칭+동작 | "룰을 어디에 두는가" 의 단위 |
| input / forward / output | 방화벽 자신에게 / 통과해 / 나가는 트래픽 | 룰 만들 때 가장 먼저 정할 칸 |
| ct state (established/related/new) | 연결의 상태 | stateful 의 핵심. new 만 검사, 응답은 자동 통과 |
| 카운터 (packets/bytes) | 룰이 매칭한 횟수·바이트 | **차단 효과의 증거** (운영자가 매일 본다) |
| named set (객체/Alias) | IP·포트의 재사용 그룹 | "악성 IP 목록 한 곳에서 관리" |
| DNAT / SNAT | 목적지 / 출발지 주소 변환 | DNAT=공개, SNAT=내부 위장 |
| web Apache (L7) | 7계층 reverse proxy + WAF (web 컨테이너) | Host 헤더로 vhost 라우팅. 방화벽 NAT 과 역할 분담 |

> **버려도 되는 깊이**: Netfilter 5 hook 의 hook 우선순위 내부, conntrack helper 모듈 목록,
> iptables-translate 같은 마이그레이션 도구, nft 의 internal data structure — 이런 건 운영자가
> 외울 필요 없다. 매뉴얼이 있다. 본 강의의 시간은 "운영" 에 쓴다.

---

## 2. fw 컨테이너 `nft` CLI 둘러보기

el34 의 fw 는 별도 GUI 콘솔이 없다. 운영자는 호스트에서 fw 컨테이너에 들어가 `nft` 로 운영한다.

```bash
ssh ccc@192.168.0.80                 # el34 호스트 (비밀번호 1)
ssh ccc@10.20.30.1                     # fw 장비 (ccc, sudo 보유)
```

| 운영자가 매일 보는 것 | nft / 도구 명령 |
|----------------------|----------------|
| 인터페이스 (fw 의 양다리) | `ip -br a` → `eth0`(ext .30.1) / `eth1`(pipe .31.1) |
| 전체 룰셋 | `nft list ruleset` |
| 필터 정책 / 체인 | `nft list table inet six_filter` |
| 객체(그룹/set) | `nft list sets` |
| NAT (DNAT/SNAT) | `nft list table ip six_nat` |
| stateful 연결 | `conntrack -L` |
| 룰별 카운터 | `nft -a list chain inet six_filter forward` (packets/bytes) |
| 영구화 | `/etc/nftables.conf` (재부팅 후 유지) |

> 우리가 만지는 것은 **`inet six_filter` / `ip six_nat`** 두 테이블뿐이다(이 둘은 nftables 표준
> 명칭이 아니라 **el34 가 임의로 붙인 이름** — `six` = 원래 인프라명 6v6 의 흔적이다. 다른 환경에선
> 다른 이름). Docker 가 자동 생성한 `ip nat` 는 건드리지 않는다 — 무심코 바꾸면 컨테이너 망이 깨진다.

---

## 3. 네트워크/존, 그리고 가시성의 한계

el34 의 4 존을 운영자 관점으로 본다.

| 존 | 대역 | 무엇이 있나 | fw 의 시야 |
|----|------|-------------|-----------|
| ext | 10.20.30.0/24 | 공격자(192.168.0.202), fw eth0 | fw 가 직접 본다 |
| pipe | 10.20.31.0/24 | fw eth1 ↔ ips eth0 (좁은 통로) | fw 가 본다(통과 트래픽) |
| dmz | 10.20.32.0/24 | ips eth1, **web/WAF**(10.20.32.80), **SIEM**(.100) | fw **는 dmz 내부 통신은 못 본다** |
| int | 10.20.40.0/24 | 백엔드 앱 (JuiceShop 등 .81~) | fw 가 못 본다 (ips 뒤) |

**가시성의 한계 — 매우 중요**: 외부(ext)에서 들어오는 트래픽은 fw 가 본다. 그러나 일단 안으로 들어간
뒤 **dmz/int 내부 통신**(web→app, 앱·호스트 내부 행위)은 fw 를 거치지 않는다. fw 는 외부 경계를 다루는
**경계 장비** 다. "내부에서 무엇을 보고 무엇을 했는가" 는 fw 가 못 본다 — 그건 **IPS(네트워크 패턴) +
WAF(웹 요청 의미) + 호스트 가시화(osquery·sysmon-for-linux, 호스트 내부 행위)** 의 일이다. 엔드포인트
내부 행위는 **W06 osquery / W07 엔드포인트 IR / W11 sysmon-for-linux** 에서 본격적으로 다룬다.

```mermaid
flowchart LR
  ATK[공격자<br/>192.168.0.202<br/><b>ext</b>]:::ext
  FW[방화벽 fw<br/>eth0:.30.1 / eth1:.31.1<br/>nftables<br/><b>경계 장비</b>]:::fw
  IPS[IPS<br/>eth0:.31.2 / eth1:.32.1]:::ips
  WEB[웹/WAF Apache<br/>10.20.32.80<br/><b>dmz</b>]:::svc
  SIEM[SIEM<br/>10.20.32.100]:::svc
  APP[백엔드 앱<br/>10.20.40.x<br/><b>int</b>]:::int

  ATK -- ext --> FW -- pipe --> IPS -- dmz --> WEB
  WEB --> APP
  FW -. counter/nft 상태 .-> SIEM

  classDef ext fill:#fee,stroke:#c33
  classDef fw fill:#fff5d6,stroke:#c80
  classDef ips fill:#e8e8ff,stroke:#55c
  classDef svc fill:#e8f8e8,stroke:#494
  classDef int fill:#f4e8f8,stroke:#849
```

> 운영자가 머릿속에 늘 그려 둘 그림: **fw 는 경계, ips 는 내부 구역 사이 게이트웨이, web Apache 가
> L7 라우팅+WAF**. fw 가 못 보는 내부 행위는 호스트 가시화 도구(osquery/sysmon-for-linux)가 본다.

---

## 4. 디렉토리·설정·로그 (운영자가 알아야 할 위치)

| 항목 | 위치 | 운영자가 만지는가 |
|------|------|------------------|
| 명령 | `/usr/sbin/nft` | 운영의 핵심. `nft list ruleset` / `nft add\|insert rule` 에 익숙해질 것 |
| 설정파일(영구) | `/etc/nftables.conf` | 룰을 영구화할 때 (재부팅 후에도 유지) |
| 연결추적 | `/usr/sbin/conntrack` | `conntrack -L` 로 살아있는 연결 보기 |
| nft native log | 커널 ring buffer (컨테이너에선 파일 미보존) | 그래서 **카운터** 가 운영자의 주된 증거 |

> **두 가지 룰의 집** — 메모리에 올라간 룰(즉시 적용, 재부팅 시 사라짐) vs `/etc/nftables.conf` (영구).
> `nft add/insert` 는 즉시 적용. 운영에선 검증 후 설정파일에도 반영해 재부팅 안전을 확보한다.

---

## 5. 룰 작성 — nft 명령

운영자의 시간은 룰 작성·점검에 가장 많이 쓴다.

### 5.1 체인 3개와 평가 순서

| 체인 | 트래픽 | 룰의 위치를 어떻게 정할까 |
|------|--------|--------------------------|
| `input` | 방화벽 **자신에게** 오는 | 관리 포트(22, 9100) 허용, 외부 직접 접근 차단 |
| `forward` | 방화벽을 **통과해** 내부로 | 차단 룰의 본거지 (대부분의 보안 정책) |
| `output` | 방화벽이 **나가는** | C2 egress 차단 등 (적게 쓰지만 중요) |

룰은 **위에서 아래로** 평가되고 **accept/drop 을 만나면 끝**난다. 그래서 "차단은 top, 일반 허용은
bottom" 이 보통이다. nft 의 `insert`(top) vs `add`(bottom) 선택이 이 차이를 만든다.

### 5.2 룰 한 줄을 읽는다

예: 체인 `forward`, 출발지 `192.168.0.202`, 동작 `drop`, 위치 `top` → nft 명령:

```
sudo nft insert rule inet six_filter forward ip saddr 192.168.0.202 counter drop
```

각 부분의 의미를 운영자 언어로:

| 토큰 | 의미 |
|------|----|
| `insert` | 체인 **맨 위** 에 넣는다 (위치 top). 가장 먼저 평가됨 |
| `inet six_filter forward` | 우리 정책 테이블의 forward 체인에 |
| `ip saddr 192.168.0.202` | **출발지 IP** 가 이것이면 |
| `counter` | 매칭한 packets/bytes 를 센다 (운영자의 증거) |
| `drop` | 조용히 버린다 (응답 없음) |

> 운영자가 외울 단어 4개: `add/insert rule`, `ip saddr/daddr`, `counter`, `drop/accept/reject`.

### 5.3 더 운영자스러운 룰 패턴 4가지

#### (a) Rate limit — SSH brute force 완화 (가용성 보존)

```
sudo nft insert rule inet six_filter input tcp dport 22 ct state new \
    limit rate over 10/minute counter drop
```

분당 10회를 **초과** 하는 신규 연결만 drop. 정상 사용자는 통과. 22번을 통째로 막는 것보다 백배 낫다.

#### (b) 그룹(객체, Alias) — 악성 IP 묶음

sudo nft **set**(객체)으로 IP 그룹 `blocklist` 생성 → 룰에서 `@blocklist` 참조:

```
sudo nft add set inet six_filter blocklist { type ipv4_addr ; }
sudo nft add element inet six_filter blocklist { 192.168.0.202, 10.20.30.250 }
sudo nft insert rule inet six_filter forward ip saddr @blocklist counter drop
```

**왜 좋은가** — CTI 에서 새 악성 IP 가 오면 **룰은 그대로 두고** 그룹에만 추가하면 모든 참조 룰에 즉시
반영된다. 운영 일관성 + 빠른 반응. 룰 100개를 만들지 말고 **그룹 1개를 살찌워라**.

#### (c) stateful — 응답 자동 통과

input/forward 체인 맨 위엔 항상 있는 룰:

```
ct state established,related accept
```

한 번 허용된 연결의 **응답 패킷** 은 자동 통과. 운영자는 룰 작성 시 "신규(new) 연결" 만 신경 쓰면 된다.
새 룰의 매치에 `ct state new` 를 추가하면 더 정확하다.

#### (d) 로그 + 차단 + 카운터 — 침해 증거 보존

```
sudo nft insert rule inet six_filter input ip saddr 192.168.0.202 \
    counter log prefix "EDU-BLOCK: " drop
```

`log prefix` 는 커널 ring buffer 로 가서 컨테이너 환경에선 파일에 안 남지만, **`counter`** 가
운영자의 가장 확실한 증거다. 적용 후 공격을 재현하면 `nft -a list chain ...` 에서 packets 값이 올라간다.

---

## 6. NAT — DNAT / SNAT / MASQUERADE

NAT 은 **주소를 바꿔치기** 한다. 운영자가 자주 하는 세 종류.

### 6.1 DNAT — 내부 서비스를 외부에 공개

예: DNAT, iif `eth0`, tcp dport `8088`, 대상 `10.20.32.80:80` → nft 명령:

```
sudo nft add rule ip six_nat prerouting iifname "eth0" tcp dport 8088 \
    counter dnat to 10.20.32.80:80
```

외부의 `방화벽:8088` → 내부 웹서버(10.20.32.80:80). **prerouting**(라우팅 결정 전)에서 일어난다.
**내부 IP 는 노출되지 않는다.**

### 6.2 SNAT / MASQUERADE — 출발지 위장

내부 호스트가 외부로 나갈 때 출발지 IP 를 방화벽 IP 로 위장(NAT). **postrouting**(라우팅 후)에서.

```
sudo nft add rule ip six_nat postrouting oifname "eth1" ip saddr 10.20.40.0/24 \
    counter snat to 10.20.31.1
```

또는 `masquerade`(자동 SNAT, 인터페이스 IP 사용). MASQUERADE 는 인터페이스 IP 가 동적일 때 쓴다.

### 6.3 prerouting vs postrouting (외우는 법)

> "**어디로 갈지 정하기 전에 목적지(D)를 바꾸고, 다 정한 뒤 출발지(S)를 바꾼다.**" — DNAT=prerouting,
> SNAT/MASQUERADE=postrouting.

### 6.4 web Apache(L7) ↔ 방화벽 NAT(L4) — 역할 분담

el34 의 L7 라우팅은 **web 컨테이너의 Apache**(vhost), L4 주소변환은 **fw 의
sudo nft NAT** 가 맡는다 — 다른 호스트, 다른 계층.

| 도구 | 위치 | 계층 | 어떻게 라우팅하나 | 예 |
|------|------|-----|-------------------|-----|
| Apache vhost | web 컨테이너 | L7 (HTTP) | **Host 헤더** | `juice.el34.lab` → int juiceshop |
| nft NAT | fw 컨테이너 | L4 (TCP/IP) | **포트/IP** | tcp 8088 → 10.20.32.80:80 |

**규칙**: fw 가 공인 .161 의 80/443 을 web 으로 보내면 그 뒤 Apache 가 Host 헤더로 vhost 를 고른다.
운영 패턴 — **HTTP 노출은 web vhost 추가**, **비 HTTP / 별도 포트 노출** 은 fw 의 nft DNAT 으로 분담.
새 DNAT 을 만들기 전 충돌 포트가 없는지 `ss -ltn` 으로 확인한다.

### 6.5 NAT 는 방화벽이 아니다 (흔한 오해)

**NAT 이 켜졌다고 그 트래픽이 보안적으로 검사된다는 뜻이 아니다.** NAT 은 주소 변환일 뿐, 콘텐츠
검사를 안 한다. NAT 으로 공개한 8088 도 똑같이 **차단 룰** 의 적용 대상이어야 안전하다. (DNAT 을
켰다면 그 대상 IP/포트에 대한 forward 차단 룰을 함께 검토할 것.)

---

## 7. Stateful — conntrack 표 읽기

**Stateful** 메뉴에서 보는 연결 추적 표.

```
proto  state         src                dst                  flags
tcp    ESTABLISHED   10.20.31.1:40428   10.20.32.120:5601    [ASSURED]
```

- `proto` = TCP/UDP/ICMP
- `state` = TCP 상태(NEW/SYN_SENT/ESTABLISHED/TIME_WAIT 등)
- `[ASSURED]` = 양방향 패킷이 오간, "확실한" 연결 (커널이 잘 안 지운다)
- `[UNREPLIED]` = 한쪽 방향만 — SYN flood / NAT 실패 / 응답 누락의 신호

### 7.1 conntrack 으로 진단할 수 있는 NAT 끊김 4 패턴

| 증상 | conntrack 의 신호 | 원인 |
|------|------------------|------|
| 연결은 되는데 응답이 안 옴 | `[UNREPLIED]` 다수 | 응답 경로가 다른 방향(asymmetric routing) — NAT 비대칭 |
| 잠시 후 끊긴다 | `TIME_WAIT` 폭증, 새 연결이 같은 5-tuple 재사용 못함 | 짧은 timeout, 포트 고갈 |
| 일부 클라이언트만 안 됨 | 그 클라이언트만 conntrack 없음 | 룰이 그 출발지 drop |
| 갑자기 모든 새 연결 안 됨 | conntrack table FULL | 용량 초과(`nf_conntrack_max`) |

운영자는 평소에 `Stateful` 메뉴의 **count + 분포** 만 보면 이상을 빠르게 잡는다.

### 7.2 conntrack table 용량 — el34 에선 신경 안 써도 되지만

운영망에서는 `nf_conntrack_max` 초과 시 새 연결이 안 만들어진다. **트래픽 폭증 사고의 단골 원인**.
운영 환경에선 모니터링 + sysctl 튜닝이 필요하지만, 본 강의 el34 규모에선 발생하지 않는다.

---

## 8. 카운터 · 이벤트 로그 · SIEM 연동

### 8.1 카운터 — 운영자의 가장 정직한 증거

**로그·활동** 메뉴에서 룰마다 packets/bytes 가 보인다. 차단 룰의 packets 가 0 → 4 → ... 로 늘면
**그 룰이 실제로 트래픽을 막고 있다** 는 100% 증거다. 어떤 보고서보다 강력하다. **카운터 리셋** 으로
주기적 측정도 가능.

### 8.2 nft 룰셋 상태 = 현재 정책의 진실

el34 fw 는 별도 콘솔/이벤트 로그가 없다. **현재 적용된 정책의 진실은 `nft list ruleset` 그 자체** 다.
침해 후 "방화벽 정책이 어떻게 되어 있나"는 이 출력으로 확인한다. 변경 이력을 남기려면 룰셋을 주기적으로
스냅샷(`nft list ruleset` → `/etc/nftables.conf` + git/SIEM 전송)하는 운영 습관이 필요하다.

### 8.3 SIEM(Wazuh) 연동 — el34 현황

el34 의 Wazuh agent 는 현재 **ips / web** 컨테이너에 있다 — SIEM 한 화면에서 **IPS alert + WAF 차단**
을 함께 본다. fw 의 nft 변경/카운터까지 SIEM 으로 보내려면 **fw 에 Wazuh agent 를 추가**해 nft 상태·로그를
ingest 해야 하며, 이 구성은 **W09(Wazuh)** 에서 다룬다. 그 전까지 fw 의 주된 증거는 **카운터** 다.

> SIEM 이 갖춰지면 운영자의 일상은 개별 도구보다 **Wazuh 대시보드** 가 중심이 된다. fw 는 "정책 변경"의
> 도구, SIEM 은 "관제"의 도구.

---

## 9. 침해대응 시나리오 7건 (R/B/P)

침해대응 시나리오는 모두 **Red(공격 재현) → Blue(nft 룰 작성·적용) → Purple(카운터로 검증·증거 보존)**
패턴을 따른다. 본 강의에선 핵심 7건을 fw 컨테이너에서 직접 `nft` 로 풀어 본다.

> 📌 `fw-sNN` 은 표준 용어가 아니라 **이 교재가 붙인 시나리오 식별자**다. 원래 s01~s11 세트에서 대표
> 사례만 추렸기에 번호가 비연속(s05/s09/s10 등 생략)이며, lab·과제는 그중 핵심 5건(s01/s03/s07/s08/s11)을 실습한다.

### 9.1 fw-s01 — 악성 IP 즉시 차단 (수동 대응)

- Red: `sudo hping3 -S -p 80 --flood -c 50 192.168.0.161` (SYN flood — 진짜 flood 도구)
- Blue: forward 체인 top 에 `ip saddr 192.168.0.202 drop`.
- Purple: 카운터 packets ≥ 50 (`nft -a list chain inet six_filter forward`) ✔.
- 교훈: 단일 IP 차단은 가장 빠른 1차 대응. 단 출발지가 분산되면 무력해진다 → fw-s11 (객체)로 진화.

### 9.2 fw-s02 — 닫혀야 할 관리 포트 보호

- Red: `nc -vz 10.20.30.1 9999`.
- Blue: input 체인에 `tcp dport 9999 drop`.
- Purple: nc 응답 timeout + counter 증가.
- 교훈: 최소권한. "쓰지 않는 포트는 닫는다"가 보안의 기본.

### 9.3 fw-s03 — SSH brute force 완화

- Red: `for i in $(seq 1 60); do nc -w1 10.20.30.1 22 </dev/null; done`
- Blue: `tcp dport 22 ct state new limit rate over 10/minute drop`.
- Purple: 정상 SSH 는 통과, 폭주만 drop (carrier-grade 패턴).
- 교훈: 가용성 보존형 방어 — 22 를 통째로 막지 않는다.

### 9.4 fw-s04 — ICMP flood 제한

- Red: `ping -f -c 500 10.20.30.1` (flood ping).
- Blue: `ip protocol icmp limit rate over 5/second drop`.
- Purple: 정상 ping 통과, flood drop.
- 교훈: 진단(ping) 가용성을 해치지 않는 방어.

### 9.5 fw-s07 — 화이트리스트 (관리망만 허용)

- Red: 외부에서 `nc -vz 10.20.30.1 9100`.
- Blue: input top 에 `ip saddr 10.20.31.0/24 tcp dport 9100 accept`, 그 아래 `tcp dport 9100 drop`.
- Purple: 관리망(pipe)에서만 9100 도달, 외부는 막힘.
- 교훈: **허용 먼저, 거부 나중** — 순서가 바뀌면 관리망도 막힌다. 화이트리스트 설계의 정석.

### 9.6 fw-s08 — DNAT 으로 안전한 공개

- Red: 공격자가 `방화벽:8088` 접속 시도 (적용 전엔 closed).
- Blue: NAT 메뉴에서 DNAT 8088 → 10.20.32.80:80.
- Purple: 접속 OK (200), 내부 IP 미노출.
- 교훈: NAT 으로 공개 = **내부 주소 은닉** + 외부 노출 표면 제어. 단 NAT 만으로는 보안 X — 차단 정책과 함께.

### 9.7 fw-s11 — 객체(그룹)로 다중 차단 + CTI 운영

- Red: CTI 에서 악성 IP 5개 식별, 한 번에 차단 필요.
- Blue: `nft add set ... blocklist` 생성 → IP 5개 `add element` → forward 룰 `@blocklist drop` 1줄.
- Purple: 5 IP 모두 차단, 새 악성 IP 발견 시 그룹에만 추가 → 룰 무수정 즉시 적용.
- 교훈: **운영 일관성 + 빠른 반응**. 룰의 수를 늘리지 말고 **객체** 로 데이터를 늘려라.

### 추가 (egress) — C2 콜백 차단 (fw-s06)

내부 호스트가 알려진 C2 IP 로 나가는 콜백을 차단:
- Blue: output 체인 top 에 `ip daddr <C2 IP> drop`.
- 교훈: **egress filtering** — 침해 후 데이터 유출/명령 수신을 끊는 마지막 보루. 흔히 잊는다.

---

## 10. 운영 트러블슈팅 — 자주 보는 4 가지

| 증상 | 확인 | 처치 |
|------|------|------|
| "차단했는데 통과한다" | 카운터 = 0 → 룰이 안 평가됨 (위에 accept 가 먼저) | **위치 top** 또는 위 accept 제거/수정 |
| "정상 사용자가 막혔다" | 카운터 = 정상 IP, 응답코드 timeout | 룰의 매칭 범위 좁히기 (출발지 CIDR 정확히) |
| "NAT 가 안 먹는다" | conntrack `[UNREPLIED]` | 응답 경로 / DNAT 대상 도달성 / 충돌 포트 |
| "방화벽이 갑자기 모든 새 연결 거부" | dmesg `nf_conntrack: table full` | `nf_conntrack_max` 증가 (운영에서) |

---

## 11. 핵심 정리 (8 줄)

1. 운영자는 **nft 명령 읽기·쓰기** 로 충분하다. 엔지니어가 아니다.
2. **체인은 input/forward/output 3개**, 평가는 **위에서 아래**, accept/drop 에서 끝난다.
3. 자주 쓰는 패턴: **stateful(established,related accept) + rate limit + 객체(@group)**.
4. **DNAT=prerouting**, **SNAT/MASQUERADE=postrouting**. web Apache(L7) 와 fw nft NAT(L4) 의 역할 분담.
5. **카운터** 가 차단 효과의 정직한 증거. nft 룰셋 스냅샷이 정책 감사 자료.
6. **SIEM(Wazuh) 연동** 으로 방화벽이 단독이 아니라 인프라 전체의 일부가 된다.
7. 침해대응은 **R/B/P** 1 cycle: 공격 재현 → 룰 → 카운터 증거.
8. 방화벽은 **경계** 만 본다 — dmz/int 내부 행위는 **W06 osquery / W11 sysmon-for-linux** 가 본다.

---

## 12. 과제

1. 시나리오 fw-s01 / s03 / s07 / s08 / s11 다섯 건을 `nft` 로 적용하고, 적용 후 카운터 증가(`nft -a list chain ...`) 출력을 제출하라.
2. fw-s07 (화이트리스트) 에서 "허용을 아래에 둘 때" 어떻게 망가지는지 시연하고 1문단 설명하라.
3. fw-s08 DNAT 룰을 만들고 적용 전·후의 `ss -ltn` / 공격자 `nc` 요청 결과를 비교하라.
4. 룰을 한 건 적용한 뒤 `nft list ruleset` 으로 현재 정책을 스냅샷하고, `/etc/nftables.conf` 로 영구화하는 절차를 기술하라.
5. (생각) 방화벽이 **못 보는 트래픽 3가지** 를 우리 el34 구조에서 구체적으로 들고, 각각을 누가 봐 주는지 쓰라.

---

## 13. 다음 주차 (W03) 예고 — Suricata IDS

방화벽은 L3/L4 헤더(IP·포트)만 본다. 그 안에 실린 **페이로드(공격 시그니처)** 는 못 본다. 다음 주차는
경계 바로 뒤의 **IPS(`el34-ips`, Suricata)** 로 들어가, 통과하는 트래픽의 페이로드를 시그니처로 검사해
스캔·익스플로잇·악성 통신을 탐지한다. 방화벽이 포트로 못 막은 것을, IDS 가 내용으로 잡는다.
(엔드포인트 내부 행위는 W06 osquery / W07 엔드포인트 IR / W11 sysmon-for-linux 에서 다룬다.)
