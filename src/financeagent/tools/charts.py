"""Chart tools. Render headlessly (Agg) to an in-memory PNG and return
{"summary": str, "image_base64": str} — the agent forwards the image to the
client but keeps only the summary in the LLM conversation history."""

import base64
import io
import re
from datetime import datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import requests

from ..config import FINNHUB_API_KEY, FINNHUB_BASE
from .market_data import _fetch_candles


def _fig_to_base64() -> str:
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close("all")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def plot_price_history(ticker: str, days: int = 90) -> dict | str:
    """Price history chart for a ticker, via Finnhub."""
    ticker = ticker.upper().strip()
    data = _fetch_candles(ticker, days)

    if data.get("s") != "ok" or len(data.get("c", [])) < 2:
        return f"Error: not enough price history for {ticker} to plot."

    dates = [datetime.fromtimestamp(t) for t in data["t"]]
    closes = data["c"]

    plt.figure(figsize=(8, 4))
    plt.plot(dates, closes, marker="o", markersize=2, color="#946E24")
    plt.title(f"{ticker} closing price, last {days} days")
    plt.xlabel("Date")
    plt.ylabel("Price ($)")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    image_base64 = _fig_to_base64()

    change_pct = (closes[-1] - closes[0]) / closes[0] * 100
    sign = "+" if change_pct >= 0 else ""
    summary = (
        f"Displayed a chart of {ticker}'s closing price over the last {days} days "
        f"(source: {data.get('source', 'Finnhub')}). Started at ${closes[0]:.2f}, "
        f"ended at ${closes[-1]:.2f} ({sign}{change_pct:.1f}%)."
    )
    return {"summary": summary, "image_base64": image_base64}


def plot_portfolio_allocation(holdings: str) -> dict | str:
    """Pie chart of portfolio allocation by current market value.

    holdings: comma separated entries like "AAPL:10:150, MSFT:5:300"
    meaning ticker:shares:cost_basis_per_share.
    """
    positions = []
    for entry in holdings.split(","):
        entry = entry.strip()
        if not entry:
            continue
        match = re.match(r"^([A-Za-z.]+):([\d.]+):([\d.]+)$", entry)
        if not match:
            return f"Error: could not parse '{entry}'. Use ticker:shares:cost_basis, e.g. AAPL:10:150"
        ticker, shares, cost_basis = match.groups()
        positions.append((ticker.upper(), float(shares), float(cost_basis)))

    if not positions:
        return "Error: no valid holdings provided."

    labels = []
    values = []
    for ticker, shares, _cost_basis in positions:
        resp = requests.get(
            f"{FINNHUB_BASE}/quote",
            params={"symbol": ticker, "token": FINNHUB_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        price = resp.json().get("c", 0) or 0
        labels.append(ticker)
        values.append(price * shares)

    total_value = sum(values)
    if total_value == 0:
        return "Error: could not price any of the positions."

    plt.figure(figsize=(6, 6))
    plt.pie(
        values,
        labels=labels,
        autopct="%1.1f%%",
        startangle=90,
        colors=["#946E24", "#B3C9CD", "#8BA18E", "#ECB748", "#E0D5C0", "#CFAE70"],
    )
    plt.title("Portfolio allocation by market value")
    plt.tight_layout()
    image_base64 = _fig_to_base64()

    summary = (
        f"Displayed a pie chart of portfolio allocation across {len(labels)} positions, "
        f"total value ${total_value:,.2f}."
    )
    return {"summary": summary, "image_base64": image_base64}
