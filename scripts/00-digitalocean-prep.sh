#!/usr/bin/env bash
# =============================================================================
# Jarvis Phase 0B — ขั้นที่ 0: เตรียม droplet ของ DigitalOcean
# =============================================================================
# DigitalOcean ส่ง droplet มาให้เป็น root เปล่าๆ ไม่มี swap ไม่มี user ธรรมดา
# สคริปต์นี้เตรียมให้ครบก่อนติดตั้ง Hermes
#
# รัน "ในฐานะ root" ทันทีหลังสร้าง droplet เสร็จ:
#   ssh root@<ip-ของ-droplet>
#   curl -fsSL <raw-url-ของไฟล์นี้> -o prep.sh && bash prep.sh
# หรือ clone repo มาก่อนแล้ว:  bash scripts/00-digitalocean-prep.sh
#
# ทำ 6 อย่าง: สร้าง user → swap → timezone → อัปเดตระบบ → firewall → เครื่องมือพื้นฐาน
# รันซ้ำได้ ทุกขั้นตรวจก่อนว่าทำไปแล้วหรือยัง
# =============================================================================
set -euo pipefail

JARVIS_USER="${JARVIS_USER:-jarvis}"
SWAP_SIZE="${SWAP_SIZE:-2G}"

C_OK=$'\033[0;32m'; C_WARN=$'\033[0;33m'; C_ERR=$'\033[0;31m'; C_INFO=$'\033[0;36m'; C_OFF=$'\033[0m'
ok()   { echo "${C_OK}✓${C_OFF} $*"; }
info() { echo "${C_INFO}→${C_OFF} $*"; }
warn() { echo "${C_WARN}⚠${C_OFF} $*"; }
die()  { echo "${C_ERR}✗${C_OFF} $*" >&2; exit 1; }

echo
echo "=============================================="
echo " Jarvis — เตรียม droplet ของ DigitalOcean"
echo "=============================================="
echo

[ "$(id -u)" -eq 0 ] || die "ต้องรันในฐานะ root — droplet ที่เพิ่งสร้างเสร็จจะล็อกอินเป็น root อยู่แล้ว
   ถ้าล็อกอินเป็น user อื่นอยู่ ให้ใช้:  sudo bash $0"

# --- 1. RAM / ดิสก์ ----------------------------------------------------------
MEM_MB=$(awk '/MemTotal/ {printf "%d", $2/1024}' /proc/meminfo)
DISK_GB=$(df -PBG / | awk 'NR==2 {gsub("G","",$4); print $4}')
info "droplet นี้: RAM ${MEM_MB}MB / ดิสก์ว่าง ${DISK_GB}GB"
[ "$DISK_GB" -lt 5 ] && die "ดิสก์ว่าง ${DISK_GB}GB น้อยเกินไป — ต้องมีอย่างน้อย 5GB"

# --- 2. swap -----------------------------------------------------------------
# droplet ของ DO ไม่มี swap มาให้ ตัว 1GB จะ OOM ตอนติดตั้ง dependency ของ Python
# นี่คือสาเหตุอันดับหนึ่งที่ติดตั้ง Hermes ไม่ผ่านบน droplet ราคาถูก
CURRENT_SWAP=$(awk '/SwapTotal/ {printf "%d", $2/1024}' /proc/meminfo)
if [ "$CURRENT_SWAP" -ge 1024 ]; then
  ok "มี swap อยู่แล้ว ${CURRENT_SWAP}MB"
elif [ -f /swapfile ]; then
  warn "มี /swapfile อยู่แล้วแต่ยังไม่ได้เปิดใช้ — กำลังเปิด..."
  swapon /swapfile 2>/dev/null || true
  ok "เปิด swap แล้ว"
