#!/usr/bin/env python3
"""Dunamu の公開為替APIから、KRW建ての基準レートと銀行の現金売買レートを取得して rates.json に保存する。

- 매매기준율(base) / 현찰 살 때(cashBuy) / 현찰 팔 때(cashSell) / 송금(tt) を保存
- ブラウザからは CORS で直接読めないため、GitHub Actions 側で取得してリポジトリに置く
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone

CODES = ["FRX.KRWUSD", "FRX.KRWJPY", "FRX.KRWEUR", "FRX.KRWCNY", "FRX.KRWGBP", "FRX.KRWAUD"]
URL = "https://quotation-api-cdn.dunamu.com/v1/forex/recent?codes=" + ",".join(CODES)
KST = timezone(timedelta(hours=9))
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rates.json")


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": "pace-maai-rates/1.0"})
    with urllib.request.urlopen(req, timeout=20) as res:
        return json.loads(res.read().decode("utf-8"))


def main():
    try:
        data = fetch()
    except Exception as e:  # ネットワーク障害時は既存ファイルを残す
        print("fetch failed:", e, file=sys.stderr)
        return 1

    rates = {}
    for row in data:
        cur = row.get("currencyCode")
        if not cur:
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

    if not rates:
        print("no rates parsed", file=sys.stderr)
        return 1

    out = {
        "updated": datetime.now(KST).isoformat(timespec="seconds"),
        "source": "dunamu quotation api",
        "note": "KRW建て。unit 単位あたりの韓国ウォン。cashBuy=현찰 살 때, cashSell=현찰 팔 때",
        "rates": rates,
    }

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print("wrote", OUT, "currencies:", ", ".join(sorted(rates)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
