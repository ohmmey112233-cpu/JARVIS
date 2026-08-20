---
name: jarvis-routines
description: "งานที่ทำเป็นรอบของโอม (ไดโอด คิ้ว ตัดผม) + ศุกร์สลับสัปดาห์จอมทอง/โรงแรม"
version: 0.1.0
author: Jarvis (Ohm)
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [Jarvis, Routines, Thai, Personal]
    related_skills: [jarvis-memory, jarvis-booking]
---

# Routines ของโอม

ติดตามงานที่ทำเป็นรอบ และรู้ว่าศุกร์นี้โอมอยู่เชียงใหม่หรือกลับจอมทอง

## เมื่อไหร่ถึงใช้

- โอมถามว่า "วันนี้มีอะไรถึงรอบไหม" / "อาทิตย์นี้มีอะไรบ้าง"
- โอมบอกว่าทำอะไรไปแล้ว: "ทำคิ้วแล้ว" / "ไดโอดแล้ว" / "ตัดผมแล้ว"
- ตอนประกอบ digest เช้า (ต้องรู้ว่ามี routine ถึงรอบไหม)
- ต้องรู้ว่าศุกร์นี้อยู่ไหน — โดยเฉพาะก่อนจะเสนอจองอะไรคืนศุกร์

## วิธีเรียก

ทุกคำสั่งคืน JSON บรรทัดเดียว `{"ok": true, "data": ...}`

```bash
cd ~/jarvis && PYTHONPATH=jarvis python3 -m cli routines due
cd ~/jarvis && PYTHONPATH=jarvis python3 -m cli routines upcoming --days 7
cd ~/jarvis && PYTHONPATH=jarvis python3 -m cli routines done --name eyebrow
cd ~/jarvis && PYTHONPATH=jarvis python3 -m cli friday state
```

ชื่อ routine ที่มี: `diode` (ไดโอด 14 วัน) · `eyebrow` (คิ้ว 7 วัน) · `haircut` (ตัดผม ทุกอังคาร)

## กติกาตอนตอบ

1. **ตอบสั้น** — "บันทึกแล้วครับ รอบหน้า 24 ส.ค." พอ ไม่ต้องเล่ากระบวนการ
2. **ไม่มีอะไรถึงรอบก็บอกบรรทัดเดียว** ไม่ต้องไล่รายการทั้งหมดให้ดู
3. **วันที่พูดเป็นภาษาไทยแบบสั้น** — "24 ส.ค." ไม่ใช่ "2026-08-24"
4. ถ้าคำสั่งคืน `ok: false` พร้อม error เรื่อง preference ที่ยังไม่ได้กรอก
   → บอกโอมตรงๆ ว่าต้องกรอกค่าไหน **ห้ามเดาค่าแล้วตอบเหมือนรู้**

## ข้อควรระวัง

- `friday state` อ่านค่า `friday_anchor_date` จากฐานข้อมูล ถ้ายังไม่ได้กรอกจะ error
  **อย่าเดาว่าศุกร์นี้อยู่ไหน** — ตอบผิดแปลว่าโอมอาจจองของผิดสัปดาห์
- `routines done` เขียนฐานข้อมูลจริง สั่งเมื่อโอมบอกว่าทำแล้วเท่านั้น ไม่ใช่ตอนถาม
