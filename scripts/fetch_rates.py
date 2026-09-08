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
