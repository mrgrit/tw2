# 트레이닝 강의·실습 골드 스탠다드 기준서 (작성 필독)

> 목적: 모든 트랙·주차의 강의(lecture_weekNN.md)와 실습(lab_weekNN.yaml)을 **학생이 보는 교과서**
> 수준으로 일관되게 작성·재작성한다. 기준 레퍼런스 = `contents/training/secuops/lecture_week01.md`.

## 0. 절대 원칙
- **학생용 교과서다.** 학생이 오해하거나 잘못 이해할 여지가 없어야 한다. 처음 등장하는 용어·개념·도구·
  명령은 **반드시 그 자리에서 설명**한다("갑자기 튀어나온 것" 금지).
- **뒤로 갈수록 부실해지지 말 것.** 모든 주차가 동일한 깊이를 유지한다.
- **검증된 실습 명령은 절대 변경 금지.** lab.yaml 의 `answer:`, `verify.expect`, `verify.field`,
  실행 명령(docker exec ...), 마커 문자열, `target_vm`, `points`, `order` 는 el34 라이브로 검증된
  값이므로 한 글자도 바꾸지 않는다. 오직 `instruction:`(학생이 읽는 설명)과 `answer_detail:`,
  `description:`, `objectives:` 의 **설명 품질만 보강**한다.

## 1. 다이어그램 = mermaid 그래픽 (ASCII 금지)
- 모든 개념도/흐름도는 ```mermaid 코드블록으로 그린다. ASCII 박스아트(``` 안의 +---+ │ → 등) **금지**.
- **세로 방향**으로 그린다: `graph TD` 또는 `graph TB`. 옆으로 긴 `graph LR` 은 가독성이 낮으므로
  쓰지 않는다(불가피한 짧은 2~3노드 흐름만 예외).
- 노드 라벨은 `<br/>` 로 여러 줄. 핵심 노드는 색을 준다:
  - 공격/위험: `style X fill:#f85149,color:#fff` (빨강)
  - 방어/정상: `style X fill:#3fb950,color:#fff` (초록) 또는 `#1f6feb`(파랑)
  - 경고/데이터: `style X fill:#d29922,color:#fff` (주황)
  - 보조/특수: `style X fill:#bc8cff,color:#fff` (보라)
- 예시(세로 흐름):
  ```mermaid
  graph TD
      A["1. 정찰<br/>nmap 포트 스캔"] --> B["2. 침투<br/>SQLi 인증 우회"]
      B --> C["3. 권한상승<br/>sudo 오설정"]
      C --> D["4. 지속성<br/>cron 백도어"]
      style A fill:#d29922,color:#fff
      style D fill:#f85149,color:#fff
  ```

## 2. 강의(lecture_weekNN.md) 필수 구조
1. `# <트랙> WNN — <주제>` 제목
2. `> 본 주차 한 줄 요약` (인용블록): 이 주에 무엇을·왜 배우는지 2~3문장.
3. `## 학습 목표`: "학생은 ~을 본인 손으로 할 수 있다" 번호 목록 4~6개.
4. `## 0. 용어 해설`(이번 주 처음 나오는 용어가 있으면): 표(용어|영문|뜻|비유) + 헷갈리기 쉬운 핵심
   용어는 **일상 비유**로 풀어 설명(secuops W01 §0.5 스타일).
5. 본문 섹션들(`## 1`, `## 2` ...): 각 개념마다
   - **한 줄 정의** → **왜 중요한가** → **el34 에서 어떻게** → **한계/주의**.
   - 처음 나오는 도구/명령/표준(CVE, PCI-DSS 조항, MITRE ATT&CK, NIST 단계 등)은 그 자리에서 풀이.
   - 개념도는 mermaid 세로 그래픽.
   - 실제 명령·출력 예시를 보여주되, 무엇을 보는지 해석을 단다.
6. `## 실습 안내`: 각 실습(=lab step 대응)마다 **4축 설명**:
   - 이 실습을 왜 하는가? / 무엇을 알 수 있는가? / 결과 해석(정상 vs 비정상) / 실전 활용.
7. `## 다음 주차 예고`: 이번→다음 연결.
- 분량보다 **완결성**이 기준: 학생이 이 문서만으로 막힘없이 이해 가능해야 한다. 터스한 한 줄 bullet
  나열 금지. 각 항목을 문장으로 설명한다.

## 3. 실습(lab) instruction 품질
- 각 step 의 `instruction:` 은 (a) 🎯 목표 (b) 개념 한 줄(왜 이걸 하나) (c) 💻 실행 명령
  (d) ✅ 합격 기준 (e) 처음 나오는 도구/옵션 풀이 를 포함한다. 명령만 던지지 말 것.
- `answer_detail:` 은 채점자·학생이 보는 정답 해설 — 무엇을·왜·어떻게 판정하는지 한 문장 이상.

## 4. el34 사실(절대 정확히 사용 — 지어내지 말 것)
- 호스트 `ssh ccc@192.168.0.151`(pw 1) → `docker exec el34-<X>`. 컨테이너 41개.
- 4-tier: ext 10.20.30 / pipe .31 / dmz .32 / int .40. fw ext.1/pipe.1, ips pipe.2/dmz.1,
  web dmz.80/int.80, siem dmz.100. attacker 내부 10.20.30.202 → 10.20.30.1(fw gw)/vhost.
- 외부공격자 VM 192.168.0.202 → 공인 .161(출처 IP 보존). vhost `*.el34.lab`(juice/dvwa/neobank/
  govportal/mediforum/admin/ai/siem/portal/bastion/landing).
- dvwa=ModSec 차단(403), juice=DetectionOnly(200). ModSec 룰군 913/930/931/932/933/941/942/949.
  로그: ips `/var/log/suricata/eve.json`, web `/var/log/apache2/modsec_audit.log`+per-vhost,
  siem(Wazuh4.10) `/var/ossec/logs/alerts/alerts.json`(agent ips003/web004). SCA/FIM on web.
- 도구: attacker 에 nmap/nikto/ffuf/sqlmap/hydra/curl/scapy/nuclei(+템플릿)/dalfox/httpx,
  호스트에 trivy/sysmon. gobuster 깨짐→ffuf.
- 트랙별 표준: secuops/soc(방어·관제), attack(공격, PTES), web-vuln(WSTG), compliance(ISMS-P/
  ISO27001/PCI-DSS/CIS/NIST), cloud-container(CIS Docker/NIST 800-190).

## 5. 작성 후 자가 점검
- [ ] ASCII 박스아트 0개, 모든 그림 mermaid 세로.
- [ ] 처음 나오는 모든 용어·도구·표준이 설명되어 있다.
- [ ] lab 의 검증된 명령/마커/expect 를 건드리지 않았다.
- [ ] 한 줄 bullet 나열이 아니라 문장으로 설명되어 있다.
- [ ] el34 사실(IP·컨테이너·경로·마커)이 정확하다.
