# แก้ปัญหา — Phase 0B

เรียงตามอาการที่เจอบ่อยที่สุดก่อน ทุกคำสั่งรันบน VPS

---

## บอทไม่ตอบใน Telegram

ไล่ตามลำดับนี้ อย่าข้าม

**1. gateway รันอยู่ไหม**
```bash
hermes gateway status
```
ถ้าขึ้น `Gateway is not running` → `hermes gateway start`

**2. ดู log ว่าพังตรงไหน**
```bash
journalctl --user -u hermes-gateway -n 80 --no-pager
```

**3. user ID เราอยู่ใน allowlist ไหม** ← สาเหตุอันดับ 1
```bash
grep TELEGRAM_ALLOWED_USERS ~/.hermes/.env
```
ต้องเป็น **ตัวเลข** เท่านั้น ถ้าใส่ `@username` ไว้จะกันเราออกจากบอทตัวเอง
ทักหา [@userinfobot](https://t.me/userinfobot) เพื่อดูเลขจริง แล้วแก้:
```bash
nano ~/.hermes/.env      # แก้บรรทัด TELEGRAM_ALLOWED_USERS
hermes gateway restart   # ต้อง restart ทุกครั้งหลังแก้ .env
```

**4. token ยังใช้ได้ไหม**
```bash
curl -s "https://api.telegram.org/bot$(grep '^TELEGRAM_BOT_TOKEN=' ~/.hermes/.env | cut -d= -f2-)/getMe"
```
ได้ `"ok":true` = token ดี / ได้ `"ok":false` = ไปสร้าง token ใหม่ที่ @BotFather

**5. มีบอทตัวเดิมค้างรันอยู่ที่อื่นไหม**
Telegram ยอมให้ต่อ polling ได้ทีละที่เดียว ถ้าเคยรัน `hermes gateway run` ทิ้งไว้ในหน้าจออื่น หรือเคยลองรันบนเครื่องอื่นด้วย token เดียวกัน สองตัวจะแย่งกัน อาการคือตอบบ้างไม่ตอบบ้าง
```bash
pgrep -af "hermes.*gateway"     # ควรเห็นแค่ process เดียว
```

---

## digest เช้าไม่มา

**เช็คว่าเวลาถัดไปถูกไหม**
```bash
hermes cron list
```
`Next run:` ต้องลงท้าย **`+07:00`** ถ้าเป็น `+00:00` แปลว่า timezone ผิด — digest จะมา 7 โมงเช้าแทน 06:20
```bash
hermes config set timezone Asia/Bangkok
hermes gateway restart
```

**เช็คว่า job เคยยิงจริงไหม**
```bash
hermes cron runs        # ประวัติการรันจริง
hermes cron status      # scheduler ทำงานอยู่ไหม
```

**cron ต้องมี gateway รันอยู่ถึงจะยิง** — ถ้า gateway ดับกลางดึก job จะข้ามไปเลย ไม่ยิงย้อนหลัง
สาเหตุที่ gateway ดับหลัง VPS รีบูตคือไม่ได้เปิด lingering:
```bash
loginctl show-user "$USER" -p Linger      # ต้องได้ Linger=yes
sudo loginctl enable-linger "$USER"
```

---

## บอทตอบว่าเรียกโมเดลไม่ได้ / 401 / credit

```bash
bash scripts/verify-phase0b.sh      # ข้อ 5 จะยิง API จริงไปเช็คให้
```

- **401** → key ผิดหรือถูกเพิกถอน สร้างใหม่ที่ [console.anthropic.com](https://console.anthropic.com) แล้ว `hermes gateway restart`
- **credit หมด / 400 about credit** → เติมเงินที่ Console → Billing
- **404 model not found** → ชื่อโมเดลผิด ดูรายชื่อที่บัญชีเข้าถึงได้:
  ```bash
  curl -s -H "x-api-key: $(grep '^ANTHROPIC_API_KEY=' ~/.hermes/.env | cut -d= -f2-)" \
       -H "anthropic-version: 2023-06-01" https://api.anthropic.com/v1/models | grep -o '"id":"[^"]*"'
  ```

---

## ค่า API แพงกว่าที่คิด

ดูยอดใช้จริง: พิมพ์ `/usage` ในแชท Telegram หรือดูที่ Console → Usage

ลดค่าใช้จ่ายจากมากไปน้อย:

1. **เปลี่ยนโมเดลหลัก** — opus-5 ($5/$25 ต่อ 1M token) → sonnet-5 ($3/$15)
   ```bash
   hermes config set model.default claude-sonnet-5 && hermes gateway restart
   ```
2. **เริ่ม session ใหม่บ่อยๆ** — พิมพ์ `/new` ในแชท บทสนทนายาวคือค่าใช้จ่ายที่โตขึ้นทุกข้อความ เพราะต้องส่งประวัติทั้งหมดไปใหม่ทุกครั้ง
3. **ลด cron job ที่ไม่จำเป็น** — ทุกครั้งที่ job ยิง = เรียกโมเดลหนึ่งรอบเต็ม

---

## ติดตั้งไม่ผ่าน

**`No space left on device`**
```bash
df -h ~                    # ต้องเหลืออย่างน้อย 3GB
uv cache clean             # ล้าง cache ของ uv
rm -rf ~/.cache/pip
```

**RAM ไม่พอ (VPS 1GB ตอนติดตั้ง dependency)** — เปิด swap ชั่วคราว
```bash
sudo fallocate -l 2G /swapfile && sudo chmod 600 /swapfile
sudo mkswap /swapfile && sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab   # ให้ติดหลังรีบูตด้วย
```

**`ModuleNotFoundError: No module named 'dotenv'`**
กำลังเรียก `hermes` ผิดตัว — ต้องเรียกตัวใน venv
```bash
~/.hermes/hermes-agent/venv/bin/hermes doctor
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
```

**`hermes: command not found` หลังติดตั้งเสร็จ**
```bash
source ~/.bashrc
```

---

## อัปเดตแล้วพัง

เวอร์ชันที่ผ่านการทดสอบถูกบันทึกไว้ที่:
```bash
cat ~/.hermes/jarvis-version.lock
```

`updates.pre_update_backup` ถูกเปิดไว้แล้วตั้งแต่ติดตั้ง ดังนั้นทุกครั้งที่ `hermes update` จะมี zip สำรองไว้ให้:
```bash
ls -lt ~/.hermes/backups/ | head
hermes import ~/.hermes/backups/<ไฟล์ที่ต้องการ>.zip
```

หรือย้อนกลับไปที่ commit เดิมตรงๆ:
```bash
cd ~/.hermes/hermes-agent
git checkout $(grep '^hermes_commit=' ~/.hermes/jarvis-version.lock | cut -d= -f2)
UV_NO_CONFIG=1 VIRTUAL_ENV="$PWD/venv" uv pip install -e ".[anthropic,messaging]"
hermes gateway restart
```

> **อย่าอัปเดตระหว่าง gate trial 3 วัน** ถ้าอัปเดตกลางคันแล้วผลเปลี่ยน จะแยกไม่ออกว่าเป็นเพราะ Hermes หรือเพราะการอัปเดต

---

## รีเซ็ตทั้งหมด เริ่มใหม่

```bash
hermes gateway stop
hermes gateway uninstall
mv ~/.hermes ~/.hermes.bak-$(date +%Y%m%d-%H%M)   # ย้ายเก็บไว้ ไม่ลบทิ้ง
```
แล้วเริ่มจาก `scripts/01-install-hermes.sh` ใหม่ ค่าลับใน `config/jarvis.env` ยังอยู่ ไม่ต้องหา token ใหม่
