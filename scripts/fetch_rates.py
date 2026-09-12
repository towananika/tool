#!/usr/bin/env python3
"""KRW建ての為替レートを取得して rates.json に保存する。

取得元は2つ。上から順に試し、最初に成功したものを使う。

1. Dunamu（韓国）— 매매기준율 / 현찰 살 때 / 현찰 팔 때 / 송금 の4種が取れる。
   ただし GitHub Actions のランナー（海外）からは名前解決に失敗することがある。
2. open.er-api.com — 世界中から引ける。取れるのは基準レートのみ。

ブラウザからは CORS で直接読めないため、GitHub Actions 側で取得してリポジトリに置く。
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

# 通貨コードと、韓国の慣習にあわせた表示単位（円は100単位で出す）
CURRENCIES = [
    ("USD", 1, "미국 달러"),
    ("JPY", 100, "일본 옌"),
    ("EUR", 1, "유로"),
    ("CNY", 1, "중국 위안"),
    ("GBP", 1, "영국 파운드"),
    ("AUD", 1, "호주 달러"),
]

DUNAMU = "https://quotation-api-cdn.dunamu.com/v1/forex/recent?codes=" + ",".join(
    "FRX.KRW" + c for c, _, _ in CURRENCIES
)
ERAPI = "https://open.er-api.com/v6/latest/KRW"

KST = timezone(timedelta(hours=9))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "rates.json")
HIST_DAYS = 180   # 半年ぶん。「この数ヶ月で高いか安いか」が言えれば足りる


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": "pace-maai-rates/1.0"})
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.loads(res.read().decode("utf-8"))


def from_dunamu():
    """4種そろったレートを返す。取れなければ None。"""
    rates = {}
    for row in get(DUNAMU):
        cur = (row.get("currencyCode") or "")[-3:]
        if not cur or row.get("basePrice") in (None, 0):
            continue
        rates[cur] = {
            "unit": row.get("currencyUnit", 1),
            "base": row.get("basePrice"),
            "cashBuy": row.get("cashBuyingPrice"),
            "cashSell": row.get("cashSellingPrice"),
            "ttBuy": row.get("ttBuyingPrice"),
            "ttSell": row.get("ttSellingPrice"),
            "name": row.get("currencyName"),
            "date": row.get("date"),
            "time": row.get("time"),
        }
    return rates or None


def from_erapi():
    """基準レートだけを返す。取れなければ None。"""
    data = get(ERAPI)
    if data.get("result") != "success":
        return None
    per_krw = data.get("rates") or {}
    day = (data.get("time_last_update_utc") or "")[5:16]  # 例: 08 Sep 2026

    rates = {}
    for cur, unit, name in CURRENCIES:
        v = per_krw.get(cur)
        if not v:
            continue
        rates[cur] = {
            "unit": unit,
            "base": round(unit / v, 2),   # 1（または100）単位あたりのウォン
            "cashBuy": None,              # この取得元では取れない
            "cashSell": None,
            "ttBuy": None,
            "ttSell": None,
            "name": name,
            "date": day,
            "time": "",
        }
    return rates or None


# ===== 国債利回り（イールドカーブ） =====
# 韓国: 韓国銀行ECOS 817Y002「시장금리(일별)」。sample鍵は1回10件までなので2回に分ける。
# 米国: 財務省の日次イールドカーブCSV。鍵は不要。
# ここが失敗しても為替の更新は続ける（前回の値を残す）。

ECOS = "https://ecos.bok.or.kr/api/StatisticSearch/sample/json/kr/{a}/{b}/817Y002/D/{d}/{d}"
UST = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
       "daily-treasury-rates.csv/{y}/all?type=daily_treasury_yield_curve"
       "&field_tdr_date_value={y}&page&_format=csv")

KR_WANT = ("1", "2", "3", "5", "10", "20", "30")


def kr_yields():
    """国庫債の年限別利回り。直近の営業日を7日さかのぼって探す。"""
    import re
    for back in range(0, 8):
        day = (datetime.now(KST) - timedelta(days=back)).strftime("%Y%m%d")
        rows = []
        for a, b in ((1, 10), (11, 20)):
            try:
                d = get(ECOS.format(a=a, b=b, d=day))
            except Exception:
                continue
            rows += (d.get("StatisticSearch") or {}).get("row") or []
        curve = {}
        for r in rows:
            m = re.match(r"국고채\((\d+)년\)", r.get("ITEM_NAME1") or "")
            if m and m.group(1) in KR_WANT and r.get("DATA_VALUE"):
                curve[m.group(1)] = float(r["DATA_VALUE"])
        if len(curve) >= 5:
            return {"date": day, "source": "BOK ECOS 817Y002", "curve": curve}
    return None


def us_yields():
    """米国財務省の日次カーブ。最新行を使う。"""
    year = datetime.now(KST).year
    req = urllib.request.Request(UST.format(y=year),
                                 headers={"User-Agent": "pace-maai-rates/1.0"})
    with urllib.request.urlopen(req, timeout=25) as res:
        text = res.read().decode("utf-8", "replace")

    lines = [l for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        return None
    head = [h.strip().strip('"') for h in lines[0].split(",")]
    cells = [c.strip().strip('"') for c in lines[1].split(",")]

    curve = {}
    for h, c in zip(head[1:], cells[1:]):
        if not c:
            continue
        n = h.replace(" Mo", "").replace(" Month", "").replace(" Yr", "")
        if "Yr" in h and n in ("1", "2", "3", "5", "7", "10", "20", "30"):
            curve[n] = float(c)
    if not curve:
        return None
    return {"date": cells[0], "source": "US Treasury daily yield curve", "curve": curve}


def collect_yields(prev):
    """取れた分だけ入れ替える。取れなければ前回の値をそのまま返す。"""
    out = dict((prev.get("yields") or {}))
    for key, fn in (("kr", kr_yields), ("us", us_yields)):
        try:
            v = fn()
        except Exception as e:
            print("yields skip", key, ":", e, file=sys.stderr)
            continue
        if v:
            out[key] = v
    if not out:
        return None
    out["updated"] = datetime.now(KST).isoformat(timespec="seconds")
    return out


def merged_history(prev, rates, day):
    """1日1件、通貨ごとの基準レートだけを積む。同じ日は最後の取得で上書きする。

    履歴は rates.json の中に入れる。ファイルを分けると Actions 側の
    コミット対象を増やす必要があり、そこは触れる権限がないため。
    """
    days = [d for d in (prev.get("history") or []) if d.get("date") != day]
    days.append({
        "date": day,
        "base": {cur: r["base"] for cur, r in rates.items() if r.get("base")},
    })
    days.sort(key=lambda d: d["date"])
    return days[-HIST_DAYS:]


def read_prev():
    try:
        with open(OUT, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


SOURCES = [
    ("dunamu quotation api", from_dunamu),
    ("open.er-api.com", from_erapi),
]


def main():
    errors = []
    for label, fn in SOURCES:
        try:
            rates = fn()
        except Exception as e:
            errors.append(label + ": " + str(e))
            continue
        if not rates:
            errors.append(label + ": レートが1件も取れなかった")
            continue

        prev = read_prev()
        history = merged_history(prev, rates, datetime.now(KST).strftime("%Y-%m-%d"))
        has_cash = any(r.get("cashBuy") for r in rates.values())
        out = {
            "updated": datetime.now(KST).isoformat(timespec="seconds"),
            "source": label,
            "hasCash": has_cash,
            "note": "KRW建て。unit 単位あたりの韓国ウォン。"
                    + ("cashBuy=현찰 살 때, cashSell=현찰 팔 때"
                       if has_cash else "この取得元では基準レートのみ。現金の売買レートは入らない。"),
            "rates": rates,
            "history": history,
        }
        ylds = collect_yields(prev)
        if ylds:
            out["yields"] = ylds
        with open(OUT, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
            f.write("\n")

        for line in errors:
            print("skipped:", line, file=sys.stderr)
        print("wrote", OUT, "/ source:", label, "/", ", ".join(sorted(rates)))
        print("history:", len(history), "days")
        return 0

    for line in errors:
        print("failed:", line, file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
