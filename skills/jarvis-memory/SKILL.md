---
name: jarvis-memory
description: "ความจำของ Jarvis — จำ/ดู/แก้/ลืม เรื่องที่โอมสอน พร้อมถังขยะที่กู้คืนได้"
version: 0.1.0
author: Jarvis (Ohm)
license: MIT
platforms: [linux, macos]
metadata:
  hermes:
    tags: [Jarvis, Memory, Thai, Personal]
    related_skills: [jarvis-routines]
---

# ความจำของ Jarvis

เก็บเรื่องที่โอมสอน แล้วเอากลับมาใช้ตอนทำงานที่เกี่ยวข้อง

> ใช้ตารางนี้แทนความจำในตัวของ Hermes เพราะ spec ต้องการ CRUD เต็มรูปแบบ
> (แก้/ลบ/กู้คืนได้ตามสั่ง) และต้องรู้ว่าความจำใหม่ทับอันไหนไป

## 4 คำสั่งที่ต้องรองรับ

| โอมพูดว่า | เรียก |
|---|---|
| "จำไว้ว่า..." | `memory remember` |
| "จำอะไรเกี่ยวกับ X ไว้บ้าง" | `memory recall` |
| "แก้ความจำเรื่อง X เป็น..." | `memory revise` |
| "ลืมเรื่อง X" | `memory forget` (ดูขั้นตอนยืนยันด้านล่าง) |

```bash
cd ~/jarvis && PYTHONPATH=jarvis python3 -m cli memory remember \
    --topic "ร้านกาแฟ" --content "Ristr8to นิมมาน สั่งลาเต้ร้อนไม่หวาน" --tags "cafe,nimman"
cd ~/jarvis && PYTHONPATH=jarvis python3 -m cli memory recall --topic "ร้านกาแฟ"
cd ~/jarvis && PYTHONPATH=jarvis python3 -m cli memory revise --topic "ร้านกาแฟ" --content "..."
cd ~/jarvis && PYTHONPATH=jarvis python3 -m cli memory forget --topic "ร้านกาแฟ"
cd ~/jarvis && PYTHONPATH=jarvis python3 -m cli memory forget --topic "ร้านกาแฟ" --confirm
```

## กติกาบังคับ 3 ข้อ

### 1. ทับของเก่าต้องบอกว่าทับอะไร

`remember` และ `revise` คืน `superseded` มาด้วยถ้ามีของเก่าถูกทับ
**ต้องเอาไปบอกโอมเสมอ** เช่น

> จำแล้วครับ — ทับของเดิมที่ว่า "Ristr8to นิมมาน สั่งลาเต้ร้อนไม่หวาน"

ห้ามจำเงียบๆ แล้วบอกแค่ "จำแล้วครับ" ถ้ามีของเก่าถูกทับ

### 2. ลบต้องยืนยันก่อนเสมอ — สองจังหวะ

```
จังหวะที่ 1  เรียก forget โดย "ไม่ใส่" --confirm
             → ยังไม่ลบ คืนรายการที่จะโดนลบมาให้
             → เอาไปถามโอกว่า "จะลบข้อนี้ใช่ไหมครับ: ..."
จังหวะที่ 2  โอมยืนยัน → เรียกซ้ำพร้อม --confirm → ลบจริง (ย้ายเข้าถังขยะ)
```

**ห้ามใส่ `--confirm` ตั้งแต่ครั้งแรกเด็ดขาด** แม้โอมจะพูดว่า "ลบเลย"
เพราะสั่งลบผิดหัวข้อเกิดขึ้นได้ง่าย และหัวข้อที่ตรงกันอาจมีหลายข้อ

### 3. กู้คืนได้ ให้บอกว่ากู้ได้

ลบแล้วของไปอยู่ถังขยะ ไม่ได้หายจริง ถ้าโอมถามหาให้ใช้ `memory trash`
แล้ว `memory restore --id <original_id>`

## ตอนทำงานอื่น

ก่อนทำงานที่เกี่ยวข้อง (จองร้าน วางแผน ตอบคำถามเรื่องร้าน) ให้ `recall` หัวข้อนั้นก่อนเสมอ
ความจำมีไว้ใช้ ไม่ใช่มีไว้เก็บ
