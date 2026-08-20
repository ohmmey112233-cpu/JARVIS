#!/usr/bin/env bash
# =============================================================================
# Jarvis — กู้คืนจากไฟล์สำรอง (คู่กับ scripts/backup-jarvis.sh)
# =============================================================================
# ใช้ยังไง:
#   bash scripts/restore-jarvis.sh ~/backups/jarvis/jarvis-backup-20260820-033000.tar.gz
#   bash scripts/restore-jarvis.sh <archive> --yes     ไม่ถามยืนยัน (ใช้ตอนซ้อม drill)
#   bash scripts/restore-jarvis.sh <archive> --force   ข้ามการเช็คว่า gateway รันอยู่
#
# หลักการเดียวกับกฎเหล็กข้อ "ลบต้องกู้คืนได้": ของเดิม **ไม่ถูกลบ** —
# ก่อนทับจะย้ายทั้งหมดไปเก็บที่ ~/.jarvis/pre-restore-<timestamp>/ ก่อนเสมอ
# ถ้ากู้แล้วพบว่าเลือกไฟล์ผิดวัน เอาของจากโฟลเดอร์นั้นกลับมาวางคืนได้ทันที
#
# exit code:  0 = สำเร็จ / ผู้ใช้ตอบไม่ยืนยันแล้วยกเลิกเอง
#             1 = เรียกใช้ผิด / หาไฟล์สำรองไม่เจอ
#             2 = gateway ยังรันอยู่ (หยุดก่อน หรือใส่ --force)
#             3 = ไฟล์สำรองแตกไม่ออก / โครงสร้างข้างในไม่ตรงแบบ
#             4 = PRAGMA integrity_check ไม่ผ่าน
#             5 = ต้องการคำยืนยันแต่ไม่ได้รันใน terminal (ใส่ --yes ถ้าตั้งใจจริง)
# =============================================================================
set -euo pipefail

C_OK=$'\033[0;32m'; C_WARN=$'\033[0;33m'; C_ERR=$'\033[0;31m'; C_INFO=$'\033[0;36m'; C_OFF=$'\033[0m'
ok()   { echo "${C_OK}✓${C_OFF} $*"; }
info() { echo "${C_INFO}→${C_OFF} $*"; }
warn() { echo "${C_WARN}⚠${C_OFF} $*"; }
die()  { local code="$1"; shift; echo "${C_ERR}✗${C_OFF} $*" >&2; exit "$code"; }

# --- 0. อ่าน argument ----------------------------------------------------------
ARCHIVE=""; ASSUME_YES=0; FORCE=0
for ARG in "$@"; do
  case "$ARG" in
    --yes)   ASSUME_YES=1 ;;
    --force) FORCE=1 ;;
    -*)      die 1 "ไม่รู้จัก option '$ARG' — ใช้ได้แค่ --yes กับ --force" ;;
    *)       [ -z "$ARCHIVE" ] || die 1 "ให้ไฟล์สำรองมาได้ทีละไฟล์เดียว"
             ARCHIVE="$ARG" ;;
  esac
done
[ -n "$ARCHIVE" ] || die 1 "บอกไฟล์สำรองด้วย:  bash scripts/restore-jarvis.sh <jarvis-backup-*.tar.gz>"
[ -f "$ARCHIVE" ] || die 1 "หาไฟล์ไม่เจอ: $ARCHIVE"

JARVIS_HOME="${JARVIS_HOME:-$HOME/.jarvis}"
DB_PATH="${JARVIS_DB:-$JARVIS_HOME/jarvis.db}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
TS="$(TZ=Asia/Bangkok date +%Y%m%d-%H%M%S)"
PRE_DIR="$JARVIS_HOME/pre-restore-$TS"

command -v python3 >/dev/null 2>&1 || die 1 "ต้องมี python3 เพื่อตรวจ integrity ของ DB"

echo
echo "=============================================="
echo " Jarvis restore — $(basename "$ARCHIVE")"
echo "=============================================="
echo

# --- 1. ห้ามกู้ทับขณะ gateway รันอยู่ ---------------------------------------------
# gateway ถือ connection ของ SQLite ค้างไว้ — สลับไฟล์ DB ใต้จมูกมัน จะได้
# ส่วนผสมของ WAL เก่ากับ DB ใหม่ = ไฟล์เสียแบบเงียบๆ กว่าจะรู้ก็สายไป
HERMES_BIN="${HERMES_BIN:-$HERMES_HOME/hermes-agent/venv/bin/hermes}"
[ -x "$HERMES_BIN" ] || HERMES_BIN="$(command -v hermes 2>/dev/null || true)"
if [ -n "$HERMES_BIN" ] && [ -x "$HERMES_BIN" ]; then
  GW_STATUS="$(timeout 30 "$HERMES_BIN" gateway status 2>&1 || true)"
  if echo "$GW_STATUS" | grep -qiE 'not running|inactive|dead|failed|stopped'; then
    ok "gateway ไม่ได้รันอยู่ — ปลอดภัย"
  elif [ -n "$GW_STATUS" ] && [ "$FORCE" -eq 0 ]; then
    die 2 "gateway ดูเหมือนยังรันอยู่ — หยุดก่อนด้วย: hermes gateway stop
   (หรือถ้ามั่นใจว่าเช็คพลาด ใส่ --force เพื่อข้าม)"
  elif [ "$FORCE" -eq 1 ]; then
    warn "ข้ามการเช็ค gateway เพราะใส่ --force มา — รับความเสี่ยงเอง"
  fi
