#!/usr/bin/env bash
# =============================================================================
# Jarvis Phase 1 — backup ทุกคืน (spec v3 §3: "Backup บังคับ ตั้งแต่ Phase 1")
# =============================================================================
# เก็บอะไรบ้าง:
#   ~/.jarvis/jarvis.db     snapshot ผ่าน sqlite backup API — ห้าม cp ตรงๆ (ดูข้อ 3)
#   ~/.hermes/memories/     ความจำอิสระของ Hermes (MEMORY.md, USER.md, ...)
#   ~/.hermes/config.yaml   ค่า config ทั้งหมด (timezone, model, cron, ...)
#   ~/.hermes/.env          ค่าลับ — คงสิทธิ์ 600 ไว้ทั้งในและนอกไฟล์สำรอง
#   ~/.hermes/skills/       custom skill ของ Jarvis (ถ้าติดตั้งแล้ว)
#
# ใช้ยังไง:
#   bash scripts/backup-jarvis.sh                      # ลง ~/backups/jarvis/
#   BACKUP_DIR=/mnt/x bash scripts/backup-jarvis.sh    # เปลี่ยนที่เก็บ
#
# ตั้งเป็น cron ทุกคืน 03:30 + ตั้ง RCLONE_REMOTE + วิธี restore → docs/backup.md
# สคริปต์นี้ idempotent — รันซ้ำได้ ไฟล์เก่าไม่โดนทับ (ชื่อไฟล์มี timestamp)
#
# exit code:  0 = สำเร็จ (รวมกรณีสำเร็จแต่ยังไม่ได้ตั้ง off-VPS — มีคำเตือนดัง)
#             1 = ไม่มีอะไรให้สำรอง / ไม่มี jarvis.db
#             2 = snapshot DB ไม่สำเร็จ หรือ integrity check ไม่ผ่าน
#             3 = อัดไฟล์ tar ไม่สำเร็จ
#             4 = ตั้ง RCLONE_REMOTE ไว้แต่อัปโหลดออกนอกเครื่องไม่สำเร็จ
#                 (ไฟล์สำรองบนเครื่องยังอยู่ครบ — แต่ cron ต้องเห็นว่า "แดง")
# =============================================================================
set -euo pipefail

C_OK=$'\033[0;32m'; C_WARN=$'\033[0;33m'; C_ERR=$'\033[0;31m'; C_INFO=$'\033[0;36m'; C_OFF=$'\033[0m'
ok()   { echo "${C_OK}✓${C_OFF} $*"; }
info() { echo "${C_INFO}→${C_OFF} $*"; }
warn() { echo "${C_WARN}⚠${C_OFF} $*"; }
die()  { local code="$1"; shift; echo "${C_ERR}✗${C_OFF} $*" >&2; exit "$code"; }

# --- 0. อ่าน config เสริม -----------------------------------------------------
# cron รันด้วย environment แทบว่างเปล่า — RCLONE_REMOTE ที่ export ไว้ใน shell
# ปกติจะไม่ติดมาด้วย เลยให้อ่านจากไฟล์นี้แทน (ดูวิธีสร้างใน docs/backup.md)
# ค่าที่ตั้งมากับ env ตอนเรียกตรงๆ ชนะค่าในไฟล์ เพื่อให้เทสต์ override ได้
_ENV_RCLONE="${RCLONE_REMOTE:-}"; _ENV_BACKUP_DIR="${BACKUP_DIR:-}"; _ENV_KEEP="${BACKUP_KEEP:-}"
BACKUP_ENV="${BACKUP_ENV:-$HOME/.jarvis/backup.env}"
if [ -f "$BACKUP_ENV" ]; then
  set -a
  # shellcheck disable=SC1090
  . "$BACKUP_ENV"
  set +a
fi
[ -n "$_ENV_RCLONE" ]     && RCLONE_REMOTE="$_ENV_RCLONE"
[ -n "$_ENV_BACKUP_DIR" ] && BACKUP_DIR="$_ENV_BACKUP_DIR"
[ -n "$_ENV_KEEP" ]       && BACKUP_KEEP="$_ENV_KEEP"

# --- 1. เส้นทางไฟล์ทั้งหมด ------------------------------------------------------
JARVIS_HOME="${JARVIS_HOME:-$HOME/.jarvis}"
DB_PATH="${JARVIS_DB:-$JARVIS_HOME/jarvis.db}"       # ตรงกับ core/db.py connect()
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
BACKUP_DIR="${BACKUP_DIR:-$HOME/backups/jarvis}"
KEEP="${BACKUP_KEEP:-14}"                            # spec ขอ ≥7 วัน — เก็บ 14 เผื่อไว้

