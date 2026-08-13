#!/bin/bash
# Nancy memory report — one command to download + open a fresh inspection workbook.
# Usage:  ./report.sh              (all users)
#         ./report.sh kamala_jaipur   (one user)
KEY="jSQ2qdMyXMJq4Y8dwcQuDjkc7zp_vB79uHvCvDTKVZA"
BASE="https://ai-memory-implementation-production.up.railway.app"
USER_ARG=""
[ -n "$1" ] && USER_ARG="?user_id=$1"
STAMP=$(date +%Y%m%d_%H%M)
OUT="$HOME/Downloads/nancy_memory_${1:-all}_${STAMP}.xlsx"
echo "Fetching report..."
CODE=$(curl -s "$BASE/export/memory-xlsx$USER_ARG" -H "X-API-Key: $KEY" -o "$OUT" -w "%{http_code}")
if [ "$CODE" = "200" ]; then
    echo "Saved: $OUT"
    open "$OUT"
else
    echo "Failed (HTTP $CODE) — is the deploy live?"
    head -3 "$OUT" 2>/dev/null
fi
