# spec-report.md — 내 장비 사양 (P1-1 산출물)

> 조회 전용 명령만 사용했다(시스템 변경 없음). 각 항목은 확인 명령과 출력 원문을 함께 남긴다.

| 항목 | 확인에 사용한 명령 | 출력 원문(핵심 줄만) |
|---|---|---|
| CPU 아키텍처 | `LC_ALL=C lscpu \| grep '^Architecture'` | `Architecture:  aarch64` |
| CPU 코어 수 | `LC_ALL=C lscpu \| grep '^CPU(s):'` | `CPU(s):  20` |
| CPU 모델 | `LC_ALL=C lscpu \| grep '^Model name'` | `Model name: Cortex-X925` / `Model name: Cortex-A725` (big.LITTLE 2클러스터) |
| 메모리 총량 | `free -h \| head -2` | `메모리: 119Gi 총계` (통합 메모리 128GB의 OS 가시량) |
| GPU 모델명 | `nvidia-smi --query-gpu=name,driver_version --format=csv,noheader` | `NVIDIA GB10, 580.126.09` |
| 디스크 용량 | `df -h / \| tail -1` | `/dev/nvme0n1p2  3.6T  1.2T  2.3T  36% /` |
| OS 배포판/버전 | `grep PRETTY_NAME /etc/os-release` | `PRETTY_NAME="Ubuntu 24.04.4 LTS"` |
| DGX OS 버전 | `cat /etc/dgx-release` | `DGX_NAME="DGX Spark"`, `DGX_SWBUILD_VERSION="7.2.3"`, `DGX_OTA_VERSION="7.4.0"` |
| 커널 버전 | `uname -r` | `6.17.0-1008-nvidia` |
| NVIDIA 드라이버 | `nvidia-smi --query-gpu=driver_version --format=csv,noheader` | `580.126.09` |
| CUDA 버전 | `nvcc --version \| tail -2` | `Cuda compilation tools, release 13.0, V13.0.88` |
| Docker 버전 | `docker --version` | `Docker version 29.1.3, build f52814d` |

## ⚠️ 한국어 로케일 주의 (검증 중 발견)

이 장비의 로케일은 `LANG=ko_KR.utf8` 이다. 따라서 `lscpu`가 **한국어 라벨**을 출력한다.

```
$ lscpu | head -3
아키텍처:                         aarch64
CPU 동작 모드:                    64-bit
바이트 순서:                      Little Endian
```

`lscpu | grep Architecture` 는 **아무것도 출력하지 않는다.** 반드시 `LC_ALL=C` 로 로케일을 고정한다.

```
$ LC_ALL=C lscpu | grep '^Architecture'
Architecture:  aarch64
```

같은 이유로 `free`, `df` 의 헤더도 한국어다. 값 자체는 영향이 없으나 헤더로 grep/파싱하면 깨진다.

## 교차 검증 (V1-1)

| 항목 | 1차 값 (1차 명령) | 2차 값 (다른 명령) | 일치 |
|---|---|---|---|
| 아키텍처 | `aarch64` (`lscpu`) | `aarch64` (`uname -m`) | ✅ |
| 메모리 | `119Gi` (`free -h`) | `MemTotal: 125257788 kB` ≈ 119.5GiB (`/proc/meminfo`) | ✅ |
| CPU 코어 | `20` (`lscpu`) | `20` (`nproc`) | ✅ |
| GPU | `NVIDIA GB10` (`nvidia-smi --query-gpu`) | `NVIDIA GB10` (`nvidia-smi -L`) | ✅ |
| 커널 | `6.17.0-1008-nvidia` (`uname -r`) | `6.17.0-1008-nvidia` (`/proc/version`) | ✅ |
| CUDA | `13.0` (`nvcc`) | `13.0` (`nvidia-smi` 헤더 CUDA Version) | ✅ |
| OS | `Ubuntu 24.04.4 LTS` (`/etc/os-release`) | `Ubuntu 24.04.4 LTS` (`lsb_release -d`) | ✅ |

교차 검증 완료: 2026-07-30
