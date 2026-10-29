"""미 재무부 Daily Treasury Par Yield Curve CSV를 연도별로 받아 data/ust_par/{year}.csv에 저장한다.

툴 밖의 수집 단계다. 툴은 저장된 파일을 quanttool.data.marketdata.UstParCsvLoader로 읽는다.

    python pipeline/ust_par.py 2025 2026
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

URL = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all?type=daily_treasury_yield_curve"
    "&field_tdr_date_value={year}&page&_format=csv"
)
OUT = Path(__file__).resolve().parents[1] / "data" / "ust_par"


def fetch(year: int, out_dir: Path = OUT) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(URL.format(year=year), headers={"User-Agent": "quanttool"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8-sig")
    if not body.startswith("Date,"):
        raise ValueError(f"{year}: 예상한 CSV 형식이 아니다: {body[:80]!r}")
    path = out_dir / f"{year}.csv"
    path.write_text(body, encoding="utf-8")
    return path


if __name__ == "__main__":
    for arg in sys.argv[1:] or ["2026"]:
        print(fetch(int(arg)))
