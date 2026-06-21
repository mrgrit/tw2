# 클라우드·컨테이너 W02 — 이미지 보안

> 클라우드·컨테이너 트랙 2주차. 선행: W01. 인프라: el34. 플랫폼: tw2. 표준: CIS Docker 4, NIST 800-190.

---

## 1. 이번 주의 통찰 — 이미지가 곧 공격 표면

컨테이너는 이미지에서 태어난다. **이미지에 든 모든 패키지·도구·비밀이 그대로 런타임의 공격 표면**이
된다. 큰 베이스 이미지(full OS)는 불필요한 도구(shell·패키지매니저·컴파일러)를 품어 침해 후 공격자의
무기고가 된다.

```
 이미지 = 레이어(layer)의 누적. 각 RUN/COPY가 한 레이어
 큰 이미지(full OS) → 많은 패키지 → 많은 CVE + 침해 후 악용 도구
 작은 이미지(distroless/alpine) → 최소 표면
```

---

## 2. 이미지 레이어/히스토리

```bash
docker history el34-web --format '{{.Size}} {{.CreatedBy}}' | head
```
- 레이어별 명령/크기 확인. COPY로 들어간 비밀이나 불필요 파일이 레이어에 영구 잔존(삭제해도 이전
  레이어에 남음)할 수 있다.

---

## 3. 베이스 이미지

```bash
docker exec el34-web sh -c 'cat /etc/os-release | head -1'
```
- el34-web: **Ubuntu 22.04**(full OS) 베이스. 기능은 풍부하나 공격 표면이 크다. 보안 권고는 최소
  베이스(distroless/alpine/slim) — 단 디버깅·호환성과 트레이드오프.

---

## 4. 이미지 크기·노출 포트

```bash
docker images --format '{{.Repository}} {{.Size}}'
docker inspect el34-web --format '{{.Config.ExposedPorts}}'
```
- el34 이미지: web 560MB, attacker 4GB 등 — 크기가 곧 표면. el34-web은 **EXPOSE 22(SSH)** 포함 →
  이미지에 SSH 서버 = 추가 표면(필요성 검토 대상).

---

## 5. 이미지 최소화

```
 멀티스테이지 빌드: 빌드 도구는 빌드 단계에만, 최종 이미지엔 산출물만
 최소 베이스: distroless/alpine/slim
 .dockerignore: 비밀·불필요 파일 빌드 컨텍스트 제외
 비밀 미포함: 빌드 시 비밀 주입(레이어에 굽지 않기)
```

---

## 6. 실습(lab) 형식 — 8 미션

1. **점검**: 대상
2. **레이어/히스토리**: docker history
3. **베이스 이미지**: Ubuntu(full)
4. **이미지 크기**: 표면
5. **노출 포트**: EXPOSE 22
6. **최소화**: 멀티스테이지/distroless
7. **방어**: 이미지 위생
8. **이미지 보안 보고서**

> 명령은 el34 호스트(`ssh ccc@192.168.0.151`)에서 `docker` CLI 로. 신규 설치 없음.

---

## 7. 다음 주차 (W03) 예고 — 이미지 취약점 스캔(Trivy)

W02는 이미지 보안이었다. W03은 이미지 취약점 스캔(Trivy 설치·스캔)을 다룬다.
