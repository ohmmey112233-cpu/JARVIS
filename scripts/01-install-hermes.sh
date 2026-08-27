#!/usr/bin/env bash
# =============================================================================
# Jarvis Phase 0B — ขั้นที่ 1: ติดตั้ง Hermes Agent บน VPS
# =============================================================================
# รันบน VPS (Ubuntu/Debian) ด้วย user ธรรมดา (ไม่ใช่ root):
#   bash scripts/01-install-hermes.sh
#
# สคริปต์นี้ idempotent — รันซ้ำได้ ถ้าติดตั้งแล้วจะข้ามไปตรวจสอบอย่างเดียว
# =============================================================================
set -euo pipefail

HERMES_HOME="${HERMES_HOME:-$HOME/.hermes}"
HERMES_SRC="$HERMES_HOME/hermes-agent"
HERMES_BIN="$HERMES_SRC/venv/bin/hermes"
VERSION_LOCK="$HERMES_HOME/jarvis-version.lock"
REPO_URL="https://github.com/NousResearch/hermes-agent.git"

# installer ของ Hermes วาง uv ไว้ที่ ~/.local/bin ซึ่ง PATH จะมีก็ต่อเมื่อ shell
# ได้ source ~/.profile — shell แบบ non-interactive (`ssh host 'bash script.sh'`,
# cron, systemd) ไม่ได้ source จึงหา uv ไม่เจอ และขั้นตอนติดตั้ง extras ข้างล่าง
# ล้มด้วย "uv: command not found" ทั้งที่ uv ติดตั้งอยู่แล้ว
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

C_OK=$'\033[0;32m'; C_WARN=$'\033[0;33m'; C_ERR=$'\033[0;31m'; C_INFO=$'\033[0;36m'; C_OFF=$'\033[0m'
ok()   { echo "${C_OK}✓${C_OFF} $*"; }
info() { echo "${C_INFO}→${C_OFF} $*"; }
warn() { echo "${C_WARN}⚠${C_OFF} $*"; }
die()  { echo "${C_ERR}✗${C_OFF} $*" >&2; exit 1; }

echo
echo "=============================================="
echo " Jarvis Phase 0B — ติดตั้ง Hermes Agent"
echo "=============================================="
echo

# --- 0. ตรวจสภาพเครื่องก่อน --------------------------------------------------
[ "$(id -u)" -eq 0 ] && die "อย่ารันด้วย root — Hermes ติดตั้งลง \$HOME ของ user ธรรมดา
   สร้าง user ก่อน:  sudo adduser jarvis && sudo usermod -aG sudo jarvis && su - jarvis"

info "ตรวจ RAM และพื้นที่ดิสก์..."
MEM_MB=$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo 2>/dev/null || echo 0)
DISK_MB=$(df -Pm "$HOME" | awk 'NR==2 {print $4}')
[ "$MEM_MB" -lt 900 ] && warn "RAM ${MEM_MB}MB — ต่ำกว่า 1GB อาจติดตั้งไม่ผ่าน (แนะนำเปิด swap 2GB)"
[ "$DISK_MB" -lt 3000 ] && die "พื้นที่ว่างเหลือ ${DISK_MB}MB — Hermes ต้องการอย่างน้อย 3GB"
ok "RAM ${MEM_MB}MB / ดิสก์ว่าง ${DISK_MB}MB"

# --- 1. ตั้งนาฬิกาเครื่องเป็นเวลาไทย ------------------------------------------
# กฎเหล็กข้อ 3: ทุกอย่างที่ถามว่า "วันนี้วันไหน" ต้องเป็น Asia/Bangkok
# ตั้งที่ระดับ OS ด้วย เพื่อให้ log/systemd timer ตรงกับที่ Hermes เห็น
CURRENT_TZ=$(timedatectl show -p Timezone --value 2>/dev/null || echo "unknown")
if [ "$CURRENT_TZ" != "Asia/Bangkok" ]; then
  info "ตั้ง timezone ของ VPS เป็น Asia/Bangkok (เดิม: $CURRENT_TZ)..."
  if sudo -n timedatectl set-timezone Asia/Bangkok 2>/dev/null; then
    ok "timezone ของ OS = Asia/Bangkok"
  else
    warn "ตั้ง timezone ของ OS ไม่ได้ (ไม่มีสิทธิ์ sudo แบบไม่ถามรหัส)"
    warn "รันเองทีหลัง:  sudo timedatectl set-timezone Asia/Bangkok"
    warn "ไม่ blocking — Hermes ตั้ง timezone ของตัวเองแยกในขั้นที่ 2 อยู่แล้ว"
  fi
