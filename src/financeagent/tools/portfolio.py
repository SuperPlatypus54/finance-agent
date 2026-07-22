"""Portfolio math: allocation, unrealized gain/loss, concentration risk, volatility."""

import re

import requests

from ..config import FINNHUB_API_KEY, FINNHUB_BASE
from .market_data import get_volatility

CONCENTRATION_THRESHOLD_PCT = 40


def compute_portfolio(holdings: str) -> str:
    """Portfolio allocation, unrealized gain/loss, concentration risk, and volatility.

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

    rows = []
    total_value = 0.0
    for ticker, shares, cost_basis in positions:
        resp = requests.get(
            f"{FINNHUB_BASE}/quote",
            params={"symbol": ticker, "token": FINNHUB_API_KEY},
            timeout=10,
        )
        resp.raise_for_status()
        price = resp.json().get("c", 0) or 0
        market_value = price * shares
        cost_total = cost_basis * shares
        gain_loss = market_value - cost_total
        gain_loss_pct = (gain_loss / cost_total * 100) if cost_total else 0
        total_value += market_value
        rows.append((ticker, shares, price, market_value, gain_loss, gain_loss_pct))

    lines = ["Portfolio summary (prices via Finnhub, math computed locally):"]
    allocations = {}
    for ticker, shares, price, market_value, gain_loss, gain_loss_pct in rows:
        allocation_pct = (market_value / total_value * 100) if total_value else 0
        allocations[ticker] = allocation_pct
        sign = "+" if gain_loss >= 0 else ""
        lines.append(
            f"- {ticker}: {shares:g} shares @ ${price:.2f} = ${market_value:,.2f} "
            f"({allocation_pct:.1f}% of portfolio), unrealized {sign}${gain_loss:,.2f} "
            f"({sign}{gain_loss_pct:.1f}%)"
        )
    lines.append(f"Total portfolio value: ${total_value:,.2f}")

    concentrated = [t for t, pct in allocations.items() if pct > CONCENTRATION_THRESHOLD_PCT]
    if concentrated:
        lines.append("")
        lines.append(
            f"Concentration flag: {', '.join(concentrated)} each make up more than "
            f"{CONCENTRATION_THRESHOLD_PCT}% of this portfolio. A single company's "
            f"problems would hit the whole portfolio harder than if value were spread out."
        )

    weighted_volatility = 0.0
    volatility_failed = False
    for ticker in allocations:
        vol_result = get_volatility(ticker)
        vol_match = re.search(r"volatility: ([\d.]+)%", vol_result)
        if vol_match:
            weighted_volatility += float(vol_match.group(1)) * (allocations[ticker] / 100)
        else:
            volatility_failed = True

    if not volatility_failed:
        lines.append("")
        lines.append(
            f"Estimated portfolio volatility: {weighted_volatility:.1f}% annualized. "
            f"This is a simplified weighted average of each position's individual "
            f"volatility, it assumes the positions move independently and ignores "
            f"correlation, so it likely overstates risk for a genuinely diversified "
            f"portfolio and understates it if the positions tend to move together."
        )

    return "\n".join(lines)
