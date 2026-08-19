#!/usr/bin/env bash
# =============================================================================
# Jarvis Phase 0B — ตรวจสอบว่าติดตั้งครบและใช้งานได้จริง
# =============================================================================
# รันได้ตลอดเวลา ไม่แก้อะไรทั้งนั้น — อ่านอย่างเดียว
#   bash scripts/verify-phase0b.sh
#
# ต่างจากการ "ดู config ว่าตั้งถูกไหม" ตรงที่อันนี้ยิง API จริงไปเช็ค
# ทั้ง Anthropic และ Telegram ว่า key ใช้ได้จริง ไม่ใช่แค่มีตัวอักษรครบ
# =============================================================================
set -uo pipefail   # ไม่ใช้ -e เพราะต้องการให้ตรวจครบทุกข้อแม้บางข้อ fail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_ENV="$HERMES_HOME/.env"
HERMES_BIN="${HERMES_BIN:-$HERMES_HOME/hermes-agent/venv/bin/hermes}"
WHOAMI="${USER:-$(id -un)}"

C_OK=$'\033[0;32m'; C_WARN=$'\033[0;33m'; C_ERR=$'\033[0;31m'; C_OFF=$'\033[0m'
PASS=0; FAIL=0; WARNED=0
pass() { echo "${C_OK}  ✓${C_OFF} $*"; PASS=$((PASS+1)); }
fail() { echo "${C_ERR}  ✗${C_OFF} $*"; FAIL=$((FAIL+1)); }
warn() { echo "${C_WARN}  ⚠${C_OFF} $*"; WARNED=$((WARNED+1)); }
head2(){ echo; echo "── $* ──"; }

# อ่านค่าจาก .env โดยไม่ต้อง source (กันไฟล์พังแล้ว shell ตาย)
env_get() { grep -m1 "^$1=" "$HERMES_ENV" 2>/dev/null | cut -d= -f2- ; }

echo
echo "=============================================="
echo " Jarvis Phase 0B — ผลการตรวจสอบ"
echo "=============================================="

# --- 1. ตัว Hermes -----------------------------------------------------------
head2 "1. Hermes Agent"
[ -x "$HERMES_BIN" ] || HERMES_BIN="$(command -v hermes 2>/dev/null || true)"
if [ -n "$HERMES_BIN" ] && [ -x "$HERMES_BIN" ]; then
  pass "ติดตั้งแล้ว: $HERMES_BIN"
  if [ -f "$HERMES_HOME/jarvis-version.lock" ]; then
    LOCKED_VER=$(grep -m1 '^hermes_version=' "$HERMES_HOME/jarvis-version.lock" | cut -d= -f2)
    pass "เวอร์ชันที่บันทึกไว้: ${LOCKED_VER:-unknown}"
  else
    warn "ไม่มีไฟล์บันทึกเวอร์ชัน (jarvis-version.lock) — รัน 01-install-hermes.sh อีกรอบเพื่อสร้าง"
  fi
else
  fail "หา hermes ไม่เจอ — รัน scripts/01-install-hermes.sh"
  echo; echo "หยุดตรวจ เพราะไม่มี hermes ให้ตรวจต่อ"; exit 1
fi

# --- 2. timezone (กฎเหล็กข้อ 3) ----------------------------------------------
head2 "2. Timezone — ต้องเป็นเวลาไทย"
CFG_TZ=$(timeout 30 "$HERMES_BIN" config get timezone 2>/dev/null | tail -1)
if [ "$CFG_TZ" = "Asia/Bangkok" ]; then
  pass "Hermes timezone = Asia/Bangkok"
else
  fail "Hermes timezone = '${CFG_TZ:-ไม่ได้ตั้ง}' (ต้องเป็น Asia/Bangkok)
       แก้: hermes config set timezone Asia/Bangkok && hermes gateway restart"
fi
OS_TZ=$(timedatectl show -p Timezone --value 2>/dev/null || echo unknown)
if [ "$OS_TZ" = "Asia/Bangkok" ]; then
  pass "timezone ของ VPS = Asia/Bangkok"
else
  warn "timezone ของ VPS = $OS_TZ — ไม่ blocking แต่ทำให้อ่าน log สับสน
       แก้: sudo timedatectl set-timezone Asia/Bangkok"
fi
pass "เวลาเครื่องตอนนี้: $(date '+%Y-%m-%d %H:%M:%S %Z (%z)')"