else
  if [ "$MEM_MB" -lt 2048 ]; then
    info "สร้าง swap ขนาด $SWAP_SIZE — RAM ${MEM_MB}MB เสี่ยง OOM ตอนติดตั้ง dependency (DO ไม่ให้ swap มาให้)"
  else
    info "สร้าง swap ขนาด $SWAP_SIZE เผื่อไว้ (DO ไม่ให้ swap มาให้ droplet)..."
  fi
  fallocate -l "$SWAP_SIZE" /swapfile || dd if=/dev/zero of=/swapfile bs=1M count=2048 status=none
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  # server ควรใช้ swap เท่าที่จำเป็น ไม่ใช่ swap ตลอดเวลา
  sysctl -q vm.swappiness=10
  grep -q '^vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf
  ok "สร้าง swap $SWAP_SIZE แล้ว (ติดอัตโนมัติหลังรีบูตด้วย)"
fi

# --- 3. timezone (กฎเหล็กข้อ 3) ----------------------------------------------
# droplet ของ DO มาเป็น UTC เสมอ ถ้าไม่แก้ digest จะมาผิดเวลา 7 ชั่วโมง
# อ่าน timezone ปัจจุบันแบบไม่พึ่ง timedatectl อย่างเดียว
# (ในบาง image ที่ไม่มี systemd เป็น PID 1 timedatectl จะใช้ไม่ได้)
current_tz() {
  timedatectl show -p Timezone --value 2>/dev/null \
    || cat /etc/timezone 2>/dev/null \
    || readlink -f /etc/localtime 2>/dev/null | sed 's|.*/zoneinfo/||' \
    || echo unknown
}
if [ "$(current_tz)" = "Asia/Bangkok" ]; then
  ok "timezone = Asia/Bangkok อยู่แล้ว"
else
  info "ตั้ง timezone เป็น Asia/Bangkok (droplet ของ DO มาเป็น UTC เสมอ)..."
  if timedatectl set-timezone Asia/Bangkok 2>/dev/null; then
    ok "timezone = Asia/Bangkok — เวลาตอนนี้ $(date '+%Y-%m-%d %H:%M:%S %Z')"
  elif [ -f /usr/share/zoneinfo/Asia/Bangkok ]; then
    # ทางสำรองเมื่อไม่มี systemd — เขียน /etc/localtime ตรงๆ
    ln -sf /usr/share/zoneinfo/Asia/Bangkok /etc/localtime
    echo "Asia/Bangkok" > /etc/timezone
    ok "timezone = Asia/Bangkok (ตั้งผ่าน /etc/localtime) — เวลาตอนนี้ $(date '+%Y-%m-%d %H:%M:%S %Z')"
  else
    warn "ตั้ง timezone ไม่สำเร็จ — รันเอง: sudo timedatectl set-timezone Asia/Bangkok"
    warn "ไม่ blocking: Hermes ตั้ง timezone ของตัวเองแยกในขั้นที่ 2 อยู่แล้ว"
  fi
fi

# --- 4. อัปเดตระบบ + เครื่องมือที่ต้องใช้ --------------------------------------
info "อัปเดตรายชื่อแพ็กเกจ..."
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
info "ติดตั้งเครื่องมือพื้นฐาน (git, curl, ripgrep, ...)..."
apt-get install -y -qq git curl ca-certificates ripgrep unzip nano >/dev/null
ok "ติดตั้งเครื่องมือพื้นฐานแล้ว"

# แพตช์ความปลอดภัยอัตโนมัติ — VPS ที่เปิดทิ้งไว้ตลอดควรมี
if apt-get install -y -qq unattended-upgrades >/dev/null 2>&1; then
  dpkg-reconfigure -f noninteractive unattended-upgrades >/dev/null 2>&1 || true
  ok "เปิดแพตช์ความปลอดภัยอัตโนมัติแล้ว"
fi

# --- 5. สร้าง user ธรรมดา ------------------------------------------------------
# Hermes ติดตั้งลง $HOME และห้ามรันด้วย root
if id "$JARVIS_USER" >/dev/null 2>&1; then
  ok "มี user '$JARVIS_USER' อยู่แล้ว"
else
  info "สร้าง user '$JARVIS_USER'..."
  adduser --disabled-password --gecos "" "$JARVIS_USER" >/dev/null
  usermod -aG sudo "$JARVIS_USER"
  ok "สร้าง user '$JARVIS_USER' แล้ว (อยู่ในกลุ่ม sudo)"
