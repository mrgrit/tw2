# 공격기법 W11 — user에서 root로: SUID·sudo 오설정·cron으로 권한 상승 vs 탐지·하드닝

> 공격기법 트랙 11주차. 선행: W08(셸 획득). 인프라: el34 (el34-web, ccc 비-root 사용자). 플랫폼: tw2.

---

## 1. 이번 주의 통찰 — 발판에서 장악으로

셸을 얻어도 보통 **저권한 사용자**(www-data/일반 계정)다. 진짜 장악은 **root 권한 상승(privilege
escalation)**. 리눅스 privesc의 단골 경로 — **SUID 오설정, sudo 오설정, cron, 쓰기 가능 파일**.

```
 저권한 셸 → [열거(enumeration)] → 오설정 발견 → root
   SUID 바이너리 / sudo 규칙 / cron 작업 / world-writable / 약한 권한
```

---

## 2. ① 열거 — privesc의 90%

privesc는 **열거**가 핵심. 무엇이 잘못 설정됐나 샅샅이:
```bash
# SUID 바이너리 (root 권한으로 실행되는 파일)
docker exec -u ccc el34-web sh -c 'find / -perm -4000 -type f 2>/dev/null'
# sudo 권한 (무엇을 root로 실행 가능?)
docker exec -u ccc el34-web sh -c 'sudo -ln 2>/dev/null'
# 내 그룹/컨텍스트
docker exec -u ccc el34-web id
```

---

## 3. ② SUID 오설정 — GTFObins

SUID 비트가 붙은 바이너리는 **소유자(root) 권한으로 실행**된다. 위험한 바이너리(find/vim/bash/cp 등)에
SUID가 붙으면 root 셸로 직행([GTFObins](https://gtfobins.github.io) 참조).
```
 find SUID:   find . -exec /bin/sh -p \; -quit   → root
 vim SUID:    vim -c ':!/bin/sh'                  → root
 cp SUID:     /etc/passwd 덮어쓰기                → root
```
- 정상 SUID(passwd/su/mount)는 의도된 것. **비정상 SUID**(셸/에디터/스크립트)가 위험.

---

## 4. ③ sudo·cron 오설정

- **sudo**: `sudo -l`에 NOPASSWD나 위험 명령(`ALL`, vi, less, awk)이 있으면 GTFObins로 escape.
- **cron**: root cron이 **world-writable 스크립트**를 실행하면, 그 스크립트를 수정해 root 코드 실행.
- **쓰기 가능 민감 파일**: /etc/passwd, /etc/shadow, /etc/sudoers 쓰기 가능 시 직접 계정/권한 추가.

---

## 5. 탐지 + 하드닝 (방어)

- **탐지**: osquery `suid_bin`(비정상 SUID), FIM(/etc/sudoers, /etc/passwd 변경), 비정상 root 프로세스.
- **하드닝**: 불필요한 SUID 제거(`chmod -s`), sudo 최소권한(NOPASSWD 감사), cron 스크립트 권한 강화,
  민감 파일 권한 점검. **최소 권한 원칙**.

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: ccc 비-root 컨텍스트
2. **SUID 열거**: find -perm -4000
3. **sudo 점검**: 권한/그룹
4. **cron·쓰기가능 점검**: 오설정 후보
5. **권한 상승 경로**: GTFObins 매핑
6. **탐지**: osquery suid_bin / FIM
7. **하드닝**: SUID 제거·sudo 최소화
8. **privesc 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker exec [-u ccc] el34-web` 로. 열거 중심(읽기전용),
> 실제 root 상승/하드닝은 개념·점검까지(공유 인프라 보존). 인가된 실습만.

---

## 7. 다음 주차 (W12) 예고 — persistence + 안티포렌식

W11은 root 상승이었다. W12는 장악 유지 — 다중 persistence(백도어/cron/키)와 안티포렌식(로그 삭제)을
심고, 방어자가 전수 헌팅·로그 무결성으로 잡는 법을 다룬다.
