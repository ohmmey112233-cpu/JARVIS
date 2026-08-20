# เช็คลิสต์ตอน MacBook มาถึง — ทำตามลำดับนี้

> เปิดไฟล์นี้ไว้ข้างๆ แล้วติ๊กไปทีละข้อ ทั้งหมดใช้เวลาราว **45-60 นาที**
> (ส่วนใหญ่คือรอสมัครบัญชีกับรอติดตั้ง — เวลาที่ต้องนั่งพิมพ์จริงๆ ไม่ถึง 15 นาที)

---

## ⓪ ก่อนอื่น — เรื่องที่ต้องเคลียร์กับที่บ้าน (H2)

- [ ] ตกลงแล้วว่าใครเป็นคนเปิดบัญชีและใช้บัตรใคร

ทุกเจ้า (DigitalOcean / Anthropic / Google Cloud) กำหนดให้ผู้เปิดบัญชีบรรลุนิติภาวะ
ถ้าเปิดในชื่อผู้ปกครอง **บิลและความรับผิดชอบทางกฎหมายเป็นของท่าน** — red team บอกให้
คุยให้จบก่อนจ่ายบาทแรก ไม่ใช่หลังจ่ายไปแล้ว

---

## ① สมัคร 3 อย่างที่ต้องมีก่อน gate trial