fi

# คัดลอก SSH key ของ root มาให้ user ใหม่ จะได้ ssh เข้าตรงได้เลย
if [ -f /root/.ssh/authorized_keys ]; then
  USER_SSH="/home/$JARVIS_USER/.ssh"
  mkdir -p "$USER_SSH"
  if [ ! -f "$USER_SSH/authorized_keys" ] || ! cmp -s /root/.ssh/authorized_keys "$USER_SSH/authorized_keys"; then
    cat /root/.ssh/authorized_keys >> "$USER_SSH/authorized_keys"
    sort -u "$USER_SSH/authorized_keys" -o "$USER_SSH/authorized_keys"
  fi
  chmod 700 "$USER_SSH"; chmod 600 "$USER_SSH/authorized_keys"
  chown -R "$JARVIS_USER:$JARVIS_USER" "$USER_SSH"
  ok "คัดลอก SSH key มาให้ '$JARVIS_USER' แล้ว — ssh เข้าตรงได้เลย"
else
  warn "root ไม่มี SSH key (แปลว่าตอนสร้าง droplet เลือกแบบรหัสผ่าน)"
  warn "ตั้งรหัสผ่านให้ '$JARVIS_USER' ด้วยตัวเอง:  passwd $JARVIS_USER"
fi

# ให้ gateway ของ user นี้รันต่อได้แม้ปิด SSH และหลังรีบูต
loginctl enable-linger "$JARVIS_USER" 2>/dev/null \
  && ok "เปิด lingering ให้ '$JARVIS_USER' แล้ว (gateway รันต่อหลังปิด SSH)" \
  || warn "เปิด lingering ไม่สำเร็จ — ค่อยรันทีหลัง: sudo loginctl enable-linger $JARVIS_USER"

# --- 6. firewall -------------------------------------------------------------
# Hermes ต่อ Telegram แบบ polling = ต่อออกอย่างเดียว ไม่ต้องเปิดพอร์ตรับเข้าเลย
# เปิดแค่ SSH พอ
if command -v ufw >/dev/null 2>&1; then
  if ufw status 2>/dev/null | grep -q "Status: active"; then
    ok "firewall (ufw) เปิดอยู่แล้ว"
  else
    info "ตั้ง firewall — เปิดรับเฉพาะ SSH"
    # ลำดับสำคัญมาก: ต้อง allow SSH "ก่อน" enable ไม่งั้นตัดขาตัวเองหลุดจาก droplet
    ufw allow OpenSSH >/dev/null 2>&1 || ufw allow 22/tcp >/dev/null
    ufw --force enable >/dev/null
    ok "เปิด firewall แล้ว (รับเข้าเฉพาะ SSH / ต่อออกได้หมด)"
  fi
  echo
  ufw status numbered 2>/dev/null | head -8 | sed 's/^/    /'
else
  warn "ไม่มี ufw — ข้ามการตั้ง firewall"
fi

# --- สรุป -------------------------------------------------------------------
echo
echo "=============================================="
ok "เตรียม droplet เสร็จแล้ว"
echo "=============================================="
echo
echo "สรุปสภาพเครื่องตอนนี้:"
echo "  RAM        ${MEM_MB}MB + swap $(awk '/SwapTotal/ {printf "%d", $2/1024}' /proc/meminfo)MB"
echo "  timezone   $(current_tz)  ($(date '+%H:%M %Z'))"
echo "  user       $JARVIS_USER"
echo
echo "ขั้นต่อไป — สลับไปเป็น user '$JARVIS_USER' แล้วติดตั้ง Hermes:"
echo
echo "    su - $JARVIS_USER"
echo "    git clone https://github.com/ohmmey112233-cpu/JARVIS.git ~/jarvis"
echo "    cd ~/jarvis && git checkout claude/hermes-agent-phase-0b-upmjjr"
echo "    bash scripts/01-install-hermes.sh"
echo
echo "⚠ อย่าติดตั้ง Hermes ด้วย root — สคริปต์ขั้นที่ 1 จะปฏิเสธให้เอง"
echo
