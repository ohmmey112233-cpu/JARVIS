#!/usr/bin/env bash
# =============================================================================
# Jarvis Phase 1 — ตั้ง cron ส่ง digest ทั้งชุด (เช้า/พุธ/เย็น/สัปดาห์/ความฝัน)
# =============================================================================
#   bash scripts/phase1-digests-setup.sh
#
# ต่างจาก gate trial ตรงที่ job ชุดนี้ "ไม่ผ่าน LLM" — ใช้ --no-agent ให้ cron
# รันสคริปต์ตัวกลางที่เรียก `python3 -m cli digest ...` แล้วเอา stdout ส่งเข้า
# Telegram ตรงๆ ทั้งก้อน เหตุผล:
#   1. digest ถูกเรนเดอร์โดย core/digest.py ให้ตรงกับแบบใน phase1-kit ทุกตัวอักษร
#      ส่งผ่าน LLM = เปลืองโทเคนฟรี + เปิดช่องให้ถ้อยคำดริฟต์จากแบบ
#   2. stdout ว่าง = Hermes ไม่ส่งอะไรเลย — เป็นกลไกเดียวกับที่ --record ใช้
#      กันส่งซ้ำ: cron ยิงซ้ำวันเดิม cli จะเงียบ ข้อความไม่เด้งซ้ำใน Telegram
#
# idempotent — รันซ้ำได้ job ที่มีอยู่แล้วจะถูกข้าม / สคริปต์ตัวกลาง generate ทับ
# เก็บกวาดทั้งชุด:  bash scripts/phase1-digests-teardown.sh
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_BIN="${HERMES_BIN:-$HERMES_HOME/hermes-agent/venv/bin/hermes}"
SCRIPTS_DIR="$HERMES_HOME/scripts"

C_OK=$'\033[0;32m'; C_WARN=$'\033[0;33m'; C_ERR=$'\033[0;31m'; C_INFO=$'\033[0;36m'; C_OFF=$'\033[0m'
ok()   { echo "${C_OK}✓${C_OFF} $*"; }
info() { echo "${C_INFO}→${C_OFF} $*"; }
warn() { echo "${C_WARN}⚠${C_OFF} $*"; }
die()  { echo "${C_ERR}✗${C_OFF} $*" >&2; exit 1; }

[ -x "$HERMES_BIN" ] || HERMES_BIN="$(command -v hermes 2>/dev/null || true)"
[ -n "$HERMES_BIN" ] && [ -x "$HERMES_BIN" ] || die "หา hermes ไม่เจอ — รัน scripts/01-install-hermes.sh ก่อน"
[ -f "$REPO_DIR/jarvis/cli.py" ] || die "ไม่พบ $REPO_DIR/jarvis/cli.py — สคริปต์นี้ต้องอยู่ใน checkout ของ repo"

echo
echo "=============================================="
echo " Jarvis Phase 1 — ตั้ง cron digest ทั้งชุด"
echo "=============================================="
echo

# --- ด่านที่ 1: timezone ต้องเป็น Asia/Bangkok ก่อน --------------------------
# เวลาในตาราง cron ข้างล่างเป็นเวลาไทยทั้งหมด — timezone ผิด = มาผิดเวลาทุก job
CFG_TZ=$(timeout 30 "$HERMES_BIN" config get timezone 2>/dev/null | tail -1)
[ "$CFG_TZ" = "Asia/Bangkok" ] \
  || die "timezone = '${CFG_TZ:-ไม่ได้ตั้ง}' ไม่ใช่ Asia/Bangkok
   ตั้ง job ตอนนี้ไปก็มาผิดเวลา แก้ก่อน:
     hermes config set timezone Asia/Bangkok && hermes gateway restart"
ok "timezone = Asia/Bangkok"

# --- ด่านที่ 2: ค่าที่ต้องกรอกเองต้องครบก่อน ---------------------------------
# digest ที่ออกไปทั้งที่ friday_anchor_date ยังไม่ได้กรอก จะเงียบเรื่องบ้าน/โรงแรม
# และ routine ที่ไม่มี last_done จะเตือนว่าถึงรอบทุกวัน — ตั้ง cron ไปตอนนี้
# ก็ได้ข้อความผิดๆ ส่งเข้ามือถือทุกเช้า จึงบังคับให้ doctor ผ่านก่อน
info "ตรวจความพร้อมด้วย cli doctor..."
set +e
DOCTOR_OUT=$(cd "$REPO_DIR" && PYTHONPATH=jarvis python3 -m cli doctor 2>&1)
DOCTOR_CODE=$?
set -e
if [ "$DOCTOR_CODE" -ne 0 ]; then
  # ดึงรายการปัญหาจาก JSON ของ doctor มาโชว์ — ถ้า parse ไม่ได้ก็เทดิบทั้งก้อน
  echo "$DOCTOR_OUT" | python3 -c '
