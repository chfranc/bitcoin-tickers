"""Build docs/data.json for the bitcoin-tickers site from the Massive REST API.

Fetches daily bars for BTC-USD and a list of Bitcoin-native companies
(companies.json), plus market caps, and writes a single JSON the static
site reads. Paced for the free tier (5 requests/min).

Usage:
    export MASSIVE_API_KEY=your_key
    python fetch_data.py
"""

import json
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

import requests

BASE_URL = "https://api.massive.com"
LOOKBACK_DAYS = 90
CALL_SPACING = 13  # seconds between calls; free tier = 5 req/min
MAX_RETRIES = 3

_last_call = [0.0]


def get(path: str, api_key: str, params: dict = None) -> dict:
    """Rate-limit-paced GET with retries."""
    wait = CALL_SPACING - (time.time() - _last_call[0])
    if wait > 0:
        time.sleep(wait)
    params = dict(params or {})
    params["apiKey"] = api_key
    for attempt in range(1, MAX_RETRIES + 1):
        _last_call[0] = time.time()
        resp = requests.get(BASE_URL + path, params=params, timeout=30)
        if resp.status_code == 429:
            print(f"    rate limited, waiting 65s (attempt {attempt})...")
            time.sleep(65)
            continue
        if resp.status_code == 401:
            sys.exit("ERROR: invalid API key (401).")
        if resp.status_code == 404:
            return {}
        if resp.status_code >= 500:
            time.sleep(5 * attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    print(f"    WARNING: giving up on {path}")
    return {}


def daily_closes(ticker: str, api_key: str) -> list:
    """[[iso_date, close], ...] oldest first, for the last LOOKBACK_DAYS."""
    to = date.today()
    frm = to - timedelta(days=LOOKBACK_DAYS)
    data = get(f"/v2/aggs/ticker/{ticker}/range/1/day/{frm}/{to}", api_key,
               params={"adjusted": "true", "sort": "asc", "limit": 50000})
    out = []
    for r in data.get("results", []):
        d = datetime.fromtimestamp(r["t"] / 1000, tz=timezone.utc).date()
        out.append([d.isoformat(), r["c"]])
    return out


def market_cap(ticker: str, api_key: str):
    data = get(f"/v3/reference/tickers/{ticker}", api_key)
    return (data.get("results") or {}).get("market_cap")


def pct(bars: list, days_back: int):
    """% change of last close vs the close ~days_back trading points earlier."""
    if len(bars) < 2:
        return None
    ref = bars[max(0, len(bars) - 1 - days_back)][1]
    return (bars[-1][1] / ref - 1) * 100 if ref else None


def main() -> None:
    api_key = os.environ.get("MASSIVE_API_KEY")
    if not api_key:
        sys.exit("ERROR: set MASSIVE_API_KEY first.")

    with open("companies.json") as f:
        cfg = json.load(f)

    print("BTC-USD...")
    btc_bars = daily_closes("X:BTCUSD", api_key)
    if not btc_bars:
        sys.exit("ERROR: no BTC data returned; aborting.")
    btc_price = btc_bars[-1][1]

    companies = []
    for c in cfg["companies"]:
        t = c["ticker"]
        print(f"{t}...")
        bars = daily_closes(t, api_key)
        if not bars:
            print(f"    no data for {t}, skipping.")
            continue
        mc = market_cap(t, api_key)
        holdings = c.get("btc_holdings") or 0
        btc_nav = holdings * btc_price
        companies.append({
            "ticker": t,
            "name": c["name"],
            "price": bars[-1][1],
            "change1d": pct(bars, 1),
            "change30d": pct(bars, 21),  # ~21 trading days
            "market_cap": mc,
            "btc_holdings": holdings,
            "btc_nav": btc_nav,
            "mnav": (mc / btc_nav) if (mc and btc_nav) else None,
            "bars": bars,
        })

    out = {
        "updated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "holdings_as_of": cfg.get("_as_of"),
        "btc": {
            "price": btc_price,
            "change1d": pct(btc_bars, 1),
            "change30d": pct(btc_bars, 30),
            "bars": btc_bars,
        },
        "companies": companies,
    }
    os.makedirs("docs", exist_ok=True)
    with open("docs/data.json", "w") as f:
        json.dump(out, f)
    print(f"\nWrote docs/data.json — BTC {btc_price:,.0f}, "
          f"{len(companies)} companies.")


if __name__ == "__main__":
    main()
