#!/usr/bin/env bash
# 실습 컨테이너 llm-lab 생성 — 새 장비에 배포할 때 이 스크립트 하나면 된다.
#
#   bash harness/run-llm-lab.sh
#
# 교재 W01 P1-4 가 요구하는 컨테이너를 만든다. 학생이 프롬프트로 직접 만드는 것이
# 원래 미션이므로, 이 스크립트는 강사/조교가 장비를 준비할 때와 사고 복구용이다.
set -euo pipefail

IMAGE="${IMAGE:-llm-course:v2}"
NAME="${NAME:-llm-lab}"
ROOT="${ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
WORK_SRC="${WORK_SRC:-$ROOT/code}"          # 컨테이너 /work — 학생 산출물이 쌓이는 곳
BOOK_SRC="${BOOK_SRC:-$ROOT/textbook}"      # 컨테이너 /textbook — 교재 원본 저장소

die() { echo "❌ $*" >&2; exit 1; }

docker image inspect "$IMAGE" >/dev/null 2>&1 \
  || die "이미지 $IMAGE 없음. 먼저: docker build -f harness/Dockerfile.llm-course-v2 -t $IMAGE harness/"

mkdir -p "$WORK_SRC" "$BOOK_SRC"

if docker container inspect "$NAME" >/dev/null 2>&1; then
  echo "기존 컨테이너 $NAME 제거 (마운트된 $WORK_SRC 의 산출물은 영향 없음)"
  docker rm -f "$NAME" >/dev/null
fi

# --restart unless-stopped : v1 에서 이게 없어 호스트 재부팅 뒤 컨테이너가 안 살아났다.
# --shm-size 8g            : DataLoader num_workers>0 이 기본 64MB 공유메모리에서 죽는다.
docker run -d \
  --name "$NAME" \
  --gpus all \
  --restart unless-stopped \
  --shm-size=8g \
  -v "$WORK_SRC:/work" \
  -v "$BOOK_SRC:/textbook" \
  "$IMAGE" sleep infinity >/dev/null

echo "생성됨: $NAME  ($IMAGE)"
echo
docker exec "$NAME" verify-env

cat <<EOF

재진입:  docker exec -it $NAME bash
정지:    docker stop $NAME      (재부팅 시 자동 복귀는 --restart unless-stopped 로 보장)
EOF