else
  warn "หา hermes ไม่เจอในเครื่องนี้ — ข้ามการเช็ค gateway"
fi

# --- 2. แตกไฟล์ลง staging ก่อน ยังไม่แตะของจริง -----------------------------------
umask 077
STAGE="$(mktemp -d "${TMPDIR:-/tmp}/jarvis-restore.XXXXXX")"
trap 'rm -rf "$STAGE"' EXIT
info "แตกไฟล์ลง staging ..."
tar -xzf "$ARCHIVE" -C "$STAGE" || die 3 "แตกไฟล์ไม่ออก — ไฟล์เสียหรือไม่ใช่ tar.gz"

TOP="$(find "$STAGE" -mindepth 1 -maxdepth 1 -type d -name 'jarvis-backup-*' | head -n 1)"
[ -n "$TOP" ] || die 3 "ข้างในไม่มีโฟลเดอร์ jarvis-backup-* — ไม่ใช่ไฟล์จาก backup-jarvis.sh"
ok "โครงสร้างไฟล์สำรองถูกต้อง ($(basename "$TOP"))"
[ -f "$TOP/MANIFEST.txt" ] && sed 's/^/    /' "$TOP/MANIFEST.txt" | head -n 6

# --- 3. ตรวจ DB ใน staging ก่อนเอาไปทับของจริง ------------------------------------
# ตรวจตั้งแต่ยังอยู่ staging — ถ้าไฟล์สำรองตัวนี้เสีย ต้องรู้ *ก่อน* ย้ายของจริงออก
HAS_DB=0
if [ -f "$TOP/jarvis.db" ]; then
  HAS_DB=1
  CHECK="$(CHECK_DB="$TOP/jarvis.db" python3 - <<'PY'
import os, sqlite3
con = sqlite3.connect(os.environ["CHECK_DB"])
print(con.execute("PRAGMA integrity_check").fetchone()[0])
con.close()
PY
)"
  [ "$CHECK" = "ok" ] || die 4 "DB ในไฟล์สำรองไม่ผ่าน integrity_check ('$CHECK') — ลองไฟล์สำรองวันอื่น"
  ok "DB ในไฟล์สำรองผ่าน integrity_check"
else
  warn "ไฟล์สำรองนี้ไม่มี jarvis.db (สำรองสมัย Phase 0B?) — จะกู้เฉพาะฝั่ง Hermes"
fi

# --- 4. ให้ยืนยันก่อนทับของจริง ---------------------------------------------------
echo
info "กำลังจะทับของจริงด้วยของจากไฟล์สำรอง:"
[ "$HAS_DB" -eq 1 ]              && echo "    jarvis.db      → $DB_PATH"
[ -d "$TOP/hermes/memories" ]    && echo "    memories/      → $HERMES_HOME/memories"
[ -f "$TOP/hermes/config.yaml" ] && echo "    config.yaml    → $HERMES_HOME/config.yaml"
[ -f "$TOP/hermes/.env" ]        && echo "    .env           → $HERMES_HOME/.env"
[ -d "$TOP/hermes/skills" ]      && echo "    skills/        → $HERMES_HOME/skills"
echo "    ของเดิมทั้งหมดจะถูกย้าย (ไม่ลบ) ไป $PRE_DIR"
echo
if [ "$ASSUME_YES" -eq 0 ]; then
  # รันจาก cron/script โดยไม่มี --yes = ไม่มีใครตอบคำถามได้ ต้องล้มดังๆ
  # ไม่ใช่ค้างรอ input เงียบๆ ทั้งคืน (kit: "การลบ/ทับต้องยืนยันก่อนเสมอ")
  [ -t 0 ] || die 5 "ไม่ได้รันใน terminal และไม่มี --yes — ไม่กู้ทับโดยไม่มีคนยืนยัน"
  read -r -p "พิมพ์ yes เพื่อยืนยันการกู้ทับ: " ANSWER
  if [ "$ANSWER" != "yes" ]; then
    echo
    ok "ยกเลิกแล้ว — ไม่มีไฟล์ไหนถูกแก้"
    exit 0
  fi
fi

