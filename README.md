# bitcoin-tickers

Bitcoin market data flows built on the [Massive REST API](https://massive.com/docs/rest/quickstart):

1. **`btc_tickers.py`** — pulls daily BTC OHLCV bars, validates them, stores CSV.
2. **Live dashboard** ([site](https://chfranc.github.io/bitcoin-tickers/)) — BTC/USD price and chart plus Bitcoin-native companies (Strategy, miners, treasuries): price, market cap, BTC holdings, BTC NAV and mNAV. Static site in `docs/`, data refreshed by `fetch_data.py`.

## Dashboard

```bash
export MASSIVE_API_KEY=your_key
python fetch_data.py        # rebuilds docs/data.json (~3 min, free-tier paced)
```

BTC holdings per company are not market data — they live in `companies.json` (approximate, from public filings) and are updated manually. mNAV = market cap ÷ (BTC held × BTC price).

## CSV fetcher

## What it does

- Fetches daily OHLCV bars for one or more crypto tickers (default `X:BTCUSD`).
- Runs basic sanity checks on every bar (OHLC consistency, positive prices) before persisting.
- Prints a summary (last close, daily change, period high/low) and writes one CSV per ticker under `data/`.
- Handles rate limits (free tier: 5 requests/min) with automatic backoff.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export MASSIVE_API_KEY=your_key   # get one at massive.com
```

## Usage

```bash
python btc_tickers.py                          # BTC-USD, last 30 days
python btc_tickers.py --days 90                # longer lookback
python btc_tickers.py --tickers X:BTCUSD X:BTCEUR
```

Example output:

```
X:BTCUSD  (2026-06-24 -> 2026-07-24, 30 bars)
  last close : 118,432.10  (+1.24% vs prev day)
  period low : 104,911.00
  period high: 120,850.00
  saved      : data/X_BTCUSD_daily.csv
```

## Automation

Run it daily with cron:

```
0 9 * * * cd /path/to/bitcoin-tickers && .venv/bin/python btc_tickers.py >> run.log 2>&1
```
