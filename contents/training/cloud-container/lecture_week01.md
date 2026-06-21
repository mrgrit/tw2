# 클라우드·컨테이너 W01 — 컨테이너 보안 개론

> 클라우드·컨테이너 트랙 1주차. 인프라: el34 (Docker 41 컨테이너). 플랫폼: tw2. 표준: CIS Docker, NIST SP 800-190.

---

## 1. 이번 주의 통찰 — 가볍지만 공유한다

컨테이너는 VM보다 가볍지만 **호스트 커널을 공유**한다. 격리가 VM보다 얕아, 잘못된 설정(특권/루트/과한
권한) 하나가 호스트 전체로 번질 수 있다(container escape). el34는 41개 컨테이너로 구성된 실제 환경이다.

```
 VM:       하드웨어 가상화, 게스트 OS 별도 (강한 격리, 무겁다)
 컨테이너: 커널 공유, 프로세스 격리 (가볍다, 격리 얕다)
 → 컨테이너 보안 = 얕은 격리를 설정으로 보강
```

---

## 2. 컨테이너 식별

```bash
docker ps --format '{{.Names}}' | head; docker ps -q | wc -l
```
- el34: 41개 컨테이너(web/ips/siem/fw/attacker/bastion 등). 무엇이 도는지 파악이 보안의 출발점.

---

## 3. 컨테이너 보안 4계층 (NIST 800-190)

```
 ① 이미지(Image):       베이스 이미지·레이어·취약점 (W02·W03)
 ② 런타임(Runtime):     특권/capabilities/user/격리 (W04·W05)
 ③ 레지스트리(Registry): 이미지 출처·서명·무결성 (W11)
 ④ 오케스트레이션:       compose/k8s 설정 (W12)
```

---

## 4. 공유 커널 위험

```
 특권 컨테이너(--privileged): 호스트 장치/커널 접근 → escape 시 호스트 장악
 root 실행: 컨테이너 내 root = 탈출 시 호스트 권한 위협
 과한 capability: CAP_SYS_ADMIN 등은 사실상 특권
```

---

## 5. 기본 점검 (docker inspect)

```bash
docker inspect el34-web --format 'Priv={{.HostConfig.Privileged}} User={{.Config.User}}'
```
- el34-web: `Privileged=false`(양호) 이나 **`User`가 비어 컨테이너가 root(uid 0)로 실행** → CIS Docker
  4.1 위반(비-root 사용자 권고). 탈출 시 위험 증가 = 갭.

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: docker 가용
2. **컨테이너 식별**: docker ps
3. **컨테이너 vs VM**: 격리 차이
4. **보안 4계층**: 이미지~오케스트레이션
5. **공유 커널 위험**: escape/특권
6. **기본 점검**: Priv/User(root 갭)
7. **방어 개요**: 최소권한
8. **컨테이너 개론 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker` CLI 로. 신규 설치 없음(이번 주).

---

## 7. 다음 주차 (W02) 예고 — 이미지 보안

W01은 개론이었다. W02는 이미지 보안(베이스 이미지·레이어·최소화)을 다룬다.
