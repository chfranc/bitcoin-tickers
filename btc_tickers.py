"""Fetch Bitcoin market data from the Massive REST API and store it as CSV.

Pulls daily OHLCV bars for one or more crypto tickers (default: X:BTCUSD),
prints a summary to the console, and writes/updates one CSV per ticker.

Usage:
    export MASSIVE_API_KEY=your_key
    python btc_tickers.py                          # BTC-USD, last 30 days
    python btc_tickers.py --days 90
    python btc_tickers.py --tickers X:BTCUSD X:BTCEUR

Designed for the free tier (5 requests/min): one request per ticker,
with automatic backoff if the rate limit is hit.
"""

import argparse
import csv
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

import requests

BASE_URL = "https://api.massive.com"
MAX_RETRIES = 3
RATE_LIMIT_WAIT = 65  # seconds; free tier allows 5 requests/min


def get(path: str, api_key: str, params: dict = None) -> dict:
    """GET a Massive endpoint, retrying on rate limits and transient errors."""
    params = dict(params or {})
    params["apiKey"] = api_key
    for attempt in range(1, MAX_RETRIES + 1):
        resp = requests.get(BASE_URL + path, params=params, timeout=30)
        if resp.status_code == 429:
            print(f"  rate limited, waiting {RATE_LIMIT_WAIT}s "
                  f"(attempt {attempt}/{MAX_RETRIES})...")
            time.sleep(RATE_LIMIT_WAIT)
            continue
        if resp.status_code == 401:
            sys.exit("ERROR: invalid or missing API key (401). "
                     "Check the MASSIVE_API_KEY environment variable.")
        if resp.status_code >= 500:
            time.sleep(5 * attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    sys.exit(f"ERROR: giving up on {path} after {MAX_RETRIES} attempts.")


def fetch_daily_bars(ticker: str, days: int, api_key: str) -> list[dict]:
    """Fetch daily OHLCV bars for the last `days` days, oldest first."""
    to = date.today()
    frm = to - timedelta(days=days)
    data = get(
        f"/v2/aggs/ticker/{ticker}/range/1/day/{frm}/{to}",
        api_key,
        params={"adjusted": "true", "sort": "asc", "limit": 50000},
    )
    bars = []
    for r in data.get("results", []):
        day = datetime.fromtimestamp(r["t"] / 1000, tz=timezone.utc).date()
        bars.append({
            "date": day.isoformat(),
            "open": r["o"],
            "high": r["h"],
            "low": r["l"],
            "close": r["c"],
            "volume": r["v"],
            "vwap": r.get("vw", ""),
            "trades": r.get("n", ""),
        })
    return bars


def validate(bars: list[dict], ticker: str) -> None:
    """Basic sanity checks before persisting anything."""
    problems = []
    for b in bars:
        if not (b["low"] <= b["open"] <= b["high"]
                and b["low"] <= b["close"] <= b["high"]):
            problems.append(f"{b['date']}: OHLC out of range")
        if b["close"] <= 0:
            problems.append(f"{b['date']}: non-positive close")
    if problems:
        print(f"  WARNING [{ticker}]: {len(problems)} suspect bars: "
              + "; ".join(problems[:5]))


def write_csv(bars: list[dict], ticker: str, outdir: str) -> str:
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, ticker.replace(":", "_") + "_daily.csv")
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(bars[0].keys()))
        writer.writeheader()
        writer.writerows(bars)
    return path


def summarize(bars: list[dict], ticker: str) -> None:
    last, prev = bars[-1], bars[-2] if len(bars) > 1 else bars[-1]
    change = (last["close"] / prev["close"] - 1) * 100 if prev["close"] else 0
    lo = min(b["low"] for b in bars)
    hi = max(b["high"] for b in bars)
    print(f"\n{ticker}  ({bars[0]['date']} -> {last['date']}, {len(bars)} bars)")
    print(f"  last close : {last['close']:,.2f}  ({change:+.2f}% vs prev day)")
    print(f"  period low : {lo:,.2f}")
    print(f"  period high: {hi:,.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--tickers", nargs="+", default=["X:BTCUSD"],
                        help="Massive crypto tickers (default: X:BTCUSD)")
    parser.add_argument("--days", type=int, default=30,
                        help="lookback window in days (default: 30)")
    parser.add_argument("--outdir", default="data",
                        help="output directory for CSVs (default: data/)")
    args = parser.parse_args()

    api_key = os.environ.get("MASSIVE_API_KEY")
    if not api_key:
        sys.exit("ERROR: set the MASSIVE_API_KEY environment variable first.\n"
                 "  export MASSIVE_API_KEY=your_key")

    for i, ticker in enumerate(args.tickers):
        if i > 0:
            time.sleep(13)  # stay under 5 requests/min on the free tier
        bars = fetch_daily_bars(ticker, args.days, api_key)
        if not bars:
            print(f"\n{ticker}: no data returned, skipping.")
            continue
        validate(bars, ticker)
        summarize(bars, ticker)
        path = write_csv(bars, ticker, args.outdir)
        print(f"  saved      : {path}")


if __name__ == "__main__":
    main()
