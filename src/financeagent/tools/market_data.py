"""Market data tools: quotes, history, fundamentals, earnings, volatility, comparison."""

import math
import statistics
from datetime import datetime, timedelta

import requests

from ..config import (
    ALPHA_VANTAGE_API_KEY,
    ALPHA_VANTAGE_BASE,
    FINNHUB_API_KEY,
    FINNHUB_BASE,
)

# Simple in-memory cache so repeat lookups in one process don't burn the
# Alpha Vantage 25/day free cap.
_alpha_vantage_cache: dict = {}


def _fetch_candles(ticker: str, days: int) -> dict:
    """Daily candles as {"s": "ok", "t": [...], "c": [...]}.

    Finnhub's /stock/candle is premium-only on free keys (403), so fall back to
    Yahoo Finance's free keyless chart API when Finnhub refuses access.
    """
    end = datetime.now()
    start = end - timedelta(days=days)
    resp = requests.get(
        f"{FINNHUB_BASE}/stock/candle",
        params={
            "symbol": ticker,
            "resolution": "D",
            "from": int(start.timestamp()),
            "to": int(end.timestamp()),
            "token": FINNHUB_API_KEY,
        },
        timeout=10,
    )
    if resp.status_code in (401, 403):
        return _fetch_candles_yahoo(ticker, days)
    resp.raise_for_status()
    data = resp.json()
    if data.get("s") != "ok":
        return _fetch_candles_yahoo(ticker, days)
    return data


def _fetch_candles_yahoo(ticker: str, days: int) -> dict:
    end = datetime.now()
    start = end - timedelta(days=days)
    resp = requests.get(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}",
        params={
            "period1": int(start.timestamp()),
            "period2": int(end.timestamp()),
            "interval": "1d",
        },
        headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        timeout=10,
    )
    resp.raise_for_status()
    result = (resp.json().get("chart", {}).get("result") or [None])[0]
    if not result:
        return {"s": "no_data"}

    timestamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    raw_closes = quote.get("close") or []

    ts, closes = [], []
    for t, c in zip(timestamps, raw_closes):
        if c is None:
            continue
        ts.append(t)
        closes.append(round(float(c), 4))

    if not closes:
        return {"s": "no_data"}
    return {"s": "ok", "t": ts, "c": closes, "source": "Yahoo Finance"}


