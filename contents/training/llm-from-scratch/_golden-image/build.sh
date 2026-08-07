#!/usr/bin/env bash
# 골든 이미지 llm-course:v1 빌드 + 수락 시험 (조교용 한 방 스크립트)
#
#   bash build.sh              # 빌드 → 스모크 테스트
#   bash build.sh --no-cache   # 캐시 없이 처음부터 (재현성 확인용, ~5분)
#   TAG=llm-course:v1-test bash build.sh   # 다른 태그로 시험 빌드
#
# 실행 위치: 이 스크립트가 있는 디렉토리. DGX Spark(GB10/aarch64) 호스트에서 돈다.
set -euo pipefail

TAG="${TAG:-llm-course:v1}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
EXTRA=("$@")

step() { printf '\n\033[1m== %s\033[0m\n' "$1"; }

step "0. 사전 조건"
LC_ALL=C uname -m | grep -qx aarch64 || { echo "FAIL: aarch64 가 아니다 ($(uname -m)) — DGX Spark 에서 실행하라"; exit 1; }
command -v docker >/dev/null || { echo "FAIL: docker 없음"; exit 1; }
nvidia-smi --query-gpu=name,driver_version --format=csv,noheader || { echo "FAIL: 호스트 nvidia-smi 실패 — 드라이버 먼저"; exit 1; }
docker run --rm --gpus all nvidia/cuda:13.0.1-runtime-ubuntu24.04 nvidia-smi -L >/dev/null 2>&1 \
  || { echo "FAIL: 컨테이너가 GPU 를 못 본다 — nvidia-container-toolkit 설치/설정 확인"; exit 1; }
echo "사전 조건 OK"

step "1. 빌드 → $TAG"
docker build "${EXTRA[@]}" -t "$TAG" -f "$HERE/Dockerfile.llm-course-v1" "$HERE"
docker images "$TAG" --format '이미지 {{.Repository}}:{{.Tag}}  {{.Size}}'

step "2. 수락 시험 (컨테이너 안 GPU 12연산 + 한글 폰트)"
docker run --rm --gpus all --ipc=host \
  -v "$HERE/smoke_test.py:/work/smoke_test.py:ro" \
  "$TAG" python3 /work/smoke_test.py

step "3. 완료 — 실습 컨테이너 기동 명령"
cat <<EOF
docker run -d --name llm-lab --gpus all --ipc=host \\
  -v \$HOME/work:/work -v \$HOME/textbook:/textbook \\
  $TAG sleep infinity
docker exec -it llm-lab bash     # 재진입
EOF