# timestamp ต้องเป็นเวลาไทยเสมอ ไม่ใช่เวลาเครื่อง (กฎเหล็กเรื่องเวลาของโปรเจกต์:
# VPS อาจตั้ง UTC — ถ้าใช้เวลาเครื่อง ชื่อไฟล์จะเหลื่อม 7 ชม. เทียบกับบันทึกอื่น)
# BACKUP_TIMESTAMP มีไว้ให้เทสต์ฉีดเวลา เหมือน `when` param ในโค้ด Python
TS="${BACKUP_TIMESTAMP:-$(TZ=Asia/Bangkok date +%Y%m%d-%H%M%S)}"
case "$TS" in
  [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]-[0-9][0-9][0-9][0-9][0-9][0-9]) ;;
  *) die 1 "BACKUP_TIMESTAMP ต้องเป็นรูปแบบ YYYYMMDD-HHMMSS ได้มา: '$TS'" ;;
esac

ARCHIVE_NAME="jarvis-backup-$TS.tar.gz"
ARCHIVE="$BACKUP_DIR/$ARCHIVE_NAME"

echo
echo "=============================================="
echo " Jarvis backup — $TS (เวลาไทย)"
echo "=============================================="
echo

# --- 2. ตรวจว่ามีอะไรให้สำรองบ้าง ------------------------------------------------
# jarvis.db เป็นหัวใจของ Phase 1 — ถ้าหายไป = ระบบผิดปกติ ต้องล้มดังๆ ให้ cron เห็น
# ไม่ใช่สำรองไฟล์ที่เหลือแล้วรายงานว่า "เรียบร้อย" (บุคลิก: ห้ามรายงานเรียบร้อย
# ถ้ายังไม่สำเร็จจริง) — ยกเว้นช่วง Phase 0B ที่ยังไม่มี DB ให้ตั้ง BACKUP_ALLOW_NO_DB=1
HAS_DB=0
[ -f "$DB_PATH" ] && HAS_DB=1
if [ "$HAS_DB" -eq 0 ]; then
  if [ "${BACKUP_ALLOW_NO_DB:-0}" = "1" ]; then
    warn "ไม่พบ $DB_PATH — สำรองเฉพาะฝั่ง Hermes (BACKUP_ALLOW_NO_DB=1)"
  else
    die 1 "ไม่พบ $DB_PATH — ถ้ายังอยู่ Phase 0B (ไม่มี DB จริง) ให้รันด้วย BACKUP_ALLOW_NO_DB=1"
  fi
fi
if [ "$HAS_DB" -eq 0 ] && [ ! -d "$HERMES_HOME/memories" ] && [ ! -f "$HERMES_HOME/config.yaml" ]; then
  die 1 "ไม่พบทั้ง jarvis.db และข้อมูล Hermes — ไม่มีอะไรให้สำรองเลย ตรวจ HOME ให้ถูกก่อน"
fi

# --- 3. เตรียมโฟลเดอร์ staging --------------------------------------------------
# โฟลเดอร์สำรองต้องเป็น 700 และไฟล์สำรองต้องเป็น 600 เพราะข้างในมี .env
# ที่เก็บ API key ทั้งหมด — ไฟล์สำรองที่ world-readable = ค่าลับรั่วทางอ้อม
umask 077
mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

STAGE_PARENT="$(mktemp -d "${TMPDIR:-/tmp}/jarvis-backup.XXXXXX")"
trap 'rm -rf "$STAGE_PARENT"' EXIT
STAGE="$STAGE_PARENT/jarvis-backup-$TS"
mkdir -p "$STAGE/hermes"

# --- 4. snapshot ฐานข้อมูล ------------------------------------------------------
# ทำไมห้าม `cp jarvis.db` ตรงๆ: DB เปิด WAL mode (schema/001_init.sql) —
# ข้อมูลที่ commit แล้วส่วนหนึ่งยังอยู่ในไฟล์ jarvis.db-wal รอ checkpoint
# cp เอาเฉพาะไฟล์หลัก = ได้ DB ย้อนยุค (แถวล่าสุดหาย) และถ้า gateway กำลังเขียน
# อยู่พอดี อาจได้ไฟล์ครึ่งๆ กลางๆ ที่เปิดไม่ขึ้นเลย — sqlite backup API ทำ
# snapshot แบบ transaction-consistent รวมของใน WAL ให้ครบในไฟล์เดียว
if [ "$HAS_DB" -eq 1 ]; then
  SNAP="$STAGE/jarvis.db"
  if command -v sqlite3 >/dev/null 2>&1; then
    info "snapshot DB ด้วย sqlite3 .backup ..."
    sqlite3 "$DB_PATH" ".backup '$SNAP'" || die 2 "sqlite3 .backup ล้มเหลว"
  elif command -v python3 >/dev/null 2>&1; then
    info "ไม่มี sqlite3 CLI — snapshot DB ด้วย python3 backup API ..."
    SRC_DB="$DB_PATH" DST_DB="$SNAP" python3 - <<'PY' || die 2 "python3 sqlite3 backup ล้มเหลว"