def get_quote(ticker: str) -> str:
    """Current price and day change for a ticker, via Finnhub."""
    ticker = ticker.upper().strip()
    resp = requests.get(
        f"{FINNHUB_BASE}/quote",
        params={"symbol": ticker, "token": FINNHUB_API_KEY},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    if not data or data.get("c") in (None, 0):
        return f"Error: no quote data found for {ticker}. Check the ticker symbol."

    return (
        f"{ticker}: price ${data['c']:.2f}, change ${data['d']:.2f} "
        f"({data['dp']:.2f}%), day high ${data['h']:.2f}, day low ${data['l']:.2f}, "
        f"previous close ${data['pc']:.2f}. Source: Finnhub, as of "
        f"{datetime.fromtimestamp(data['t']).strftime('%Y-%m-%d %H:%M:%S')}."
    )


def get_price_history(ticker: str, days: int = 30) -> str:
    """Daily closing prices for a ticker over the last N days, via Finnhub."""
    ticker = ticker.upper().strip()
    data = _fetch_candles(ticker, days)

    if data.get("s") != "ok":
        return f"Error: no price history found for {ticker} over the last {days} days."

    lines = [f"Daily closes for {ticker}, last {days} days (source: {data.get('source', 'Finnhub')}):"]
    for t, c in zip(data["t"], data["c"]):
        date = datetime.fromtimestamp(t).strftime("%Y-%m-%d")
        lines.append(f"- {date}: ${c:.2f}")
    return "\n".join(lines)


def get_fundamentals(ticker: str) -> str:
    """Company fundamentals (PE, market cap, dividend yield, etc), via Alpha Vantage.

    Cached in memory per process since the free tier is capped at 25 requests/day.
    """
    ticker = ticker.upper().strip()
    if ticker in _alpha_vantage_cache.get("overview", {}):
        cached = _alpha_vantage_cache["overview"][ticker]
        return cached + "\n(Served from session cache to conserve the daily quota.)"

    resp = requests.get(
        ALPHA_VANTAGE_BASE,
        params={"function": "OVERVIEW", "symbol": ticker, "apikey": ALPHA_VANTAGE_API_KEY},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    if not data or "Symbol" not in data:
        return f"Error: no fundamentals found for {ticker}, or the daily Alpha Vantage quota may be exhausted."

    result = (
        f"{ticker} fundamentals (source: Alpha Vantage):\n"
        f"- Name: {data.get('Name', 'n/a')}\n"
        f"- Sector: {data.get('Sector', 'n/a')}\n"
        f"- Market cap: {data.get('MarketCapitalization', 'n/a')}\n"
        f"- PE ratio: {data.get('PERatio', 'n/a')}\n"
        f"- Dividend yield: {data.get('DividendYield', 'n/a')}\n"
        f"- 52 week range: {data.get('52WeekLow', 'n/a')} - {data.get('52WeekHigh', 'n/a')}"
    )
    _alpha_vantage_cache.setdefault("overview", {})[ticker] = result
    _alpha_vantage_cache.setdefault("overview_raw", {})[ticker] = data
    return result


def get_earnings(ticker: str) -> str:
    """Last four quarters of earnings (EPS estimate vs reported), via Alpha Vantage."""
    ticker = ticker.upper().strip()
    if ticker in _alpha_vantage_cache.get("earnings", {}):
        cached = _alpha_vantage_cache["earnings"][ticker]
        return cached + "\n(Served from session cache to conserve the daily quota.)"

    resp = requests.get(
        ALPHA_VANTAGE_BASE,
        params={"function": "EARNINGS", "symbol": ticker, "apikey": ALPHA_VANTAGE_API_KEY},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    quarterly = data.get("quarterlyEarnings", [])[:4]
    if not quarterly:
        return f"Error: no earnings data found for {ticker}."

    lines = [f"{ticker} last 4 quarterly earnings (source: Alpha Vantage):"]
    for q in quarterly:
        lines.append(
            f"- {q.get('fiscalDateEnding')}: reported EPS {q.get('reportedEPS')}, "
            f"estimated EPS {q.get('estimatedEPS')}, surprise {q.get('surprisePercentage')}%"
        )
    result = "\n".join(lines)
    _alpha_vantage_cache.setdefault("earnings", {})[ticker] = result
    return result


def get_volatility(ticker: str, days: int = 90) -> str:
    """Annualized volatility for a ticker, based on daily returns over the last N days, via Finnhub."""
    ticker = ticker.upper().strip()
    data = _fetch_candles(ticker, days)

    if data.get("s") != "ok" or len(data.get("c", [])) < 10:
        return f"Error: not enough price history for {ticker} over the last {days} days to compute volatility."

    closes = data["c"]
    daily_returns = [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]

    daily_stdev = statistics.stdev(daily_returns)
    annualized_volatility = daily_stdev * math.sqrt(252)

    return (
        f"{ticker} annualized volatility: {annualized_volatility * 100:.1f}%, "
        f"based on {len(daily_returns)} daily returns over the last {days} days "
        f"(source: {data.get('source', 'Finnhub')}). Higher means bigger price swings, not necessarily worse "
        f"long-term returns."
    )


def compare_stocks(tickers: str) -> str:
    """Side by side fundamentals for multiple tickers, from Alpha Vantage.

    tickers: comma separated symbols, e.g. "AAPL, MSFT, GOOGL"
    """
    symbols = [t.strip().upper() for t in tickers.split(",") if t.strip()]
    if not symbols:
        return "Error: no tickers provided."
    if len(symbols) > 5:
        return "Error: compare at most 5 tickers at once, to stay within the Alpha Vantage daily quota."

    rows = []
    for ticker in symbols:
        if ticker in _alpha_vantage_cache.get("overview_raw", {}):
            data = _alpha_vantage_cache["overview_raw"][ticker]
        else:
            resp = requests.get(
                ALPHA_VANTAGE_BASE,
                params={"function": "OVERVIEW", "symbol": ticker, "apikey": ALPHA_VANTAGE_API_KEY},
                timeout=10,
            )
            resp.raise_for_status()
            data = resp.json()
            if not data or "Symbol" not in data:
                rows.append((ticker, None))
                continue
            _alpha_vantage_cache.setdefault("overview_raw", {})[ticker] = data

        rows.append((ticker, data))

    lines = ["Comparison (source: Alpha Vantage):", ""]
    lines.append(f"{'Ticker':<8}{'Sector':<20}{'Market Cap':<15}{'PE Ratio':<10}{'Div Yield':<10}")
    for ticker, data in rows:
        if data is None:
            lines.append(f"{ticker:<8}(no data found, check ticker or daily quota)")
            continue
        lines.append(
            f"{ticker:<8}"
            f"{data.get('Sector', 'n/a'):<20}"
            f"{data.get('MarketCapitalization', 'n/a'):<15}"
            f"{data.get('PERatio', 'n/a'):<10}"
            f"{data.get('DividendYield', 'n/a'):<10}"
        )

    return "\n".join(lines)
