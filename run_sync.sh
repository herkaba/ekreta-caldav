#!/bin/bash
set -u

LOG="/home/noirbit/Programs/ekreta-caldav/sync.log"
exec >>"$LOG" 2>&1

echo "===== $(date '+%Y-%m-%d %H:%M:%S') START ====="

source /home/noirbit/miniconda3/etc/profile.d/conda.sh
conda activate ekreta

cd /home/noirbit/Programs/ekreta-caldav || exit 1

python -u /home/noirbit/Programs/ekreta-caldav/sync.py
STATUS=$?

echo "===== $(date '+%Y-%m-%d %H:%M:%S') END exit=$STATUS ====="
echo

exit "$STATUS"
