#!/usr/bin/env bash
# 골든 이미지 llm-course:v2 빌드 + 수락 시험 (조교용 한 방 스크립트)
#
#   bash build.sh              # 빌드 → 수락 시험
#   bash build.sh --no-cache   # 캐시 없이 처음부터 (재현성 확인용, ~5분)
#   TAG=llm-course:v2-test bash build.sh   # 다른 태그로 시험 빌드
#
# 기준 환경은 DGX Spark(GB10/aarch64)지만, 베이스 이미지도 torch cu130 휠도
# arm64/amd64 양쪽에 존재하므로 일반 x86 + RTX(Blackwell) 장비에서도 그대로 빌드된다.
set -euo pipefail

TAG="${TAG:-llm-course:v2}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTRA=("$@")

step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

step "0. 사전 조건"
ARCH="$(LC_ALL=C uname -m)"
case "$ARCH" in
  aarch64) echo "아키텍처 $ARCH (기준 환경 — DGX Spark)" ;;
  x86_64)  echo "아키텍처 $ARCH (비기준 환경 — 빌드는 되지만 교재 실측치는 GB10 기준이다)" ;;
  *)       echo "FAIL: 지원하지 않는 아키텍처 $ARCH"; exit 1 ;;
esac
command -v docker >/dev/null || { echo "FAIL: docker 없음"; exit 1; }
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader || { echo "FAIL: 호스트 nvidia-smi 실패 — 드라이버 먼저"; exit 1; }
docker run --rm --gpus all nvidia/cuda:13.0.1-runtime-ubuntu24.04 nvidia-smi -L >/dev/null 2>&1 \
  || { echo "FAIL: 컨테이너가 GPU 를 못 본다 — nvidia-container-toolkit 설치/설정 확인"; exit 1; }
echo "사전 조건 OK"

step "1. 빌드 → $TAG"
# Dockerfile 마지막 단계에 verify-env --no-gpu 자체검사가 들어 있다.
# 패키지가 하나라도 고정 버전과 어긋나면 여기서 빌드가 실패하고 태그가 붙지 않는다.
docker build "${EXTRA[@]}" -t "$TAG" -f "$HERE/Dockerfile.llm-course-v2" "$HERE"
docker images "$TAG" --format '이미지 {{.Repository}}:{{.Tag}}  {{.Size}}'

step "2. 런타임 검증 (GPU 실연산 — 인식이 아니라 계산을 검사한다)"
docker run --rm --gpus all "$TAG" verify-env

step "3. 수락 시험 (교재 15주가 쓰는 GPU 12연산 + 한글 폰트 + 의도적 부재)"
docker run --rm --gpus all --shm-size=8g \
  -v "$HERE/smoke_test.py:/work/smoke_test.py:ro" \
  "$TAG" python3 /work/smoke_test.py

step "4. 완료 — 실습 컨테이너 기동"
cat <<EOF
bash run-llm-lab.sh            # 권장: 마운트·재시작정책·shm 까지 맞춰서 생성

# 직접 띄운다면
docker run -d --name llm-lab --gpus all --restart unless-stopped --shm-size=8g \\
  -v \$HOME/work:/work -v \$HOME/textbook:/textbook \\
  $TAG sleep infinity
docker exec -it llm-lab bash     # 재진입
EOF