# --- 3. โมเดล ----------------------------------------------------------------
head2 "3. Claude เป็นโมเดลหลัก"
PROVIDER=$(timeout 30 "$HERMES_BIN" config get model.provider 2>/dev/null | tail -1)
MODEL=$(timeout 30 "$HERMES_BIN" config get model.default 2>/dev/null | tail -1)
[ "$PROVIDER" = "anthropic" ] \
  && pass "provider = anthropic (ยิงตรง Anthropic API)" \
  || fail "provider = '${PROVIDER:-ไม่ได้ตั้ง}' (ต้องเป็น anthropic)
       แก้: hermes config set model.provider anthropic"
case "$MODEL" in
  claude-*) pass "โมเดลหลัก = $MODEL" ;;
  *) fail "โมเดลหลัก = '${MODEL:-ไม่ได้ตั้ง}' — ต้องเป็นโมเดลตระกูล claude-*
       แก้: hermes config set model.default claude-opus-5" ;;
esac
case "$MODEL" in
  claude-opus-5)   warn "opus-5 ราคา \$5/\$25 ต่อ 1M token — spec ตั้งงบไว้ \$2-10/เดือน อาจเกิน
       ถ้าอยากคุมงบ: hermes config set model.default claude-sonnet-5 (\$3/\$15)" ;;
  claude-sonnet-5) pass "sonnet-5 = ตัวเลือกคุมงบ (\$3/\$15 ต่อ 1M token)" ;;
esac

# --- 4. ค่าลับ ---------------------------------------------------------------
head2 "4. ค่าลับใน ~/.hermes/.env"
if [ -f "$HERMES_ENV" ]; then
  PERM=$(stat -c '%a' "$HERMES_ENV" 2>/dev/null || echo "?")
  [ "$PERM" = "600" ] \
    && pass "สิทธิ์ไฟล์ 600 (อ่านได้เฉพาะเจ้าของ)" \
    || warn "สิทธิ์ไฟล์ $PERM — ควรเป็น 600  แก้: chmod 600 $HERMES_ENV"
else
  fail "ไม่มีไฟล์ $HERMES_ENV — รัน scripts/02-configure-jarvis.sh"
fi

AKEY=$(env_get ANTHROPIC_API_KEY)
BTOKEN=$(env_get TELEGRAM_BOT_TOKEN)
AUSERS=$(env_get TELEGRAM_ALLOWED_USERS)

[ -n "$AKEY" ]   && pass "มี ANTHROPIC_API_KEY"      || fail "ไม่มี ANTHROPIC_API_KEY"
[ -n "$BTOKEN" ] && pass "มี TELEGRAM_BOT_TOKEN"     || fail "ไม่มี TELEGRAM_BOT_TOKEN"
if [ -z "$AUSERS" ]; then
  fail "ไม่มี TELEGRAM_ALLOWED_USERS — ใครก็สั่ง Jarvis ได้ อันตราย"
elif echo "$AUSERS" | grep -qE '^[0-9]+(,[0-9]+)*$'; then
  pass "TELEGRAM_ALLOWED_USERS ตั้งไว้ $(echo "$AUSERS" | tr ',' '\n' | grep -c .) คน (เป็นตัวเลข ถูกต้อง)"
else
  fail "TELEGRAM_ALLOWED_USERS ไม่ใช่ตัวเลขล้วน — กันคนอื่นไม่ได้จริง"
fi

# --- 5. ยิง API จริงเพื่อพิสูจน์ว่า key ใช้ได้ ---------------------------------
head2 "5. ทดสอบ key จริง (ยิง API ออกไปจริง)"
if command -v curl >/dev/null 2>&1 && [ -n "$AKEY" ]; then
  HTTP=$(curl -s -o /tmp/.jarvis_anthropic_check -w '%{http_code}' --max-time 25 \
        -H "x-api-key: $AKEY" -H "anthropic-version: 2023-06-01" \
        https://api.anthropic.com/v1/models 2>/dev/null || echo 000)
  case "$HTTP" in
    200) N=$(grep -o '"id"' /tmp/.jarvis_anthropic_check 2>/dev/null | wc -l)
         pass "Anthropic API ตอบกลับ 200 — key ใช้ได้จริง (เห็นโมเดล $N ตัว)"
         if grep -q "\"$MODEL\"" /tmp/.jarvis_anthropic_check 2>/dev/null; then
           pass "บัญชีนี้เข้าถึงโมเดล $MODEL ได้"
         else
           warn "ไม่เห็น '$MODEL' ในรายการโมเดลที่บัญชีนี้เข้าถึงได้ — ตรวจชื่อโมเดลอีกที
       ดูรายชื่อทั้งหมด: curl -H \"x-api-key: \$ANTHROPIC_API_KEY\" -H 'anthropic-version: 2023-06-01' https://api.anthropic.com/v1/models"
         fi ;;
    401) fail "Anthropic ตอบ 401 — key ผิดหรือถูกเพิกถอน สร้างใหม่ที่ console.anthropic.com" ;;
    000) warn "ต่อ api.anthropic.com ไม่ได้ (เน็ต/firewall) — ตรวจซ้ำทีหลัง" ;;
    *)   fail "Anthropic ตอบ HTTP $HTTP — ดูรายละเอียด: cat /tmp/.jarvis_anthropic_check" ;;
  esac
  rm -f /tmp/.jarvis_anthropic_check
