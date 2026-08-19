#!/usr/bin/env bash
# =============================================================================
# Jarvis Phase 0B — ลบ cron ของ gate trial ทิ้งหลังทดสอบเสร็จ
# =============================================================================
#   bash scripts/gate-trial-teardown.sh
#
# ลบเฉพาะ job ที่ชื่อขึ้นต้นด้วย jarvis-gate- เท่านั้น
# job อื่นที่ตั้งเองไว้ไม่ถูกแตะ
# =============================================================================
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_BIN="${HERMES_BIN:-$HERMES_HOME/hermes-agent/venv/bin/hermes}"

C_OK=$'\033[0;32m'; C_INFO=$'\033[0;36m'; C_OFF=$'\033[0m'
[ -x "$HERMES_BIN" ] || HERMES_BIN="$(command -v hermes 2>/dev/null || true)"
[ -n "$HERMES_BIN" ] && [ -x "$HERMES_BIN" ] || { echo "หา hermes ไม่เจอ" >&2; exit 1; }

echo
echo "${C_INFO}→${C_OFF} ค้นหา job ของ gate trial..."

# ดึงคู่ (id, name) จากผลลัพธ์ของ cron list แล้วเลือกเฉพาะที่ชื่อขึ้นต้น jarvis-gate-
# หมายเหตุ: awk ที่มากับ Ubuntu คือ mawk ซึ่ง "ไม่รองรับ" regex แบบ {6,}
# ถ้าใช้ {6,} มันจะไม่ match อะไรเลยแบบเงียบๆ แล้วสคริปต์จะบอกว่าลบเสร็จทั้งที่ยังอยู่
# จึงใช้ length() แทน — ทำงานได้ทั้ง mawk และ gawk
IDS=$(timeout 40 "$HERMES_BIN" cron list 2>/dev/null | awk '
  $1 ~ /^[0-9a-f]+$/ && length($1) >= 6 && $2 ~ /^\[/ { id = $1 }
  $1 == "Name:" && index($2, "jarvis-gate-") == 1 { if (id != "") { print id; id = "" } }
')

if [ -z "$IDS" ]; then
  echo "${C_OK}✓${C_OFF} ไม่มี job ของ gate trial เหลืออยู่ — เก็บกวาดเรียบร้อยแล้ว"
  exit 0
fi

for id in $IDS; do
  echo "${C_INFO}→${C_OFF} ลบ job $id ..."
  timeout 40 "$HERMES_BIN" cron remove "$id" 2>&1 | sed 's/^/    /' || true
done

echo
echo "${C_OK}✓${C_OFF} เก็บกวาดเรียบร้อย — job ที่เหลือ:"
timeout 40 "$HERMES_BIN" cron list 2>&1 | sed 's/^/    /'
echo