import os, sqlite3
src = sqlite3.connect(os.environ["SRC_DB"])
dst = sqlite3.connect(os.environ["DST_DB"])
with dst:
    src.backup(dst)   # อ่านแบบ online ได้ ไม่ล็อกคนเขียนค้างไว้
dst.close(); src.close()
PY
  else
    die 2 "ไม่มีทั้ง sqlite3 และ python3 — snapshot DB แบบปลอดภัยไม่ได้"
  fi

  # ตรวจของที่เพิ่ง snapshot ทันที — สำรองไฟล์เสียไป 14 วัน = ไม่มีสำรองเลย 14 วัน
  if command -v python3 >/dev/null 2>&1; then
    CHECK="$(CHECK_DB="$SNAP" python3 - <<'PY'
import os, sqlite3
con = sqlite3.connect(os.environ["CHECK_DB"])
print(con.execute("PRAGMA integrity_check").fetchone()[0])
con.close()
PY
)"
  else
    CHECK="$(sqlite3 "$SNAP" 'PRAGMA integrity_check;')"
  fi
  [ "$CHECK" = "ok" ] || die 2 "integrity_check ของ snapshot ได้ '$CHECK' — DB ต้นทางอาจเสีย ตรวจด่วน"
  ok "snapshot jarvis.db แล้ว (integrity_check = ok)"
fi

# --- 5. เก็บฝั่ง Hermes --------------------------------------------------------
# cp -a เพื่อคงสิทธิ์ไฟล์เดิม — สำคัญที่สุดกับ .env (600) เพราะตอน restore
# จะได้กลับมาเป็น 600 เหมือนเดิม ไม่กลายเป็นไฟล์อ่านได้ทั้งเครื่อง
copy_if_exists() {
  local src="$1" dst="$2" label="$3"
  if [ -e "$src" ]; then
    cp -a "$src" "$dst"
    ok "เก็บ $label"
  else
    warn "ไม่พบ $label ($src) — ข้าม"
  fi
}
copy_if_exists "$HERMES_HOME/memories"    "$STAGE/hermes/memories"    "ความจำ Hermes (memories/)"
copy_if_exists "$HERMES_HOME/config.yaml" "$STAGE/hermes/config.yaml" "config.yaml"
copy_if_exists "$HERMES_HOME/.env"        "$STAGE/hermes/.env"        "ค่าลับ .env"
copy_if_exists "$HERMES_HOME/skills"      "$STAGE/hermes/skills"      "custom skills"

# --- 6. เขียน manifest ----------------------------------------------------------
# ไว้ให้ตอน restore (หรือคนเปิดไฟล์สำรองในอนาคต) รู้ว่าก้อนนี้มาจากไหน เมื่อไหร่
# และไฟล์ DB ต้องมี checksum เท่าไหร่ — เทียบได้ว่าไฟล์เสียหายระหว่างทางไหม
{
  echo "jarvis backup manifest"
  echo "created_at_bangkok: $TS"
  echo "hostname: $(hostname 2>/dev/null || echo unknown)"
  echo "source_db: $DB_PATH"
  echo "source_hermes: $HERMES_HOME"
  if [ "$HAS_DB" -eq 1 ] && command -v sha256sum >/dev/null 2>&1; then
    echo "jarvis.db_sha256: $(sha256sum "$STAGE/jarvis.db" | cut -d' ' -f1)"
  fi
  echo "contents:"
  (cd "$STAGE" && find . -type f | sort | sed 's/^/  /')
} > "$STAGE/MANIFEST.txt"