else
  ok "timezone ของ OS = Asia/Bangkok อยู่แล้ว"
fi

# --- 2. ติดตั้ง Hermes -------------------------------------------------------
if [ -x "$HERMES_BIN" ]; then
  ok "พบ Hermes ติดตั้งอยู่แล้วที่ $HERMES_SRC — ข้ามการติดตั้ง"
else
  info "ติดตั้ง Hermes Agent (ใช้เวลา 5-15 นาที ขึ้นกับความเร็ว VPS)..."
  echo
  # ช่องทางหลัก: installer ทางการ — จัดการ uv, Python 3.11, Node, ripgrep, ffmpeg ให้ครบ
  # --skip-browser: Phase 0B ไม่ใช้ browser automation จึงข้าม Chromium (~400MB) ไปก่อน
  #                 เปิดทีหลังได้ด้วย: npx playwright install chromium
  if curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-browser; then
    ok "ติดตั้งผ่าน installer ทางการสำเร็จ"
  else
    warn "installer ทางการล้มเหลว — เปลี่ยนไปติดตั้งจาก source แทน"
    command -v git >/dev/null || die "ไม่มี git — ติดตั้งก่อน: sudo apt install -y git curl"
    if [ ! -d "$HERMES_SRC/.git" ]; then
      mkdir -p "$HERMES_HOME"
      git clone "$REPO_URL" "$HERMES_SRC"
    fi
    # ลง ripgrep ไว้ก่อน: setup-hermes.sh จะถามเรื่องนี้แบบ interactive
    # ถ้ามี rg อยู่แล้วมันจะข้ามคำถามไปเลย (Hermes ใช้ rg ค้นไฟล์เร็วกว่า grep ด้วย)
    if ! command -v rg >/dev/null 2>&1; then
      sudo -n apt-get install -y ripgrep >/dev/null 2>&1 || true
    fi
    # setup-hermes.sh มี `read -p` 2 จุด และใช้ set -e อยู่ ถ้าป้อน /dev/null เข้าไป
    # read จะคืนค่า non-zero แล้วสคริปต์ตายกลางคัน "ก่อน" ถึงขั้นสร้าง symlink
    # จึงป้อน n ให้มันแทน — ตอบไม่ทั้งสองคำถาม แต่ read สำเร็จ สคริปต์ไปต่อจนจบ
    ( cd "$HERMES_SRC" && printf 'n\nn\n' | ./setup-hermes.sh ) || warn "setup-hermes.sh จบแบบมี error — ตรวจต่อด้านล่างว่าใช้ได้ไหม"
    ok "ติดตั้งจาก source เสร็จ"
  fi
fi

# --- 3. หา binary ให้เจอ -----------------------------------------------------
if [ ! -x "$HERMES_BIN" ]; then
  HERMES_BIN="$(command -v hermes 2>/dev/null || echo "$HOME/.local/bin/hermes")"
fi
[ -x "$HERMES_BIN" ] || die "ติดตั้งเสร็จแต่หา binary 'hermes' ไม่เจอ — ลอง: source ~/.bashrc && which hermes"
ok "hermes binary: $HERMES_BIN"

# สร้าง symlink เองถ้ายังไม่มี — ทางติดตั้งแบบ fallback อาจข้ามขั้นนี้ไป
if [ ! -e "$HOME/.local/bin/hermes" ]; then
  mkdir -p "$HOME/.local/bin"
  ln -sf "$HERMES_BIN" "$HOME/.local/bin/hermes"
  ok "สร้าง symlink ~/.local/bin/hermes แล้ว"
fi

# ให้ hermes เรียกได้จากทุก shell
if ! grep -q '.local/bin' "$HOME/.bashrc" 2>/dev/null; then
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
  info "เพิ่ม ~/.local/bin เข้า PATH ใน ~/.bashrc แล้ว (เปิด shell ใหม่หรือ source ~/.bashrc)"
fi

