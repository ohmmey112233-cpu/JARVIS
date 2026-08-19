#!/usr/bin/env bash
# =============================================================================
# Jarvis Phase 0B — ขั้นที่ 3: เปิด Telegram gateway ให้รันตลอด 24 ชม.
# =============================================================================
# gateway = process ที่คอยฟังข้อความ Telegram และเป็นตัวยิง cron job ด้วย
# ถ้า gateway ไม่รัน → ทั้งแชทและ digest ตอนเช้าจะไม่ทำงาน
#
#   bash scripts/03-start-gateway.sh
# =============================================================================
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_BIN="${HERMES_BIN:-$HERMES_HOME/hermes-agent/venv/bin/hermes}"
WHOAMI="${USER:-$(id -un)}"

C_OK=$'\033[0;32m'; C_WARN=$'\033[0;33m'; C_ERR=$'\033[0;31m'; C_INFO=$'\033[0;36m'; C_OFF=$'\033[0m'
ok()   { echo "${C_OK}✓${C_OFF} $*"; }
info() { echo "${C_INFO}→${C_OFF} $*"; }
warn() { echo "${C_WARN}⚠${C_OFF} $*"; }
die()  { echo "${C_ERR}✗${C_OFF} $*" >&2; exit 1; }

echo
echo "=============================================="
echo " Jarvis Phase 0B — เปิด Telegram gateway"
echo "=============================================="
echo

[ -x "$HERMES_BIN" ] || HERMES_BIN="$(command -v hermes 2>/dev/null || true)"
[ -n "$HERMES_BIN" ] && [ -x "$HERMES_BIN" ] || die "หา hermes ไม่เจอ — รัน scripts/01-install-hermes.sh ก่อน"

# --- ตรวจก่อนว่าตั้งค่าครบจริง -----------------------------------------------
grep -q '^TELEGRAM_BOT_TOKEN=.\+' "$HERMES_HOME/.env" 2>/dev/null \
  || die "ยังไม่มี TELEGRAM_BOT_TOKEN ใน $HERMES_HOME/.env — รัน scripts/02-configure-jarvis.sh ก่อน"
grep -q '^ANTHROPIC_API_KEY=.\+' "$HERMES_HOME/.env" 2>/dev/null \
  || die "ยังไม่มี ANTHROPIC_API_KEY ใน $HERMES_HOME/.env — รัน scripts/02-configure-jarvis.sh ก่อน"
ok "ค่าลับครบ"

# --- เปิด lingering: ให้ service รันต่อแม้ logout / หลังรีบูต -------------------
if command -v loginctl >/dev/null 2>&1; then
  if [ "$(loginctl show-user "$WHOAMI" -p Linger --value 2>/dev/null || echo no)" = "yes" ]; then
    ok "เปิด lingering ไว้แล้ว (service รันต่อแม้ปิด SSH)"
  else
    info "เปิด lingering เพื่อให้ gateway รันต่อหลัง logout และหลังรีบูต..."
    if sudo -n loginctl enable-linger "$WHOAMI" 2>/dev/null; then
      ok "เปิด lingering แล้ว"
    else
      warn "เปิด lingering อัตโนมัติไม่ได้ (ต้องใส่รหัส sudo)"
      warn "สำคัญมาก — รันเองด้วยมือ ไม่งั้นพอปิด SSH gateway จะดับ:"
      echo "     sudo loginctl enable-linger $WHOAMI"
    fi
  fi
fi

# --- ติดตั้งเป็น systemd service ---------------------------------------------
info "ติดตั้ง gateway เป็น systemd service..."
"$HERMES_BIN" gateway install 2>&1 | sed 's/^/    /' || die "ติดตั้ง service ไม่สำเร็จ"

info "สั่งให้ gateway เริ่มทำงาน..."
"$HERMES_BIN" gateway start 2>&1 | sed 's/^/    /' || warn "สั่ง start แล้วมี warning — เช็ค status ด้านล่าง"

# ให้เวลามันต่อ Telegram สักครู่ก่อนเช็ค
sleep 5

echo
info "สถานะ gateway:"
"$HERMES_BIN" gateway status 2>&1 | sed 's/^/    /' || true

echo
echo "=============================================="
ok "ขั้นที่ 3 เสร็จ"
echo "=============================================="
echo
echo "ทดสอบเดี๋ยวนี้เลย:"
echo "  เปิด Telegram → ทักบอทที่สร้างไว้ → พิมพ์ 'สวัสดี'"
echo "  ถ้าตอบกลับเป็นภาษาไทย = ต่อครบวงจรแล้ว 🎉"
echo
echo "ถ้าบอทเงียบ ให้ดู log:"
echo "  journalctl --user -u hermes-gateway -f --no-pager"
echo
echo "คำสั่งที่ใช้บ่อย:"
echo "  hermes gateway status      ดูสถานะ"
echo "  hermes gateway restart     รีสตาร์ท (ใช้ทุกครั้งหลังแก้ config)"
echo "  hermes gateway stop        หยุด"
echo
echo "ขั้นต่อไป:  bash scripts/verify-phase0b.sh   (ตรวจให้ครบก่อนเริ่ม gate trial)"
echo