import json, sys
payload = None
for line in reversed([l for l in sys.stdin.read().splitlines() if l.strip()]):
    try:
        payload = json.loads(line)
        break
    except ValueError:
        continue
if payload is None:
    sys.exit(1)
problems = (payload.get("data") or {}).get("problems") or []
if not problems and payload.get("error"):
    problems = [payload["error"]]
for p in problems:
    print("    - " + str(p))
' || echo "$DOCTOR_OUT" | sed 's/^/    /'
  die "cli doctor รายงานว่ายังไม่พร้อม — กรอกค่าข้างบนให้ครบก่อนแล้วรันใหม่
   (ดูวิธีกรอกใน docs/phase1-checklist.md)"
fi
ok "cli doctor ผ่าน — ค่าที่ต้องกรอกเองครบแล้ว"

# --- generate สคริปต์ตัวกลางให้ cron เรียก -----------------------------------
# cron รันใน environment โล้นๆ ที่ไม่มี cwd/PYTHONPATH ของเรา จึงฝัง path เต็ม
# ของ checkout นี้ลงไปตอน generate เลย (REPO_DIR มาจาก BASH_SOURCE ข้างบน)
mkdir -p "$SCRIPTS_DIR"

write_job_script() {
  local kind="$1"
  local path="$SCRIPTS_DIR/jarvis-p1-digest-$kind.sh"
  cat > "$path" <<SCRIPT
#!/usr/bin/env bash
# สร้างโดย scripts/phase1-digests-setup.sh — อย่าแก้ไฟล์นี้ตรงๆ
# อยากเปลี่ยนอะไรให้แก้ที่ setup script แล้วรันซ้ำ (generate ทับ)
set -euo pipefail
cd "$REPO_DIR"
export PYTHONPATH="$REPO_DIR/jarvis"
# cron อาจให้ locale C มา — เปิด UTF-8 กันข้อความไทยพังตอน print
export PYTHONUTF8=1
# --record telegram = กันส่งซ้ำ + นับโควตา (H14: telegram ไม่นับ) — stdout ว่าง
# เมื่อวันนี้ส่ง kind นี้ไปแล้ว ซึ่ง Hermes ตีความว่า "ไม่ต้องส่งอะไร"
exec python3 -m cli digest $kind --record telegram
SCRIPT
  chmod +x "$path"
  # heredoc พังเงียบๆ ได้ถ้า REPO_DIR มีอักขระที่ bash ตีความ (เช่น ") —
  # ตรวจ syntax ทันทีที่สร้าง ดีกว่าไปรู้ตอน cron ยิงจริงพรุ่งนี้เช้า
  bash -n "$path" || die "สคริปต์ที่ generate ($path) syntax พัง — ตรวจ path ของ repo: $REPO_DIR"
  ok "generate $path"
}

info "generate สคริปต์ตัวกลางลง $SCRIPTS_DIR ..."
write_job_script morning
write_job_script evening
write_job_script weekly
write_job_script dream

# --- ตั้ง cron job (ข้ามตัวที่มีอยู่แล้ว) ------------------------------------
CRON_LIST=$(timeout 40 "$HERMES_BIN" cron list 2>/dev/null || true)

job_exists() {
  # เทียบชื่อแบบเต็มคำจากบรรทัด "Name: ..." — ใช้ grep เฉยๆ ไม่ได้เพราะ
  # 'jarvis-p1-morning' จะไปจับ 'jarvis-p1-morning-wed' ติดด้วย
  # แล้ว idempotency จะข้าม job ที่ยังไม่ได้สร้างจริง
  printf '%s\n' "$CRON_LIST" | awk -v want="$1" '
    $1 == "Name:" && $2 == want { found = 1 }
    END { exit !found }
  '
}

register_job() {
  local name="$1" schedule="$2" script_path="$3" note="$4"
  if job_exists "$name"; then
    warn "มี job '$name' อยู่แล้ว — ข้าม (อยากตั้งใหม่ให้ลบทั้งชุดก่อน: bash scripts/phase1-digests-teardown.sh)"
    return 0
  fi
  info "สร้าง job $name — $note ..."
  timeout 60 "$HERMES_BIN" cron create "$schedule" \
    --name "$name" --no-agent --script "$script_path" --deliver telegram 2>&1 | sed 's/^/    /'
  ok "สร้าง job $name แล้ว"
}

