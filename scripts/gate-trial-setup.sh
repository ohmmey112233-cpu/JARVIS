#!/usr/bin/env bash
# =============================================================================
# Jarvis Phase 0B — ตั้ง cron สำหรับ gate trial ข้อ 2 (digest เช้า 06:20)
# =============================================================================
#   bash scripts/gate-trial-setup.sh           ตั้ง digest 06:20 เวลาไทย
#   bash scripts/gate-trial-setup.sh --smoke   ตั้ง + ยิงทดสอบใน 3 นาที
#
# แนะนำให้ใส่ --smoke ครั้งแรก จะได้รู้ภายใน 3 นาทีว่าท่อส่งข้อความทำงาน
# ไม่ต้องรอถึงเช้าพรุ่งนี้แล้วมาพบว่าตั้งผิด เสียไปหนึ่งวันฟรีๆ
# =============================================================================
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_BIN="${HERMES_BIN:-$HERMES_HOME/hermes-agent/venv/bin/hermes}"
SMOKE=0
[ "${1:-}" = "--smoke" ] && SMOKE=1

C_OK=$'\033[0;32m'; C_WARN=$'\033[0;33m'; C_ERR=$'\033[0;31m'; C_INFO=$'\033[0;36m'; C_OFF=$'\033[0m'
ok()   { echo "${C_OK}✓${C_OFF} $*"; }
info() { echo "${C_INFO}→${C_OFF} $*"; }
warn() { echo "${C_WARN}⚠${C_OFF} $*"; }
die()  { echo "${C_ERR}✗${C_OFF} $*" >&2; exit 1; }

[ -x "$HERMES_BIN" ] || HERMES_BIN="$(command -v hermes 2>/dev/null || true)"
[ -n "$HERMES_BIN" ] && [ -x "$HERMES_BIN" ] || die "หา hermes ไม่เจอ — รัน scripts/01-install-hermes.sh ก่อน"

echo
echo "=============================================="
echo " Gate trial ข้อ 2 — digest เช้า 06:20 เวลาไทย"
echo "=============================================="
echo

# เตือนตั้งแต่ต้นถ้า timezone ผิด — ไม่งั้นตั้ง job ไปก็มาผิดเวลา
CFG_TZ=$(timeout 30 "$HERMES_BIN" config get timezone 2>/dev/null | tail -1)
[ "$CFG_TZ" = "Asia/Bangkok" ] \
  || die "timezone = '${CFG_TZ:-ไม่ได้ตั้ง}' ไม่ใช่ Asia/Bangkok
   ตั้ง job ตอนนี้ไปก็มาผิดเวลา แก้ก่อน:
     hermes config set timezone Asia/Bangkok && hermes gateway restart"
ok "timezone = Asia/Bangkok"

# --- prompt ของ digest ------------------------------------------------------
# cron job รันใน session ใหม่ที่ไม่มีความจำของแชทเดิม prompt ต้องอธิบายตัวเองครบ
# Phase 0B ยังไม่มี custom skill / jarvis.db ตัว digest จริงตามแบบใน phase1-kit
# ค่อยทำใน Phase 1 — ตอนนี้ทดสอบแค่ว่า "มาตรงเวลาไหม" กับ "ภาษาไทยเพี้ยนไหม"
read -r -d '' DIGEST_PROMPT <<'PROMPT' || true
คุณคือ Jarvis ผู้ช่วยส่วนตัวของโอม กำลังส่งข้อความทักทายตอนเช้า

ตอบเป็นภาษาไทยล้วน สั้นๆ ไม่เกิน 4 บรรทัด โดยมีข้อมูลครบทุกข้อนี้:
1. ทักทายตอนเช้าสั้นๆ
2. วันที่และเวลาปัจจุบัน (ต้องเป็นเวลาไทย) พร้อมบอกว่าเป็นวันอะไรของสัปดาห์
3. เหลืออีกกี่วันจะถึงสิ้นเดือน
4. ปิดท้ายด้วยประโยคให้กำลังใจสั้นๆ หนึ่งประโยค

ห้ามใช้ตาราง ห้ามใช้หัวข้อ ห้ามขึ้นต้นด้วยคำอธิบายว่ากำลังจะทำอะไร
PROMPT

# --- ตั้ง job หลัก -----------------------------------------------------------
if timeout 40 "$HERMES_BIN" cron list 2>/dev/null | grep -q 'jarvis-gate-digest'; then
  warn "มี job 'jarvis-gate-digest' อยู่แล้ว — ข้ามการสร้างซ้ำ"
  warn "ถ้าอยากตั้งใหม่ ให้ลบก่อน: bash scripts/gate-trial-teardown.sh"
else
  info "สร้าง job digest เช้า 06:20 (ทุกวัน)..."
  timeout 60 "$HERMES_BIN" cron create "20 6 * * *" "$DIGEST_PROMPT" \
    --name "jarvis-gate-digest" --deliver telegram 2>&1 | sed 's/^/    /'
  ok "สร้าง job แล้ว"
fi

# --- smoke test: ยิงทดสอบใน 3 นาที ------------------------------------------
if [ "$SMOKE" -eq 1 ]; then
  echo
  info "สร้าง job ทดสอบที่จะยิงใน 3 นาที (ยิงครั้งเดียวแล้วหายไปเอง)..."
  timeout 60 "$HERMES_BIN" cron create "3m" \
    "ตอบกลับสั้นๆ เป็นภาษาไทยบรรทัดเดียวว่า: ท่อส่งข้อความทำงานปกติ แล้วต่อท้ายด้วยวันเวลาปัจจุบันแบบเวลาไทย" \
    --name "jarvis-gate-smoke" --deliver telegram --repeat 1 2>&1 | sed 's/^/    /'
  ok "สร้าง job ทดสอบแล้ว — รอดู Telegram ใน 3 นาที"
fi

echo
info "job ทั้งหมดตอนนี้:"
timeout 40 "$HERMES_BIN" cron list 2>&1 | sed 's/^/    /'

# --- ย้ำเรื่อง gateway -------------------------------------------------------
GW=$(timeout 40 "$HERMES_BIN" gateway status 2>&1 || echo "")
if echo "$GW" | grep -qiE 'not running|inactive|dead|failed'; then
  echo
  warn "gateway ไม่ได้รัน — job จะไม่ยิงเลยแม้ตั้งไว้แล้ว"
  warn "เปิดก่อน:  hermes gateway start"
fi

echo
echo "=============================================="
ok "ตั้ง gate trial เรียบร้อย"
echo "=============================================="
echo
echo "ต่อไปทำตาม docs/gate-trial.md:"
echo "  ข้อ 1  คุยไทยกับบอทใน Telegram (ชุดคำถามอยู่ในเอกสาร)"
echo "  ข้อ 2  เช็ค 3 เช้าติดว่า digest มา 06:20 ตรงไหม  ← job ตั้งให้แล้ว"
echo "  ข้อ 3  ทดสอบสั่งจำ/แก้/ลบ/ดู ความจำผ่านแชท"
echo
echo "จดผลลงตารางใน docs/gate-trial.md แล้วตัดสิน Track A / Track B"
echo
echo "เสร็จ trial แล้วเก็บกวาด:  bash scripts/gate-trial-teardown.sh"
echo
