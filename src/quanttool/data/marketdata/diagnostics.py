"""구축 결과 진단: 헬퍼 재가격 오차."""

from __future__ import annotations

import pandas as pd

from .todaysmarket import TodaysMarket


def helper_repricing(snap: TodaysMarket, curve_name: str) -> pd.DataFrame:
    """커브로 다시 계산한 시세와 시장 시세의 차이(bp). 부트스트랩이 맞으면 0에 가깝다."""
    rows = []
    with snap.active():
        snap.yield_curve(curve_name).discount(1.0)  # 부트스트랩 강제
        for h in snap.curve_helpers(curve_name):
            market = snap.quotes[h.quote_id].value()
            implied = h.to_quote(h.helper.impliedQuote())
            rows.append(
                {
                    "quote_id": h.quote_id,
                    "maturity": h.maturity.ISO(),
                    "market": market,
                    "implied": implied,
                    "error_bp": (implied - market) * 1e4,
                }
            )
    return pd.DataFrame(rows)
