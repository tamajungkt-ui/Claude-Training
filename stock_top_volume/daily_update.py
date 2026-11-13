"""
อัปเดตข้อมูล dashboard รายวัน (ไม่ต้องใช้ข้อมูลเดิม คำนวณใหม่ทั้งหมดจาก Yahoo Finance)

สร้าง 3 ไฟล์ในโฟลเดอร์ที่ระบุ:
  history.csv        หุ้น Volume สูงสุด 10 อันดับ ของ 5 วันทำการล่าสุด
  dividends.csv      ปันผล 12 เดือน, อัตราปันผล ณ ราคาล่าสุด, ผลตอบแทนรวมปันผล 1/3/5 ปี
                     ของหุ้น 10 อันดับ Volume วันล่าสุด
  yield_history.csv  อัตราปันผล ณ ราคาปิดของแต่ละวัน ย้อนหลัง 6 วันทำการ (วันล่าสุด + 5 วันก่อนหน้า)

ใช้:  python daily_update.py --out <โฟลเดอร์>
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yfinance as yf

HERE = Path(__file__).resolve().parent
DAYS = 6  # วันล่าสุด + ย้อนหลัง 5 วัน


def load_symbols(path: Path) -> list[str]:
    return [s.strip().upper() for s in path.read_text(encoding="utf-8").splitlines()
            if s.strip() and not s.startswith("#")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--symbols", type=Path, default=HERE / "symbols_set100.txt")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)

    symbols = load_symbols(a.symbols)
    raw = yf.download([f"{s}.BK" for s in symbols], period="15d", group_by="ticker",
                      auto_adjust=False, progress=False, threads=True)
    rows = []
    for s in symbols:
        tk = f"{s}.BK"
        if tk not in raw.columns.get_level_values(0):
            continue
        df = raw[tk].dropna(subset=["Close", "Volume"])
        for d, r in df[df["Volume"] > 0].iterrows():
            rows.append({"date": pd.Timestamp(d).date().isoformat(), "symbol": s,
                         "volume": int(r["Volume"]), "close": round(float(r["Close"]), 2)})
    vol = pd.DataFrame(rows)
    # ใช้เฉพาะวันที่มีข้อมูลครบเกือบทุกตัว (ตัดวันที่ตลาดยังไม่ปิด/ข้อมูลยังไม่ครบ)
    counts = vol.groupby("date")["symbol"].nunique()
    full = counts[counts >= 0.8 * counts.max()].index
    dates = sorted(full)[-5:]

    # 1) Top 10 Volume ของ 5 วันทำการล่าสุด
    hist = []
    for d in dates:
        top = vol[vol["date"] == d].sort_values("volume", ascending=False).head(10).copy()
        top.insert(1, "rank", range(1, len(top) + 1))
        top["value_mb"] = (top["volume"] * top["close"] / 1e6).round(1)
        hist.append(top)
    hist = pd.concat(hist)[["date", "rank", "symbol", "volume", "close", "value_mb"]]
    hist.to_csv(a.out / "history.csv", index=False)

    # 2) ปันผลของหุ้น 10 อันดับวันล่าสุด
    latest = dates[-1]
    top_syms = hist[hist["date"] == latest]["symbol"].tolist()
    div_rows, yield_rows = [], []
    for s in top_syms:
        h = yf.Ticker(f"{s}.BK").history(period="6y", auto_adjust=False, actions=True)
        h.index = h.index.tz_localize(None).normalize()
        h = h[h.index <= pd.Timestamp(latest)]
        dv = h["Dividends"][h["Dividends"] > 0]  # ก่อนกรอง: บางวัน XD ไม่มีแถวราคา
        dv = dv.groupby(dv.index).sum()
        h = h[h["Close"].notna() & (h["Volume"] > 0)]

        def ttm(day: pd.Timestamp) -> float:
            return float(dv[(dv.index > day - pd.Timedelta(days=365)) & (dv.index <= day)].sum())

        for day in h.index[-DAYS:]:
            c = float(h.at[day, "Close"])
            t = ttm(day)
            yield_rows.append({"date": day.date().isoformat(), "symbol": s, "close": round(c, 2),
                               "div_ttm": round(t, 4), "yield_pct": round(t / c * 100, 2)})

        last = h.index[-1]
        adj = h["Adj Close"]

        def tr(days: int):
            past = adj[adj.index <= last - pd.Timedelta(days=days)]
            return None if past.empty else round(float(adj.iloc[-1] / past.iloc[-1] - 1) * 100, 1)

        yearly = dv.groupby(dv.index.year).sum()
        close = float(h["Close"].iloc[-1])
        rec = {"symbol": s, "price_date": last.date().isoformat(), "close": round(close, 2),
               "div_ttm": round(ttm(last), 4), "yield_pct": round(ttm(last) / close * 100, 2)}
        this_year = last.year
        for y in range(this_year - 5, this_year):
            rec[f"div_{y}"] = round(float(yearly.get(y, 0.0)), 4)
        rec[f"div_{this_year}_ytd"] = round(float(yearly.get(this_year, 0.0)), 4)
        rec.update(total_return_1y_pct=tr(365), total_return_3y_pct=tr(365 * 3),
                   total_return_5y_pct=tr(365 * 5))
        div_rows.append(rec)

    pd.DataFrame(div_rows).to_csv(a.out / "dividends.csv", index=False)
    pd.DataFrame(yield_rows).to_csv(a.out / "yield_history.csv", index=False)
    print(f"latest={latest} top10={','.join(top_syms)}")
    print(pd.DataFrame(yield_rows).pivot(index="symbol", columns="date", values="yield_pct").to_string())


if __name__ == "__main__":
    main()
