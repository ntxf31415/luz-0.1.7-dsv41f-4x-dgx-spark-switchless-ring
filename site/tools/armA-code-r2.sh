#!/bin/bash
set -uo pipefail
cd "$HOME/luz017"
TAG="luz024-code-r2"
LOG="logs-tp4/$TAG.log"
exec > "$LOG" 2>&1
echo "=== code round 2 start $(date -Is) ==="
docker cp benchmarks/de_matrix_v3.py dsv41-head:/state/sdbench/de_matrix_v3.py
docker exec -e OUT_DIR="/state/bench-results/de-$TAG" -e RUN_TAG="$TAG" \
  -e TYPES=code -e CONCURRENCIES=1,2,4,8,16 -e WAVES=3 -e MAXTOK=2048 \
  dsv41-head python3 /state/sdbench/de_matrix_v3.py
echo "code r2 exit=$?"
echo "=== done $(date -Is) ==="