# --- 5. ย้ายของเดิมไปเก็บก่อน (ห้ามลบเด็ดขาด) -------------------------------------
mkdir -p "$PRE_DIR/hermes" "$JARVIS_HOME" "$HERMES_HOME"
move_aside() {
  local src="$1" dst="$2"
  [ -e "$src" ] && mv "$src" "$dst"
  return 0
}
if [ "$HAS_DB" -eq 1 ]; then
  move_aside "$DB_PATH" "$PRE_DIR/jarvis.db"
  # -wal/-shm ของ DB เก่าต้องตามไปด้วยกัน — ถ้าทิ้ง -wal เก่าไว้ข้างๆ DB ใหม่
  # SQLite จะพยายาม "กู้" WAL เก่าใส่ DB ใหม่ตอนเปิดครั้งแรก = ข้อมูลปนสองยุค
  move_aside "$DB_PATH-wal" "$PRE_DIR/jarvis.db-wal"
  move_aside "$DB_PATH-shm" "$PRE_DIR/jarvis.db-shm"
fi
[ -d "$TOP/hermes/memories" ]    && move_aside "$HERMES_HOME/memories"    "$PRE_DIR/hermes/memories"
[ -f "$TOP/hermes/config.yaml" ] && move_aside "$HERMES_HOME/config.yaml" "$PRE_DIR/hermes/config.yaml"
[ -f "$TOP/hermes/.env" ]        && move_aside "$HERMES_HOME/.env"        "$PRE_DIR/hermes/.env"
[ -d "$TOP/hermes/skills" ]      && move_aside "$HERMES_HOME/skills"      "$PRE_DIR/hermes/skills"
ok "ย้ายของเดิมไปเก็บที่ $PRE_DIR แล้ว"

# --- 6. วางของจากไฟล์สำรองลงที่จริง ----------------------------------------------
RESTORED=()
if [ "$HAS_DB" -eq 1 ]; then
  cp "$TOP/jarvis.db" "$DB_PATH"
  RESTORED+=("jarvis.db")
fi
if [ -d "$TOP/hermes/memories" ]; then
  cp -a "$TOP/hermes/memories" "$HERMES_HOME/memories"; RESTORED+=("memories/")
fi
if [ -f "$TOP/hermes/config.yaml" ]; then
  cp -a "$TOP/hermes/config.yaml" "$HERMES_HOME/config.yaml"; RESTORED+=("config.yaml")
fi
if [ -f "$TOP/hermes/.env" ]; then
  cp -a "$TOP/hermes/.env" "$HERMES_HOME/.env"
  chmod 600 "$HERMES_HOME/.env"   # กันเหนียวอีกชั้น เผื่อ tar/รูปแบบเก่าไม่เก็บสิทธิ์มา
  RESTORED+=(".env")
fi
if [ -d "$TOP/hermes/skills" ]; then
  cp -a "$TOP/hermes/skills" "$HERMES_HOME/skills"; RESTORED+=("skills/")
fi

# --- 7. ตรวจของจริงหลังวางแล้ว ---------------------------------------------------
# checklist E4: "restore ขึ้นมาแล้วเปิดใช้งานได้จริง ไม่ใช่แค่ไฟล์ดาวน์โหลดมาได้"
# → ต้องเปิด DB ที่ตำแหน่งจริง เช็ค integrity และนับแถวให้ดูกับตา
if [ "$HAS_DB" -eq 1 ]; then
  RESULT="$(CHECK_DB="$DB_PATH" python3 - <<'PY'
import os, sqlite3
con = sqlite3.connect(os.environ["CHECK_DB"])
print("integrity_check:", con.execute("PRAGMA integrity_check").fetchone()[0])
tables = [r[0] for r in con.execute(
    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
for t in tables:
    n = con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    print(f"  {t}: {n} แถว")
con.close()
PY
)"
  echo "$RESULT" | sed 's/^/    /'
  echo "$RESULT" | head -n 1 | grep -q 'integrity_check: ok' \
    || die 4 "DB ที่กู้มาไม่ผ่าน integrity_check — ของเดิมยังอยู่ครบที่ $PRE_DIR เอากลับมาวางคืนได้"
  ok "DB ที่กู้มาเปิดได้จริง (integrity_check = ok)"
fi

echo
echo "=============================================="
ok "restore เสร็จ"
echo "=============================================="
echo
echo "กู้คืนแล้ว: ${RESTORED[*]:-ไม่มีอะไรเลย(?)}"
echo "ของเดิมก่อนกู้: $PRE_DIR  (ไม่ถูกลบ — เก็บไว้จนกว่าจะแน่ใจแล้วค่อยเก็บกวาดเอง)"
echo
echo "ขั้นต่อไป:"
echo "  1. เปิด gateway กลับ:  hermes gateway start"
echo "  2. ทักบอทใน Telegram เช็คว่าความจำ/ข้อมูลกลับมาครบ"
echo "  3. จดวันที่ซ้อม restore ลง docs/backup.md (checklist E4)"
echo
