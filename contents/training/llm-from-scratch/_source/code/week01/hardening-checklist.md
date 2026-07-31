# hardening-checklist.md — 하드닝 종합 점검 (V1-2 산출물)

> V1-2의 제약 준수: **FAIL 항목을 고치지 않았다.** 원인 분석만 표 아래에 적었다.

| 항목 | 기대 상태 | 증거 명령 | 실제 출력 | 판정 |
|---|---|---|---|---|
| 1. 패스워드 로그인 비활성 | `passwordauthentication no` | `sudo sshd -T \| grep -i passwordauthentication` | `passwordauthentication yes` | **FAIL** |
| 2. 열린 TCP 포트 (22 외 외부 노출) | 22만 | `sudo ss -tlnp` | `0.0.0.0:22`, `[::]:22`, **`*:11434`(ollama)** — 그 외는 127.0.0.1 바인딩 | **FAIL** |
| 3. 방화벽 상태 | `Status: active` + 22/tcp ALLOW | `sudo ufw status verbose` | `상태: 비활성` | **FAIL** |
| 4. fail2ban 동작 | sshd jail 활성, `Currently banned: 0` | `sudo fail2ban-client status sshd` | `Currently banned: 0` / `Total banned: 0` / `Journal matches: _SYSTEMD_UNIT=sshd.service + _COMM=sshd` | **PASS** |
| 5. 자동 보안 업데이트 | 설정 활성 + 타이머 동작 | `cat /etc/apt/apt.conf.d/20auto-upgrades`; `systemctl list-timers apt-daily-upgrade.timer` | `APT::Periodic::Update-Package-Lists "1";` / `APT::Periodic::Unattended-Upgrade "1";` / 타이머 `NEXT Fri 2026-07-31 06:30:35 KST` | **PASS** |

## FAIL 원인 분석 (수정하지 않음)

**항목 1 — 패스워드 로그인 비활성 (FAIL):**
검증 과정의 **의도된 미적용**이다. 이 호스트는 원격 SSH 세션으로 접속 중이며(journald 기록:
`Accepted password for mrgrit from 211.170.162.139`), 패스워드 인증을 끄는 순간 키 인증이
정상 동작하지 않으면 **즉시 잠금(lockout)** 된다. 교재 P1-2가 "내 확인 전에는 절대 설정을
변경하지 말 것" 게이트를 둔 이유가 정확히 이것이다. 전제 조건은 모두 충족되어 있다:

- `~/.ssh/authorized_keys` 존재 (265 바이트)
- `sudo sshd -T | grep pubkeyauthentication` → `pubkeyauthentication yes`
- `sudo sshd -t` → 종료코드 **0** (문법 검사 도구 정상 동작)
- `/etc/ssh/sshd_config.d/` **비어 있음** → cloud-init 계열 drop-in 오버라이드 없음
  (클라우드 이미지에서 흔한 `50-cloud-init.conf: PasswordAuthentication yes` 함정이 여기엔 없다)

**항목 2 — 22 외 외부 노출 포트 (FAIL):**
`*:11434` 에서 **Ollama가 전 인터페이스에 바인딩**되어 있다. 13주차 LLM-as-judge가 이 포트를
쓰므로 기능상 필요하지만, 교내망에 그대로 노출되면 **누구나 인증 없이 로컬 LLM을 호출**할 수 있다.
조치 방향(지시 대기): `OLLAMA_HOST=127.0.0.1:11434` 로 바인딩을 좁히고, 컨테이너에서는
`host-gateway` 로 접근한다. 나머지 리스닝 포트(cupsd 631, dashboard 11000, systemd-resolved 53)는
모두 `127.0.0.1` 바인딩이므로 외부 노출이 아니다.

**항목 3 — 방화벽 비활성 (FAIL):**
의도된 미적용. 이유 두 가지.
1. `sudo ufw enable` 은 `명령은 존재하는 ssh 연결에 피해를 줄 수 있습니다. 진행하시겠습니까(y|n)?`
   로 **대화형 확인을 요구**한다. 원격 세션에서의 위험이 실재한다는 증거다.
2. 이 호스트는 Docker를 쓴다. `iptables -L DOCKER-USER` 체인이 존재하며(1 reference),
   **Docker가 게시한 포트는 UFW 규칙을 우회**한다. UFW를 켜도 컨테이너 게시 포트는
   막히지 않으므로, "UFW active" 만으로 안전하다고 결론내면 오판이다.

절차 자체는 `ufw --dry-run allow 22/tcp` 로 검증했다 — `ufw-user-input` 체인에 규칙이 정상
생성되는 것을 확인했다.

## 판정 요약

2 PASS / 3 FAIL. FAIL 3건 중 2건(항목 1·3)은 **잠금 위험 때문에 의도적으로 적용하지 않은 것**이고,
1건(항목 2)은 **실제로 발견된 노출**이다.
