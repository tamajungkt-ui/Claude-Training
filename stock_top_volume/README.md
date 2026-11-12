# หุ้น Volume สูงสุด 10 อันดับรายวัน

เครื่องมือรวบรวมว่าแต่ละวัน **หุ้นตัวไหนมีปริมาณการซื้อขาย (Volume) สูงสุด 10 อันดับ, Volume เท่าไหร่**
แล้วสร้างรายงานสำหรับผู้บริหาร โดยให้ AI (Claude) เขียนบทสรุปได้

## ทำงานอย่างไร

```
แหล่งข้อมูล (Yahoo Finance / CSV จากโบรกเกอร์-SETSMART)
      ↓
จัดอันดับ Volume สูงสุด 10 ตัว + มูลค่าโดยประมาณ + เทียบค่าเฉลี่ย 5 วัน
      ↓
AI เขียนบทสรุปผู้บริหาร (เลือกได้)
      ↓
reports/YYYY-MM-DD.md, .csv และ reports/history.csv (สะสมทุกวัน)
```

GitHub Actions (`.github/workflows/daily-top-volume.yml`) รันอัตโนมัติ จันทร์–ศุกร์ 17:40 น.
หลังตลาดปิด แล้ว commit รายงานเข้า repo

## วิธีใช้

```bash
pip install -r requirements.txt
python top_volume.py --source yahoo                    # ดึงข้อมูลวันล่าสุด
python top_volume.py --source yahoo --date 2026-11-12  # ระบุวัน
python top_volume.py --source yahoo --ai               # + บทสรุปจาก AI (ต้องมี ANTHROPIC_API_KEY)
python top_volume.py --source csv --csv sample_data/sample_daily.csv   # ทดลองด้วยข้อมูลตัวอย่าง (สมมติ)
```

- ปรับรายชื่อหุ้นที่ติดตามได้ที่ `symbols_set100.txt`
- เปิดใช้ AI ใน GitHub Actions: เพิ่ม secret `ANTHROPIC_API_KEY` ที่ Settings → Secrets and variables → Actions

## ข้อควรรู้

- **"ยอดซื้อ" กับ Volume**: ทุกการซื้อขายต้องจับคู่ ฝั่งซื้อ = ฝั่งขาย Volume จึงเท่ากับยอดซื้อ
  ถ้าต้องการแยก "ใครซื้อ" (ต่างชาติ / สถาบัน / รายย่อย) ตลาดฯ เปิดเผยระดับทั้งตลาดเท่านั้น
  ไม่ได้แยกรายหุ้น
- **Yahoo Finance** ฟรีแต่ไม่เป็นทางการ และครอบคลุมเฉพาะหุ้นในรายชื่อ ถ้าต้องการข้อมูลทั้งตลาด
  ให้ใช้ข้อมูลทางการ (SETSMART / SET Market Data API / โบรกเกอร์) export เป็น CSV
  ที่มีคอลัมน์ `symbol, volume, close` แล้วใช้ `--source csv`
- รายงานเป็นข้อมูลประกอบการตัดสินใจ ไม่ใช่คำแนะนำการลงทุน