# ตารางเวลา (เวลาไทยทั้งหมด — ด่านที่ 1 การันตีแล้ว / cron: อาทิตย์=0 พุธ=3):
#   06:20 ทุกวันยกเว้นพุธ  digest เช้า
#   06:00 เฉพาะพุธ          digest เช้า — kit checklist A2: พุธต้องมา 06:00
#                           (ตื่นเร็วกว่าปกติ 20 นาที) จึงแยกเป็นคนละ job
#                           สอง job ชี้สคริปต์ตัวเดียวกัน วันพุธไม่ชนกันเพราะ
#                           job แรก exclude วันพุธ (0,1,2,4,5,6) ไว้แล้ว
#   06:18 ทุกวัน            รายงานความฝัน — จัดระเบียบความจำ + รายงาน จบในครั้งเดียว
#   18:30 ทุกวัน            สรุปเย็น
#   20:00 อาทิตย์           สรุปสัปดาห์
#
# ทำไม "ไม่มี" job ตอน 02:30 ทั้งที่ spec เขียนว่า consolidation รันตี 2:
#   `cli digest dream` เรียก memory.consolidate ในตัวอยู่แล้ว (จัดระเบียบ+รายงาน
#   เป็น atomic ครั้งเดียว — ดู docstring ของ assemble.dream_summary) และ summary
#   ที่ได้รายงาน "เฉพาะก้อนที่เพิ่งถูกพักในรอบนั้น" ถ้าแยกไปรัน `memory consolidate`
#   ตอน 02:30 อีกรอบ ก้อนที่ถูกพักตอนตี 2 จะไม่โผล่ในรายงาน 06:18 เลย
#   (รอบ 06:18 เห็นแต่ก้อนที่ยังไม่ archived) = ความจำหายเงียบๆ โดยไม่มีใครตรวจ
#   ซึ่งคือสิ่งที่ red-team H13 ห้ามตรงๆ การขยับเวลา consolidation จากตี 2 มา
#   06:18 ไม่กระทบใคร เพราะทั้งสองช่วงไม่มีคนใช้ระบบอยู่แล้ว
#   หมายเหตุ: วันพุธ digest เช้ามา 06:00 รายงานความฝันจะตามหลัง 18 นาที —
#   ยังเป็น "รายงานทุกเช้า" ตามที่ H13 ต้องการ แค่ลำดับสลับเฉพาะวันพุธ
register_job "jarvis-p1-morning"     "20 6 * * 0,1,2,4,5,6" "$SCRIPTS_DIR/jarvis-p1-digest-morning.sh" "digest เช้า 06:20 (ทุกวันยกเว้นพุธ)"
register_job "jarvis-p1-morning-wed" "0 6 * * 3"            "$SCRIPTS_DIR/jarvis-p1-digest-morning.sh" "digest เช้าวันพุธ 06:00 (ตื่นเร็วกว่าปกติ)"
register_job "jarvis-p1-dream"       "18 6 * * *"           "$SCRIPTS_DIR/jarvis-p1-digest-dream.sh"   "รายงานความฝัน 06:18 (เงียบถ้าไม่มีอะไรถูกจัดระเบียบ)"
register_job "jarvis-p1-evening"     "30 18 * * *"          "$SCRIPTS_DIR/jarvis-p1-digest-evening.sh" "สรุปเย็น 18:30 ทุกวัน"
register_job "jarvis-p1-weekly"      "0 20 * * 0"           "$SCRIPTS_DIR/jarvis-p1-digest-weekly.sh"  "สรุปสัปดาห์ อาทิตย์ 20:00"

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
ok "ตั้ง cron digest ของ Phase 1 เรียบร้อย"
echo "=============================================="
echo
echo "ต่อไปทำตาม docs/phase1-checklist.md ข้อ A:"
echo "  - digest เช้าต้องมาตรงเวลา 7 วันติดไม่ขาด (สำคัญสุด)"
echo "  - วันพุธต้องมา 06:00 ไม่ใช่ 06:20"
echo "  - ตรวจว่ายิงจริงไหม:  hermes cron runs"
echo
echo "เก็บกวาดทั้งชุด:  bash scripts/phase1-digests-teardown.sh"
echo
