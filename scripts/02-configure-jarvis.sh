#!/usr/bin/env bash
# =============================================================================
# Jarvis Phase 0B — ขั้นที่ 2: ตั้ง Claude เป็นโมเดลหลัก + ต่อ Telegram
# =============================================================================
# ต้องรัน scripts/01-install-hermes.sh ให้เสร็จก่อน
# และต้องกรอก config/jarvis.env ให้ครบก่อนรันอันนี้
#
#   cp config/jarvis.env.example config/jarvis.env && nano config/jarvis.env
#   bash scripts/02-configure-jarvis.sh
#
# สคริปต์นี้ idempotent — รันซ้ำได้ ค่าเดิมจะถูกอัปเดตทับ ไม่ซ้อนกัน
# =============================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_SRC="${JARVIS_ENV_FILE:-$REPO_DIR/config/jarvis.env}"
HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_ENV="$HERMES_HOME/.env"
HERMES_BIN="${HERMES_BIN:-$HERMES_HOME/hermes-agent/venv/bin/hermes}"

C_OK=$'\033[0;32m'; C_WARN=$'\033[0;33m'; C_ERR=$'\033[0;31m'; C_INFO=$'\033[0;36m'; C_OFF=$'\033[0m'
ok()   { echo "${C_OK}✓${C_OFF} $*"; }
info() { echo "${C_INFO}→${C_OFF} $*"; }
warn() { echo "${C_WARN}⚠${C_OFF} $*"; }
die()  { echo "${C_ERR}✗${C_OFF} $*" >&2; exit 1; }

echo
echo "=============================================="
echo " Jarvis Phase 0B — ตั้งค่า Claude + Telegram"
echo "=============================================="
echo

[ -x "$HERMES_BIN" ] || HERMES_BIN="$(command -v hermes 2>/dev/null || true)"
[ -n "$HERMES_BIN" ] && [ -x "$HERMES_BIN" ] || die "หา hermes ไม่เจอ — รัน scripts/01-install-hermes.sh ก่อน"
ok "ใช้ hermes: $HERMES_BIN"

# --- 1. อ่านค่าลับ ------------------------------------------------------------
[ -f "$ENV_SRC" ] || die "ไม่มีไฟล์ $ENV_SRC
   สร้างก่อน:  cp config/jarvis.env.example config/jarvis.env && nano config/jarvis.env"

# อ่านแบบ source เพื่อรองรับค่าที่มีอักขระพิเศษ แต่ไม่ให้ค่าเก่าใน shell มา override
set -a
# shellcheck disable=SC1090
. "$ENV_SRC"
set +a

MODEL="${JARVIS_MODEL:-claude-opus-5}"
TZ_NAME="${JARVIS_TIMEZONE:-Asia/Bangkok}"

# --- 2. ตรวจว่าค่าจำเป็นครบไหม -----------------------------------------------
PROBLEMS=0
check_required() {
  local name="$1" val="$2" hint="$3"
  if [ -z "$val" ]; then
    echo "${C_ERR}✗${C_OFF} ยังไม่ได้กรอก $name — $hint"
    PROBLEMS=$((PROBLEMS+1))
  fi
}
check_required "ANTHROPIC_API_KEY"      "${ANTHROPIC_API_KEY:-}"      "หาที่ console.anthropic.com → API Keys"
check_required "TELEGRAM_BOT_TOKEN"     "${TELEGRAM_BOT_TOKEN:-}"     "หาจาก @BotFather ด้วยคำสั่ง /newbot"
check_required "TELEGRAM_ALLOWED_USERS" "${TELEGRAM_ALLOWED_USERS:-}" "ทักหา @userinfobot เพื่อดู user ID (เป็นตัวเลข)"
[ "$PROBLEMS" -gt 0 ] && die "กรอก config/jarvis.env ให้ครบก่อน แล้วรันใหม่"

# ตรวจรูปแบบคร่าวๆ ตั้งแต่ตอนนี้ ดีกว่าไปพังตอน gateway start
case "${ANTHROPIC_API_KEY}" in
  sk-ant-*) ok "รูปแบบ ANTHROPIC_API_KEY ถูกต้อง" ;;
  *) warn "ANTHROPIC_API_KEY ปกติขึ้นต้นด้วย 'sk-ant-' — ตรวจอีกทีว่าคัดลอกครบไหม" ;;
esac
case "${TELEGRAM_BOT_TOKEN}" in
  [0-9]*:*) ok "รูปแบบ TELEGRAM_BOT_TOKEN ถูกต้อง" ;;
  *) warn "TELEGRAM_BOT_TOKEN ปกติเป็นแบบ '123456789:ABCdef...' — ตรวจอีกที" ;;
esac
if echo "$TELEGRAM_ALLOWED_USERS" | grep -qE '^[0-9]+(,[0-9]+)*$'; then
  ok "รูปแบบ TELEGRAM_ALLOWED_USERS ถูกต้อง"
