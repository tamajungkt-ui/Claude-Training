"""
รวบรวมหุ้นที่มีปริมาณการซื้อขาย (Volume) สูงสุด 10 อันดับในแต่ละวัน
แล้วสร้างรายงานสรุปสำหรับผู้บริหาร (ภาษาไทย) — มีตัวเลือกให้ AI (Claude) เขียนบทสรุป

แหล่งข้อมูล:
  --source yahoo : ดึงจาก Yahoo Finance (ฟรี, ใช้ชื่อหุ้นจาก symbols_set100.txt + ".BK")
  --source csv   : อ่านไฟล์ CSV ที่ export จากโบรกเกอร์/SETSMART (คอลัมน์ symbol, volume, close)

ตัวอย่าง:
  python top_volume.py --source yahoo
  python top_volume.py --source csv --csv sample_data/sample_daily.csv --date 2026-11-12
  python top_volume.py --source yahoo --ai        # ให้ Claude เขียนบทสรุปผู้บริหาร
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
REPORT_DIR = HERE / "reports"
HISTORY_FILE = REPORT_DIR / "history.csv"


# ---------------------------------------------------------------- data sources
def load_symbols(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return [s.strip().upper() for s in lines if s.strip() and not s.startswith("#")]


def fetch_yahoo(symbols: list[str], date: dt.date | None) -> tuple[pd.DataFrame, dt.date]:
    """ดึงราคาปิดและ volume รายวันของหุ้นไทยจาก Yahoo Finance"""
    import yfinance as yf

    tickers = [f"{s}.BK" for s in symbols]
    raw = yf.download(tickers, period="10d", group_by="ticker",
                      auto_adjust=False, progress=False, threads=True)
    if raw.empty:
        sys.exit("ดึงข้อมูลจาก Yahoo Finance ไม่ได้ (ตรวจสอบอินเทอร์เน็ต)")

    rows = []
    for sym, tk in zip(symbols, tickers):
        if tk not in raw.columns.get_level_values(0):
            continue
        df = raw[tk].dropna(subset=["Close", "Volume"])
        df = df[df["Volume"] > 0]
        if df.empty:
            continue
        df.index = pd.to_datetime(df.index).date
        for d, r in df.iterrows():
            rows.append({"date": d, "symbol": sym,
                         "volume": int(r["Volume"]), "close": float(r["Close"])})
    data = pd.DataFrame(rows)
    if data.empty:
        sys.exit("ไม่พบข้อมูลการซื้อขาย")

    # ใช้วันที่ระบุ หรือวันทำการล่าสุดที่มีข้อมูล
    target = date or max(data["date"])
    prev_days = sorted(d for d in data["date"].unique() if d < target)
    day = data[data["date"] == target].copy()
    if day.empty:
        sys.exit(f"ไม่มีข้อมูลวันที่ {target} (อาจเป็นวันหยุดตลาด)")

    # เทียบ volume กับค่าเฉลี่ย 5 วันก่อนหน้า เพื่อดูว่า "ผิดปกติ" แค่ไหน
    if prev_days:
        hist = data[data["date"].isin(prev_days[-5:])]
        avg = hist.groupby("symbol")["volume"].mean().rename("avg_volume_5d")
        day = day.merge(avg, on="symbol", how="left")
    return day.drop(columns="date"), target


def load_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    df.columns = [c.strip().lower() for c in df.columns]
    missing = {"symbol", "volume", "close"} - set(df.columns)
    if missing:
        sys.exit(f"ไฟล์ CSV ขาดคอลัมน์: {', '.join(sorted(missing))}")
    df["symbol"] = df["symbol"].str.upper().str.strip()
    return df


# ---------------------------------------------------------------- ranking
def rank_top(df: pd.DataFrame, n: int) -> pd.DataFrame:
    df = df.copy()
    df["value_mb"] = df["volume"] * df["close"] / 1_000_000  # มูลค่าซื้อขายโดยประมาณ (ล้านบาท)
    if "avg_volume_5d" in df.columns:
        df["vs_avg_5d"] = df["volume"] / df["avg_volume_5d"]
    top = df.sort_values("volume", ascending=False).head(n).reset_index(drop=True)
    top.insert(0, "rank", range(1, len(top) + 1))
    return top


# ---------------------------------------------------------------- reports
def to_markdown(top: pd.DataFrame, date: dt.date, n: int) -> str:
    has_avg = "vs_avg_5d" in top.columns
    head = "| อันดับ | หุ้น | Volume (หุ้น) | ราคาปิด (บาท) | มูลค่าโดยประมาณ (ล้านบาท) |"
    sep = "|---:|---|---:|---:|---:|"
    if has_avg:
        head += " เทียบค่าเฉลี่ย 5 วัน |"
        sep += "---:|"
    lines = [f"# หุ้น Volume สูงสุด {n} อันดับ — {date:%d/%m/%Y}", "", head, sep]
    for r in top.itertuples():
        line = (f"| {r.rank} | **{r.symbol}** | {r.volume:,.0f} | {r.close:,.2f} "
                f"| {r.value_mb:,.1f} |")
        if has_avg:
            line += " - |" if pd.isna(r.vs_avg_5d) else f" {r.vs_avg_5d:.1f} เท่า |"
        lines.append(line)
    total = top["volume"].sum()
    lines += ["", f"รวม Volume ของ {n} อันดับ: **{total:,.0f} หุ้น** "
                  f"(มูลค่าโดยประมาณ {top['value_mb'].sum():,.1f} ล้านบาท)",
              "", "> หมายเหตุ: Volume คือจำนวนหุ้นที่จับคู่ซื้อขายได้ (ฝั่งซื้อ = ฝั่งขาย) "
                  "มูลค่าคำนวณจาก Volume × ราคาปิด จึงเป็นค่าประมาณ"]
    return "\n".join(lines) + "\n"


def ai_summary(table_md: str) -> str:
    """ให้ Claude เขียนบทสรุปผู้บริหาร (ต้องตั้งค่า ANTHROPIC_API_KEY)"""
    import anthropic

    client = anthropic.Anthropic()
    response = client.beta.messages.create(
        model="claude-opus-5-5",
        max_tokens=4000,
        output_config={"effort": "low"},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",  # ถ้าโมเดลหลักปฏิเสธ ให้โมเดลสำรองตอบแทน
        system=("คุณเป็นนักวิเคราะห์ที่เขียนสรุปให้ผู้บริหาร ตอบเป็นภาษาไทย กระชับ "
                "ใช้เฉพาะข้อมูลในตาราง ห้ามแต่งตัวเลขหรือข่าวเพิ่ม และไม่ให้คำแนะนำซื้อขาย"),
        messages=[{"role": "user", "content":
                   "สรุปตารางหุ้น Volume สูงสุดวันนี้เป็น bullet 3-5 ข้อ: หุ้นเด่น, "
                   "หุ้นที่ volume ผิดปกติเทียบค่าเฉลี่ย (ถ้ามี), ข้อสังเกตเรื่องมูลค่าซื้อขาย\n\n"
                   + table_md}],
    )
    if response.stop_reason == "refusal":
        return "_(AI ไม่สามารถสรุปได้ในรอบนี้)_"
    return "".join(b.text for b in response.content if b.type == "text").strip()


def save(top: pd.DataFrame, md: str, date: dt.date) -> Path:
    REPORT_DIR.mkdir(exist_ok=True)
    top.to_csv(REPORT_DIR / f"{date}.csv", index=False, encoding="utf-8-sig")
    md_path = REPORT_DIR / f"{date}.md"
    md_path.write_text(md, encoding="utf-8")

    hist = top.assign(date=str(date))[["date", "rank", "symbol", "volume", "close", "value_mb"]]
    if HISTORY_FILE.exists():
        old = pd.read_csv(HISTORY_FILE)
        hist = pd.concat([old[old["date"] != str(date)], hist], ignore_index=True)
    hist.to_csv(HISTORY_FILE, index=False, encoding="utf-8-sig")
    return md_path


# ---------------------------------------------------------------- main
def main() -> None:
    p = argparse.ArgumentParser(description="หุ้น Volume สูงสุดรายวัน")
    p.add_argument("--source", choices=["yahoo", "csv"], default="yahoo")
    p.add_argument("--csv", type=Path, help="ไฟล์ CSV (ใช้กับ --source csv)")
    p.add_argument("--symbols", type=Path, default=HERE / "symbols_set100.txt")
    p.add_argument("--date", type=dt.date.fromisoformat, help="YYYY-MM-DD (ค่าเริ่มต้น: วันล่าสุด)")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--ai", action="store_true", help="ให้ Claude เขียนบทสรุปผู้บริหาร")
    a = p.parse_args()

    if a.source == "csv":
        if not a.csv:
            p.error("--source csv ต้องระบุ --csv")
        data, date = load_csv(a.csv), a.date or dt.date.today()
    else:
        data, date = fetch_yahoo(load_symbols(a.symbols), a.date)

    top = rank_top(data, a.top)
    md = to_markdown(top, date, a.top)
    if a.ai:
        md += "\n## บทสรุปผู้บริหาร (AI)\n\n" + ai_summary(md) + "\n"
    path = save(top, md, date)
    print(md)
    print(f"บันทึกรายงานที่ {path}")


if __name__ == "__main__":
    main()
