#!/usr/bin/env bash
# =============================================================================
# Jarvis Phase 1 — ลบ cron digest ทั้งชุด + สคริปต์ตัวกลางที่ generate ไว้
# =============================================================================
#   bash scripts/phase1-digests-teardown.sh
#
# ลบเฉพาะ job ที่ชื่อขึ้นต้นด้วย jarvis-p1- และไฟล์ ~/.hermes/scripts/jarvis-p1-*.sh
# job อื่นที่ตั้งเองไว้ (รวมถึง jarvis-gate-* ของ gate trial) ไม่ถูกแตะ
# =============================================================================
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_BIN="${HERMES_BIN:-$HERMES_HOME/hermes-agent/venv/bin/hermes}"
SCRIPTS_DIR="$HERMES_HOME/scripts"

C_OK=$'\033[0;32m'; C_INFO=$'\033[0;36m'; C_OFF=$'\033[0m'
[ -x "$HERMES_BIN" ] || HERMES_BIN="$(command -v hermes 2>/dev/null || true)"
[ -n "$HERMES_BIN" ] && [ -x "$HERMES_BIN" ] || { echo "หา hermes ไม่เจอ" >&2; exit 1; }

echo
echo "${C_INFO}→${C_OFF} ค้นหา job digest ของ Phase 1..."

# ดึงคู่ (id, name) จากผลลัพธ์ของ cron list แล้วเลือกเฉพาะที่ชื่อขึ้นต้น jarvis-p1-
# หมายเหตุ: awk ที่มากับ Ubuntu คือ mawk ซึ่ง "ไม่รองรับ" regex แบบ {6,}
# ถ้าใช้ {6,} มันจะไม่ match อะไรเลยแบบเงียบๆ แล้วสคริปต์จะบอกว่าลบเสร็จทั้งที่ยังอยู่
# จึงใช้ length() แทน — ทำงานได้ทั้ง mawk และ gawk
IDS=$(timeout 40 "$HERMES_BIN" cron list 2>/dev/null | awk '
  $1 ~ /^[0-9a-f]+$/ && length($1) >= 6 && $2 ~ /^\[/ { id = $1 }
  $1 == "Name:" && index($2, "jarvis-p1-") == 1 { if (id != "") { print id; id = "" } }
')

if [ -z "$IDS" ]; then
  echo "${C_OK}✓${C_OFF} ไม่มี job jarvis-p1-* เหลืออยู่"
else
  for id in $IDS; do
    echo "${C_INFO}→${C_OFF} ลบ job $id ..."
    timeout 40 "$HERMES_BIN" cron remove "$id" 2>&1 | sed 's/^/    /' || true
  done
fi

# ลบสคริปต์ตัวกลางที่ setup generate ไว้ — ลบเฉพาะชื่อที่เรา generate เอง
# (glob ไม่เจออะไร = ลูปไม่วิ่ง เพราะเช็ค -e ก่อน ไม่ต้องพึ่ง nullglob)
REMOVED=0
for f in "$SCRIPTS_DIR"/jarvis-p1-*.sh; do
  [ -e "$f" ] || continue
  rm -f "$f"
  echo "${C_INFO}→${C_OFF} ลบ $f"
  REMOVED=$((REMOVED+1))
done
[ "$REMOVED" -eq 0 ] && echo "${C_OK}✓${C_OFF} ไม่มีสคริปต์ตัวกลางเหลืออยู่"

echo
echo "${C_OK}✓${C_OFF} เก็บกวาดเรียบร้อย — job ที่เหลือ:"
timeout 40 "$HERMES_BIN" cron list 2>&1 | sed 's/^/    /'
echo