else
  die "TELEGRAM_ALLOWED_USERS ต้องเป็นตัวเลขล้วน (คั่นด้วยคอมมาถ้ามีหลายคน)
   ที่กรอกมา: '$TELEGRAM_ALLOWED_USERS'
   ถ้าใส่ @username มา จะกันคนอื่นไม่ได้ — ทักหา @userinfobot เพื่อดูเลข ID จริง"
fi

# --- 3. เขียนค่าลับลง ~/.hermes/.env -----------------------------------------
mkdir -p "$HERMES_HOME"
touch "$HERMES_ENV"
chmod 600 "$HERMES_ENV"

# upsert: มีคีย์อยู่แล้ว = แทนที่บรรทัดเดิม / ยังไม่มี = ต่อท้าย
# ใช้ python เพราะ token/key มีอักขระที่ทำ sed พังได้ง่าย
upsert_env() {
  KEY="$1" VALUE="$2" ENVFILE="$HERMES_ENV" python3 - <<'PY'
import os
key, value, path = os.environ["KEY"], os.environ["VALUE"], os.environ["ENVFILE"]
try:
    lines = open(path, encoding="utf-8").read().splitlines()
except FileNotFoundError:
    lines = []
out, replaced = [], False
for line in lines:
    stripped = line.lstrip()
    # แทนที่ทั้งบรรทัดที่ตั้งค่าอยู่ และบรรทัดที่ถูก comment ทิ้งไว้
    if stripped.startswith(f"{key}=") or stripped.startswith(f"# {key}=") or stripped.startswith(f"#{key}="):
        if not replaced:
            out.append(f"{key}={value}")
            replaced = True
        continue
    out.append(line)
if not replaced:
    out.append(f"{key}={value}")
with open(path, "w", encoding="utf-8") as fh:
    fh.write("\n".join(out).rstrip("\n") + "\n")
PY
}

info "เขียนค่าลับลง $HERMES_ENV ..."
upsert_env ANTHROPIC_API_KEY      "$ANTHROPIC_API_KEY"
upsert_env TELEGRAM_BOT_TOKEN     "$TELEGRAM_BOT_TOKEN"
upsert_env TELEGRAM_ALLOWED_USERS "$TELEGRAM_ALLOWED_USERS"
chmod 600 "$HERMES_ENV"
ok "เขียนค่าลับเรียบร้อย (สิทธิ์ไฟล์ 600 — อ่านได้เฉพาะเจ้าของ)"

# --- 4. ตั้ง config.yaml ------------------------------------------------------
info "ตั้ง timezone = $TZ_NAME (กฎเหล็กข้อ 3)..."
"$HERMES_BIN" config set timezone "$TZ_NAME" >/dev/null
ok "timezone = $TZ_NAME"

info "ตั้ง Claude เป็นโมเดลหลัก..."
"$HERMES_BIN" config set model.provider anthropic >/dev/null
"$HERMES_BIN" config set model.default  "$MODEL"  >/dev/null
ok "provider = anthropic (ยิงตรง Anthropic API ไม่ผ่านคนกลาง)"
ok "โมเดลหลัก = $MODEL"

# aux model: ปล่อยว่าง = Hermes เลือก claude-haiku-4-5 ให้เองเมื่อ provider=anthropic
if [ -n "${JARVIS_AUX_MODEL:-}" ]; then
  "$HERMES_BIN" config set auxiliary.model "$JARVIS_AUX_MODEL" >/dev/null 2>&1 \
    && ok "โมเดลผู้ช่วย = $JARVIS_AUX_MODEL" \
    || warn "ตั้ง auxiliary.model ไม่สำเร็จ — ปล่อยให้ Hermes เลือก Haiku เองแทน"
else
  ok "โมเดลผู้ช่วย = claude-haiku-4-5 (Hermes เลือกให้อัตโนมัติเมื่อ provider=anthropic)"
fi

# ปิดการส่ง metrics ออกนอกเครื่อง — ระบบนี้เก็บเรื่องส่วนตัว
"$HERMES_BIN" config set telemetry.shared_metrics.enabled false >/dev/null 2>&1 \
  && ok "ปิดการส่ง metrics ออกนอกเครื่องแล้ว" || true

echo
echo "=============================================="
ok "ขั้นที่ 2 เสร็จ — ตั้งค่าครบแล้ว"
echo "=============================================="
echo
echo "ค่าที่ตั้งไว้:"
echo "  timezone       $("$HERMES_BIN" config get timezone 2>/dev/null | tail -1)"
echo "  provider       $("$HERMES_BIN" config get model.provider 2>/dev/null | tail -1)"
echo "  โมเดลหลัก       $("$HERMES_BIN" config get model.default 2>/dev/null | tail -1)"
echo
echo "ขั้นต่อไป:  bash scripts/03-start-gateway.sh"
echo