# --- 7. อัดเป็น tar.gz ----------------------------------------------------------
info "อัดไฟล์ $ARCHIVE_NAME ..."
tar -czf "$ARCHIVE" -C "$STAGE_PARENT" "jarvis-backup-$TS" || die 3 "อัด tar ไม่สำเร็จ"
chmod 600 "$ARCHIVE"
# เปิดอ่านสารบัญกลับมาหนึ่งรอบ — กันกรณีดิสก์เต็มแล้วได้ tar ครึ่งไฟล์
tar -tzf "$ARCHIVE" >/dev/null || die 3 "ไฟล์ tar ที่ได้เปิดอ่านไม่ขึ้น (ดิสก์เต็ม?)"
SIZE="$(du -h "$ARCHIVE" | cut -f1)"
ok "ได้ไฟล์สำรอง $ARCHIVE ($SIZE)"

# --- 8. ส่งออกนอกเครื่อง (ข้อบังคับของ spec — ห้ามแกล้งทำเป็นผ่าน) ------------------
UPLOAD_RC=0
if [ -n "${RCLONE_REMOTE:-}" ]; then
  if command -v rclone >/dev/null 2>&1; then
    info "อัปโหลดออกนอกเครื่อง → $RCLONE_REMOTE ..."
    if rclone copy "$ARCHIVE" "$RCLONE_REMOTE" 2>&1 | sed 's/^/    /'; then
      ok "อัปโหลดขึ้น $RCLONE_REMOTE แล้ว"
    else
      UPLOAD_RC=4
      warn "อัปโหลดไม่สำเร็จ — ไฟล์บนเครื่องยังอยู่ครบ ลองรันซ้ำหรือเช็ค rclone config"
    fi
  else
    UPLOAD_RC=4
    warn "ตั้ง RCLONE_REMOTE ไว้แต่ไม่มีคำสั่ง rclone ในเครื่อง — ติดตั้งตาม docs/backup.md"
  fi
else
  # spec v3 §3 บังคับเก็บนอก VPS — ยังไม่ตั้ง = ยังไม่ผ่านข้อบังคับ ต้องตะโกนไว้
  # ห้ามพิมพ์เบาๆ แล้วปล่อยผ่าน เดี๋ยววันที่ VPS พังจะไม่เหลืออะไรเลย
  warn "══════════════════════════════════════════════════════════"
  warn " สำรองอยู่บนเครื่องนี้เครื่องเดียว — ยังไม่ตรง spec (ต้อง off-VPS)"
  warn " ถ้า VPS พัง/โดนลบ/โดนยึด ไฟล์สำรองหายพร้อมกันทั้งหมด"
  warn " ตั้ง RCLONE_REMOTE ใน ~/.jarvis/backup.env ตาม docs/backup.md"
  warn "══════════════════════════════════════════════════════════"
fi

# --- 9. ลบไฟล์สำรองเก่าเกินโควตา -------------------------------------------------
# จับเฉพาะชื่อที่ตรง pattern ของเราเป๊ะๆ (เลข 8 หลัก ขีด เลข 6 หลัก) —
# ไฟล์อื่นที่โอมเอามาวางในโฟลเดอร์เดียวกันต้องไม่โดนลูกหลง
mapfile -t ARCHIVES < <(
  find "$BACKUP_DIR" -maxdepth 1 -type f -name 'jarvis-backup-*.tar.gz' 2>/dev/null \
    | grep -E '/jarvis-backup-[0-9]{8}-[0-9]{6}\.tar\.gz$' \
    | sort || true
)
TOTAL="${#ARCHIVES[@]}"
if [ "$TOTAL" -gt "$KEEP" ]; then
  # ชื่อไฟล์ขึ้นต้นด้วย timestamp → เรียงตามชื่อ = เรียงตามเวลา ตัวแรกสุดคือเก่าสุด
  for OLD in "${ARCHIVES[@]:0:$((TOTAL - KEEP))}"; do
    rm -f -- "$OLD"
    info "ลบสำรองเก่า: $(basename "$OLD")"
  done
  ok "เหลือไฟล์สำรองบนเครื่อง $KEEP ชุดล่าสุด"
else
  ok "ไฟล์สำรองบนเครื่องมี $TOTAL ชุด (เก็บสูงสุด $KEEP)"
fi

echo
echo "=============================================="
if [ "$UPLOAD_RC" -eq 0 ]; then
  ok "backup เสร็จ — $ARCHIVE_NAME"
else
  warn "backup ได้ไฟล์แล้ว แต่ยังไม่ได้ขึ้น off-VPS (exit $UPLOAD_RC)"
fi
echo "=============================================="
echo
echo "อย่าลืม: backup ที่ไม่เคยทดสอบ restore ถือว่ายังไม่มี backup (checklist E4)"
echo "วิธีซ้อม restore → docs/backup.md"
echo
exit "$UPLOAD_RC"