### [ ] 1.1 Anthropic API key — สมองของ Jarvis
1. เข้า [console.anthropic.com](https://console.anthropic.com)
2. Settings → API Keys → **Create Key** → คัดลอกเก็บทันที (ปิดหน้าต่างแล้วดูซ้ำไม่ได้)
3. Billing → เติมเครดิต (เริ่มที่ $5-10 พอสำหรับ gate trial)

### [ ] 1.2 Telegram bot token
1. เปิด Telegram หา [@BotFather](https://t.me/BotFather) → `/newbot`
2. ตั้งชื่อที่แสดง (อะไรก็ได้) → ตั้ง username **ลงท้ายด้วย `bot`**
3. คัดลอก token หน้าตา `123456789:ABCdef...`

### [ ] 1.3 Telegram user ID ของตัวเอง
1. ทักหา [@userinfobot](https://t.me/userinfobot) → มันตอบเลขมาให้ทันที
2. ⚠️ ต้องเป็น **ตัวเลข** ไม่ใช่ `@username` — ใส่ผิดจะกันตัวเองออกจากบอทตัวเอง

---

## ② สร้าง Droplet

- [ ] เข้า [cloud.digitalocean.com](https://cloud.digitalocean.com) → **Create → Droplets**
- [ ] Region **Singapore** · Ubuntu **24.04 LTS** · Basic → Regular SSD → **$6/เดือน (1GB)**
- [ ] Authentication: **SSH Key** → สร้างจาก Mac ก่อน:
      `ssh-keygen -t ed25519 -C "jarvis-vps"` แล้ว `cat ~/.ssh/id_ed25519.pub` ไปวาง
- [ ] ติ๊ก **Add improved metrics monitoring and alerting** (ฟรี)
- [ ] จด **IP address** ที่ได้

> ⛔ ต้องเป็น **Droplets** ห้ามใช้ App Platform — เหตุผลเต็มใน `docs/digitalocean-setup.md`

---

## ③ ติดตั้ง (คัดลอกวางทีละก้อน)

**เป็น root:**
```bash
ssh root@<IP-ที่จด>
apt-get update -qq && apt-get install -y -qq git
git clone https://github.com/ohmmey112233-cpu/JARVIS.git /root/jarvis
cd /root/jarvis && git checkout claude/hermes-agent-phase-0b-upmjjr
bash scripts/00-digitalocean-prep.sh
```

**เป็น user `jarvis`:**
```bash
su - jarvis
git clone https://github.com/ohmmey112233-cpu/JARVIS.git ~/jarvis
cd ~/jarvis && git checkout claude/hermes-agent-phase-0b-upmjjr
bash scripts/01-install-hermes.sh            # 5-15 นาที ปล่อยรันไป
cp config/jarvis.env.example config/jarvis.env
nano config/jarvis.env                        # กรอก 3 ค่าจากข้อ ①
bash scripts/02-configure-jarvis.sh
bash scripts/03-start-gateway.sh
bash scripts/verify-phase0b.sh                # ต้องไม่มี ✗ เหลือ
```

- [ ] ทักบอทใน Telegram พิมพ์ "สวัสดี" → ตอบไทยกลับมา

---

## ④ Gate trial 3 วัน

```bash
bash scripts/gate-trial-setup.sh --smoke
```

- [ ] ข้อความทดสอบมาถึงใน 3 นาที (ถ้าไม่มา อย่าเพิ่งเริ่มนับวัน — แก้ให้จบก่อน)
- [ ] ทำตาม `docs/gate-trial.md` ครบ 3 ข้อ แล้วกรอกผลในเอกสาร
- [ ] ตัดสิน **Track A** (ใช้ Hermes ต่อ) หรือ **Track B**

---

## ⑤ ผ่านแล้วค่อยทำ — เปิด Phase 1 เต็มรูปแบบ

### [ ] 5.1 สมัคร API เสริม digest
| อะไร | ที่ไหน | ถ้าไม่มี |
|---|---|---|
| `GOOGLE_MAPS_API_KEY` | Google Cloud Console → เปิด **Distance Matrix API** + ผูก billing | ไม่มีบรรทัด 🚗 |
| `LONGDO_API_KEY` | [map.longdo.com](https://map.longdo.com) → สมัครฟรี | ไม่มีบรรทัด 🌤️ |
| Air4Thai | — | ✅ ไม่ต้องใช้ key ทำงานเลย |

ใส่ลง `~/.hermes/.env` แล้ว `hermes gateway restart`

### [ ] 5.2 กรอกพิกัดหอกับโรงเรียน
```sql
-- เปิด Google Maps → คลิกขวาที่จุด → คัดลอกพิกัด
UPDATE preferences SET value='LAT,LNG' WHERE key='dorm_latlng';
UPDATE preferences SET value='LAT,LNG' WHERE key='school_latlng';
```
(พิกัดบ้านจอมทองกรอกให้แล้ว)

### [ ] 5.3 เปิด digest จริง + backup
```bash
bash scripts/phase1-digests-setup.sh     # digest เช้า/เย็น/สัปดาห์/ความฝัน
```
- [ ] ตั้ง backup ตาม `docs/backup.md` (รวมตั้ง `RCLONE_REMOTE` ไปที่ Cloudflare R2)
- [ ] **ซ้อม restore จริง 1 ครั้ง** แล้วจดวันที่ไว้ (checklist E4)

### [ ] 5.4 ถ่าย snapshot ของ droplet
พอทุกอย่างนิ่ง → หน้า droplet → Snapshots → Take Snapshot
ราคาเดือนละไม่กี่บาท แต่ถ้าพังทีหลังกดกลับมาได้เลย

---

## ⑥ อย่าเพิ่งทำ

Twilio / Vapi / Botnoi (Phase 3) · LINE OA (Phase 2) · scaccouting OAuth (Phase 2) ·
Home Assistant (Phase 5)

**ก่อนแตะ Phase 3 ให้ทำ H3 ก่อน:** โทรจองร้านที่ไปบ่อย 10 ร้านด้วยตัวเอง
นับว่ากี่ร้านรับจองทางโทรศัพท์จริง — **ต่ำกว่าครึ่ง = ไม่คุ้มสร้าง**

---

## เกณฑ์สุดท้ายที่ตัดสินทุกอย่าง

ใช้จริง 1 เดือน แล้วตอบคำถามเดียว: **เปิดอ่าน digest เช้ากี่วันจาก 30 วัน?**

≥25 ไปต่อ Phase 2 · 10-24 แก้เนื้อหาก่อน · <10 หยุด (ประหยัดเงินหลักหมื่นและเวลาช่วง TCAS)
