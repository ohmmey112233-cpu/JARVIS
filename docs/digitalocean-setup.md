# ติดตั้งบน DigitalOcean — ทีละคลิก

คู่มือเฉพาะ DigitalOcean ตั้งแต่ยังไม่มี droplet จนถึงเริ่ม gate trial
ถ้ามี droplet อยู่แล้วให้ข้ามไป[ขั้นที่ 3](#ขั้นที่-3--ssh-เข้า-droplet)

---

## ⛔ อ่านก่อน — ต้องใช้ Droplets ไม่ใช่ App Platform

DigitalOcean มีบริการรันโค้ดหลายตัว ที่ต้องใช้คือ **Droplets** เท่านั้น

ถ้าเผลอเข้าหน้า **Create an app** (App Platform) แล้วเลือก repo นี้ จะเจอ:

> ❗ **No components detected:** Verify the repo contains supported file types, such as `package.json`, `requirements.txt`, or a Dockerfile.

**นี่ไม่ใช่บั๊ก และไม่ต้องไปแก้ repo ให้มีไฟล์พวกนั้น** — repo นี้เป็นชุดสคริปต์ที่ไปติดตั้ง
Hermes ลงบนเครื่อง ไม่ใช่ตัวแอปที่ App Platform จะเอาไป build ได้ App Platform
มองหาแอปที่ build เป็น container ได้ พอไม่เจอก็เลยบอกว่าไม่มี component

ถ้าอยู่หน้านั้นอยู่ ให้ออกมาเลย — ยังไม่ได้สร้างอะไร ยังไม่เสียเงิน

### ทำไม App Platform ใช้กับ Hermes ไม่ได้เลย

| เหตุผล | ผลที่ตามมา |
|---|---|
| **ดิสก์เป็นแบบชั่วคราว** — ทุกครั้งที่ deploy หรือ container รีสตาร์ท ไฟล์ที่เขียนไว้หายหมด | `~/.hermes/` ที่เก็บ SQLite, `MEMORY.md`, `USER.md` และรายการ cron จะถูกล้างทิ้ง — **gate trial ข้อ 3 (คุมความจำ) พังทันที** เพราะสิ่งที่สั่งให้จำหายทุกครั้งที่ระบบรีสตาร์ท |
| ติดตั้งผ่าน installer ลง `$HOME` + venv | ออกแบบมาสำหรับเครื่อง VM ไม่ใช่ build pipeline ของ container |
| gateway คุมทั้งแชทและ cron ในตัวเดียว ต้องรันยาวและใช้ systemd | สคริปต์ `03-start-gateway.sh` ใช้ `hermes gateway install` ซึ่งเป็น systemd service — App Platform ไม่มี systemd ให้ |
| ต้อง SSH เข้าไปดู log และแก้ config | App Platform เข้าถึงเครื่องแบบนั้นไม่ได้ |

Droplet คือเครื่อง Ubuntu จริงที่ SSH เข้าไปได้ ดิสก์อยู่ถาวร มี systemd ครบ — ตรงกับที่ spec เขียนไว้ว่า "Hermes Agent บน VPS"

---

## ขั้นที่ 1 — สร้าง Droplet

เข้า [cloud.digitalocean.com](https://cloud.digitalocean.com) → ปุ่ม **Create** มุมขวาบน → **Droplets**

กรอกตามนี้ทีละช่อง:

### Choose Region
**Singapore** — ใกล้ไทยที่สุด ping ต่ำสุด ราคาเท่ากันทุก region ไม่มีค่าบวกเพิ่ม
Datacenter ย่อยข้างใต้ปล่อยเป็นค่า default

### Choose an image
แท็บ **OS** → **Ubuntu** → เวอร์ชัน **24.04 (LTS) x64**

> อย่าเลือก 25.x — LTS ได้ security update ยาวกว่า และสคริปต์ชุดนี้ทดสอบบน 24.04

### Choose Size
- **Droplet Type:** `Basic`
- **CPU options:** `Regular` (Disk type: SSD) ← ถูกสุด พอสำหรับงานนี้

เลือกขนาด:

| ราคา/เดือน | RAM | vCPU | SSD | เหมาะกับ |
|---|---|---|---|---|
| $4 | 512 MB | 1 | 10 GB | ❌ **อย่าเลือก** — ติดตั้งไม่ผ่านแน่นอน |
| **$6** | **1 GB** | **1** | **25 GB** | ✅ **เลือกอันนี้** — อยู่ในงบ spec ($5-10) ใช้ได้จริงเมื่อมี swap |
| $12 | 2 GB | 1 | 50 GB | ✅ สบายกว่า ไม่ต้องลุ้นตอนติดตั้ง — แต่เกินงบที่ spec ตั้งไว้ |

> ราคาข้างบนคือที่ควรเจอ แต่ **เช็คหน้า [Droplet Pricing](https://www.digitalocean.com/pricing/droplets) อีกทีก่อนกด** เพราะ DigitalOcean ปรับราคาเป็นระยะ (ตั้งแต่ 1 ม.ค. 2026 คิดเงินเป็นรายวินาที ขั้นต่ำ 60 วินาที)
>
> **เลือก $6 ได้เพราะสคริปต์ `00-digitalocean-prep.sh` สร้าง swap 2GB ให้** — DO ไม่ให้ swap มากับ droplet และตัวติดตั้ง Python dependency ของ Hermes คือจุดที่กิน RAM หนักสุด นี่คือสาเหตุอันดับหนึ่งที่คนติดตั้งไม่ผ่านบน droplet 1GB
>
> ขยายทีหลังได้: Droplet → **Resize** → เลือกแบบ *CPU and RAM only* ซึ่ง**ย้อนกลับได้** (ถ้าขยายดิสก์ด้วยจะย้อนไม่ได้)

### Choose Authentication Method
เลือก **SSH Key** (ปลอดภัยกว่าและไม่ต้องพิมพ์รหัสทุกครั้ง)

ยังไม่มี key → กด **New SSH Key** แล้วสร้างจากเครื่องตัวเอง:

```bash
# บน MacBook — เปิด Terminal
ssh-keygen -t ed25519 -C "jarvis-vps"     # กด Enter รวดเดียวได้ทั้ง 3 คำถาม
cat ~/.ssh/id_ed25519.pub                 # คัดลอกทั้งบรรทัดไปวางในช่องของ DO
```

> เลือก **Password** ก็ได้ถ้าจะรีบ แต่ต้องจดรหัสไว้ดีๆ และสคริปต์เตรียมเครื่องจะเตือนให้ตั้งรหัสให้ user `jarvis` เองอีกที

### Advanced / Recommended options
- ✅ ติ๊ก **Add improved metrics monitoring and alerting** — ฟรี และใช้ตั้งแจ้งเตือนได้ว่า RAM ใกล้เต็มหรือ droplet ดับ
- ⬜ Backups — +20% ของค่า droplet (~$1.2/เดือนสำหรับตัว $6) **Phase 0B ยังไม่จำเป็น** ใช้ snapshot ฟรีกว่า (ดู[ท้ายเอกสาร](#snapshot--ประกันชีวิตราคาถูก))

### Finalize Details
- **Quantity:** 1
- **Hostname:** `jarvis` (หรืออะไรก็ได้ ไม่มีผลกับระบบ)

กด **Create Droplet** → รอ ~1 นาที → จดเลข **IP address** ที่ขึ้นมา

---

## ขั้นที่ 2 — ตั้งแจ้งเตือน (ทำเลย 2 นาที คุ้มมาก)

ในหน้า droplet → แท็บ **Monitoring** → **Create alert policy**

ตั้ง 2 อัน:

| แจ้งเตือนเมื่อ | ค่า | ทำไมต้องมี |
|---|---|---|
| Memory utilization | สูงกว่า 90% นาน 5 นาที | รู้ก่อนที่ gateway จะถูก OOM kill |
| Droplet is down | — | รู้ทันทีถ้า droplet ดับ ไม่ต้องมารู้ตอนเช้าที่ digest ไม่มา |

ส่งเข้า email ตัวเอง — ตรงนี้แหละที่ทำให้ gate trial ข้อ 2 (digest 3 เช้าติด) แยกออกว่า "Hermes ห่วย" กับ "droplet ดับ" คนละเรื่องกัน

---

## ขั้นที่ 3 — SSH เข้า droplet

```bash
ssh root@<ip-ที่จดไว้>
```

ครั้งแรกจะถามว่า `Are you sure you want to continue connecting?` → พิมพ์ `yes`

> **ต่อไม่ได้?**
> - `Permission denied (publickey)` → ตอนสร้างเลือก SSH key แต่เครื่องใช้ key คนละอัน ลอง `ssh -i ~/.ssh/id_ed25519 root@<ip>`
> - `Connection refused` → droplet ยังบูตไม่เสร็จ รอ 1 นาทีแล้วลองใหม่
> - ลืมรหัส/ล็อกอินไม่ได้เลย → หน้า droplet มีปุ่ม **Console** ใช้เข้าผ่านเบราว์เซอร์ได้

---

## ขั้นที่ 4 — เตรียมเครื่อง (รันในฐานะ root)

```bash
apt-get update -qq && apt-get install -y -qq git
git clone https://github.com/ohmmey112233-cpu/JARVIS.git /root/jarvis
cd /root/jarvis && git checkout claude/hermes-agent-phase-0b-upmjjr
bash scripts/00-digitalocean-prep.sh
```

ใช้เวลา 2-3 นาที ทำให้ 6 อย่าง:

1. **สร้าง swap 2GB** — DO ไม่ให้มา และ droplet 1GB ต้องใช้ตอนติดตั้ง
2. **ตั้ง timezone เป็น Asia/Bangkok** — droplet ของ DO มาเป็น UTC เสมอ ถ้าไม่แก้ digest จะมาผิดไป 7 ชั่วโมง
3. อัปเดตระบบ + ลง git/curl/ripgrep + เปิดแพตช์ความปลอดภัยอัตโนมัติ
4. **สร้าง user `jarvis`** พร้อมคัดลอก SSH key จาก root มาให้ (Hermes ห้ามติดตั้งด้วย root)
5. **เปิด lingering** — ให้ gateway รันต่อแม้ปิด SSH และหลังรีบูต
6. **เปิด firewall (ufw) รับเข้าเฉพาะ SSH** — Hermes ต่อ Telegram แบบ polling คือต่อออกอย่างเดียว **ไม่ต้องเปิดพอร์ตรับเข้าเลย**

รันซ้ำได้ ถ้าทำไปแล้วจะข้ามเอง

---

## ขั้นที่ 5 — ติดตั้ง Hermes (สลับเป็น user `jarvis`)

```bash
su - jarvis
git clone https://github.com/ohmmey112233-cpu/JARVIS.git ~/jarvis
cd ~/jarvis && git checkout claude/hermes-agent-phase-0b-upmjjr
bash scripts/01-install-hermes.sh
```

⏱ 5-15 นาทีบน droplet $6 — ปล่อยรันไป ไม่ต้องเฝ้า

จากนั้นทำต่อตาม [README.md](../README.md) ขั้นที่ 2 เป็นต้นไป:

```bash
cp config/jarvis.env.example config/jarvis.env
nano config/jarvis.env          # กรอก 3 ค่า: Anthropic key, bot token, user ID
bash scripts/02-configure-jarvis.sh
bash scripts/03-start-gateway.sh
bash scripts/verify-phase0b.sh
bash scripts/gate-trial-setup.sh --smoke
```

> **จบ SSH แล้ว Jarvis ยังรันอยู่ไหม?** รันอยู่ — `00-digitalocean-prep.sh` เปิด lingering ให้แล้ว
> ตรวจเองได้: `loginctl show-user jarvis -p Linger` ต้องได้ `Linger=yes`

---

## ค่าใช้จ่ายจริงต่อเดือน

| รายการ | ราคา |
|---|---|
| Droplet $6 (1GB, Singapore) | ~$6 |
| Monitoring + alerts | ฟรี |
| Bandwidth (1TB มาให้ในตัว) | ฟรี — Jarvis ใช้ไม่ถึง 1GB/เดือน |
| Snapshot 1 อัน (~3GB) | ~$0.18 |
| **รวมฝั่ง DigitalOcean** | **~$6.2** |
| Claude API | $2-10 ขึ้นกับการใช้และโมเดล |
| **รวมทั้งหมด** | **~$8-16/เดือน** |

> บัญชีใหม่มักได้ **Signup Credit $5** — ครอบคลุมค่า droplet เดือนแรกเกือบทั้งเดือน
> เครดิตมีวันหมดอายุ เช็คได้ที่ **Billing** ในเมนูบัญชี

spec ตั้งงบรวมไว้ **$7-20/เดือน** สำหรับ Phase 1-2 → **อยู่ในงบ**

ถ้าค่า API เกิน ให้ลดโมเดลก่อน ไม่ต้องลด droplet:
```bash
hermes config set model.default claude-sonnet-5 && hermes gateway restart
```

---

## Snapshot — ประกันชีวิตราคาถูก

**พอ gate trial ผ่านครบ 3 ข้อ ให้ถ่าย snapshot ทันที** ก่อนจะไปแตะอะไรใน Phase 1

หน้า droplet → **Snapshots** → **Take Snapshot** (ต้องปิด droplet ก่อนถึงจะได้ snapshot ที่สมบูรณ์ที่สุด)

- ราคา ~$0.06 ต่อ GiB ต่อเดือน → ระบบขนาดนี้ตกเดือนละไม่กี่บาท
- ถ้า Phase 1 ทำพัง กด restore กลับมาที่จุดที่ผ่าน gate trial ได้เลย ไม่ต้องติดตั้งใหม่
- ต่างจาก Backups ตรงที่ snapshot ถ่ายเมื่อสั่งเท่านั้น ไม่ได้คิดเงินรายเดือนแบบ +20%

---

## ปัญหาที่เจอเฉพาะบน DigitalOcean

**ติดตั้งแล้วเครื่องค้าง / process โดน kill**
RAM หมด — เช็คว่า swap ติดจริงไหม
```bash
free -h        # บรรทัด Swap ต้องไม่เป็น 0
sudo swapon /swapfile
```

**digest มาตอน 13:20 แทน 06:20**
timezone ยังเป็น UTC (13:20 = 06:20 + 7 ชั่วโมง)
```bash
timedatectl                                     # ต้องเห็น Asia/Bangkok
sudo timedatectl set-timezone Asia/Bangkok
hermes config set timezone Asia/Bangkok
hermes gateway restart
hermes cron list                                # Next run ต้องลงท้าย +07:00
```

**รีบูต droplet แล้ว Jarvis ไม่กลับมา**
```bash
loginctl show-user jarvis -p Linger             # ต้องได้ Linger=yes
sudo loginctl enable-linger jarvis
hermes gateway start
```

**ssh เข้าไม่ได้หลังเปิด firewall**
ไม่ควรเกิด เพราะสคริปต์ `allow OpenSSH` ก่อน `enable` เสมอ แต่ถ้าเกิดจริง — ใช้ปุ่ม **Console** ในหน้า droplet เข้าผ่านเบราว์เซอร์ (ไม่ผ่าน firewall) แล้ว:
```bash
ufw allow OpenSSH && ufw reload
```

**ปัญหาอื่นที่ไม่เกี่ยวกับ DO** → [troubleshooting.md](troubleshooting.md)