# --- 4. ตรวจว่า dependency ที่ Jarvis ต้องใช้ครบไหม ---------------------------
# provider=anthropic ต้องมี anthropic SDK / Telegram ต้องมี python-telegram-bot
# installer ทางการลง .[all] ให้อยู่แล้ว แต่ถ้าลงแบบ lean มาต้องเติมเอง
VENV_PY="$HERMES_SRC/venv/bin/python"
if [ -x "$VENV_PY" ]; then
  MISSING=""
  "$VENV_PY" -c 'import anthropic' 2>/dev/null || MISSING="$MISSING anthropic"
  "$VENV_PY" -c 'import telegram'  2>/dev/null || MISSING="$MISSING messaging"
  if [ -n "$MISSING" ]; then
    warn "ขาด extras:$MISSING — กำลังติดตั้งเพิ่ม..."
    # venv ที่ uv สร้างไม่มี pip ติดมาด้วย ทางสำรองเดิมจึงพังเสมอด้วย
    # "No module named pip" — ต้อง ensurepip ก่อนถึงจะเป็นทางสำรองได้จริง
    ( cd "$HERMES_SRC" && UV_NO_CONFIG=1 VIRTUAL_ENV="$HERMES_SRC/venv" \
        uv pip install -e ".[anthropic,messaging]" ) \
      || { "$VENV_PY" -m ensurepip --upgrade >/dev/null 2>&1 || true
           "$VENV_PY" -m pip install -e "${HERMES_SRC}[anthropic,messaging]"; } \
      || die "ติดตั้ง extras ไม่สำเร็จ — ต้องมี anthropic + python-telegram-bot ก่อนไปขั้นที่ 2
   ถ้าขึ้น 'uv: command not found' แปลว่า uv ไม่อยู่ใน PATH — ลอง:
     export PATH=\"\$HOME/.local/bin:\$PATH\" && bash scripts/01-install-hermes.sh"
    ok "ติดตั้ง extras เพิ่มเรียบร้อย"
  else
    ok "dependency ครบ (anthropic SDK + python-telegram-bot)"
  fi
fi

# --- 5. บันทึกเวอร์ชันที่ติดตั้ง (pin ไว้กันอัปเดตแล้วพัง) ---------------------
# ความเสี่ยงข้อ 1 ใน spec: Hermes ยังใหม่ อัปเดตอาจพัง config
INSTALLED_VER="$("$HERMES_BIN" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || echo 'unknown')"
INSTALLED_SHA="$(git -C "$HERMES_SRC" rev-parse HEAD 2>/dev/null || echo 'unknown')"
{
  echo "# Jarvis Phase 0B — เวอร์ชัน Hermes ที่ผ่านการทดสอบ (อย่าอัปเดตระหว่าง gate trial)"
  echo "installed_at=$(date -Iseconds)"
  echo "hermes_version=$INSTALLED_VER"
  echo "hermes_commit=$INSTALLED_SHA"
} > "$VERSION_LOCK"
ok "บันทึกเวอร์ชัน $INSTALLED_VER ($(echo "$INSTALLED_SHA" | cut -c1-8)) ลง $VERSION_LOCK"

# เปิด backup อัตโนมัติก่อน update ทุกครั้ง — กันอัปเดตแล้วพังกู้ไม่ได้
"$HERMES_BIN" config set updates.pre_update_backup true >/dev/null 2>&1 \
  && ok "เปิด backup อัตโนมัติก่อน hermes update แล้ว" \
  || warn "ตั้ง updates.pre_update_backup ไม่สำเร็จ (ไม่ blocking)"

echo
echo "=============================================="
ok "ขั้นที่ 1 เสร็จ — Hermes ติดตั้งแล้ว"
echo "=============================================="
echo
echo "ขั้นต่อไป: ตั้งค่า Claude + Telegram"
echo
echo "  1) เตรียมค่า 3 อย่าง (ดูวิธีหาใน README.md ส่วน 'ขั้นที่ 2'):"
echo "       - ANTHROPIC_API_KEY   จาก console.anthropic.com"
echo "       - TELEGRAM_BOT_TOKEN  จาก @BotFather"
echo "       - TELEGRAM_USER_ID    จาก @userinfobot"
echo
echo "  2) คัดลอกไฟล์ตัวอย่างแล้วกรอกค่า:"
echo "       cp config/jarvis.env.example config/jarvis.env"
echo "       nano config/jarvis.env"
echo
echo "  3) รัน:  bash scripts/02-configure-jarvis.sh"
echo