fi

if command -v curl >/dev/null 2>&1 && [ -n "$BTOKEN" ]; then
  RESP=$(curl -s --max-time 25 "https://api.telegram.org/bot$BTOKEN/getMe" 2>/dev/null || echo '')
  if echo "$RESP" | grep -q '"ok":true'; then
    BOTNAME=$(echo "$RESP" | grep -o '"username":"[^"]*"' | head -1 | cut -d'"' -f4)
    pass "Telegram bot token ใช้ได้จริง — บอทชื่อ @${BOTNAME:-unknown}"
  elif echo "$RESP" | grep -q '"ok":false'; then
    fail "Telegram ปฏิเสธ token — สร้างใหม่ที่ @BotFather (/mybots → API Token)"
  else
    warn "ต่อ api.telegram.org ไม่ได้ — ตรวจซ้ำทีหลัง"
  fi
fi

# --- 6. gateway --------------------------------------------------------------
head2 "6. Telegram gateway (ตัวที่ทำให้แชทและ cron ทำงาน)"
GW=$(timeout 40 "$HERMES_BIN" gateway status 2>&1 || echo "")
# ระวัง: ข้อความตอนไม่ได้รันคือ "Gateway is not running" — มีคำว่า running อยู่ด้วย
# ต้องเช็ค "not running" ก่อนเสมอ ไม่งั้นจะรายงานผ่านทั้งที่ไม่ได้รัน
if echo "$GW" | grep -qiE 'not running|inactive|dead|failed'; then
  fail "gateway ไม่ได้รัน — แชทและ digest จะไม่ทำงาน
       แก้: hermes gateway start
       ดู log: journalctl --user -u hermes-gateway -n 50 --no-pager"
elif echo "$GW" | grep -qiE 'running|active'; then
  pass "gateway กำลังรัน"
else
  warn "อ่านสถานะ gateway ไม่ออก — ตรวจเอง: hermes gateway status"
fi
if command -v loginctl >/dev/null 2>&1; then
  [ "$(loginctl show-user "$WHOAMI" -p Linger --value 2>/dev/null || echo no)" = "yes" ] \
    && pass "เปิด lingering แล้ว (รันต่อหลังปิด SSH และหลังรีบูต)" \
    || warn "ยังไม่เปิด lingering — พอปิด SSH gateway อาจดับ
       แก้: sudo loginctl enable-linger $WHOAMI"
fi

# --- 7. cron -----------------------------------------------------------------
head2 "7. ตัวตั้งเวลา (cron) — ใช้ทดสอบ digest เช้า"
CRON=$(timeout 40 "$HERMES_BIN" cron list 2>&1 || echo "")
if echo "$CRON" | grep -q 'No scheduled jobs'; then
  warn "ยังไม่มี job — ตั้งได้ด้วย: bash scripts/gate-trial-setup.sh"
else
  NEXT=$(echo "$CRON" | grep -m1 'Next run:' | sed 's/.*Next run:[[:space:]]*//')
  pass "มี job ตั้งไว้แล้ว"
  if [ -n "$NEXT" ]; then
    case "$NEXT" in
      *+07:00*) pass "รอบถัดไป: $NEXT  ← ลงท้าย +07:00 = เวลาไทย ถูกต้อง" ;;
      *) fail "รอบถัดไป: $NEXT  ← ไม่ใช่ +07:00 แปลว่า timezone ผิด digest จะมาผิดเวลา" ;;
    esac
  fi
fi

# --- สรุป -------------------------------------------------------------------
echo
echo "=============================================="
echo " สรุป: ผ่าน $PASS / เตือน $WARNED / ไม่ผ่าน $FAIL"
echo "=============================================="
if [ "$FAIL" -eq 0 ]; then
  echo "${C_OK}พร้อมเริ่ม gate trial แล้ว${C_OFF} → อ่าน docs/gate-trial.md"
  echo "เริ่มเลย:  bash scripts/gate-trial-setup.sh"
  exit 0
else
  echo "${C_ERR}แก้ข้อที่ ✗ ให้หมดก่อนเริ่ม gate trial${C_OFF}"
  echo "ติดตรงไหนดู docs/troubleshooting.md"
  exit 1
fi
