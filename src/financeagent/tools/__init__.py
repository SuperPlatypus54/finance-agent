"""Tool registry: JSON schemas for the LLM plus the name -> callable dispatch table."""

from . import budget, charts, market_data, portfolio, utility
from .schemas import (
    AddAccountArgs,
    CalculateArgs,
    CompareArgs,
    CurrentTimeArgs,
    ExecutePythonArgs,
    ListFilesArgs,
    LogExpenseArgs,
    NetWorthArgs,
    PlotPriceHistoryArgs,
    PortfolioArgs,
    PriceHistoryArgs,
    ReadFileArgs,
    ReadNotesArgs,
    SpendingArgs,
    TakeNotesArgs,
    TickerArgs,
    VolatilityArgs,
    WebSearchArgs,
    WriteFileArgs,
    tool_from_model,
)

TOOL_SCHEMAS = [
    tool_from_model("read_file", "Read the contents of a text file from the sandbox directory", ReadFileArgs),
    tool_from_model("write_file", "Write text content to a file in the sandbox directory. Set overwrite=true to replace an existing file.", WriteFileArgs),
    tool_from_model("list_files", "List the names of files and folders in a sandbox directory", ListFilesArgs),
    tool_from_model("calculate", "Evaluate a basic arithmetic expression like '2 + 3 * 4'. Supports +, -, *, /, **, %.", CalculateArgs),
    tool_from_model("web_search", "Search the live web for current information", WebSearchArgs),
    tool_from_model("take_notes", "Save a short note to memory, to refer back to later in this task", TakeNotesArgs),
    tool_from_model("read_notes", "Read back every note saved so far in this task", ReadNotesArgs),
    tool_from_model("current_time", "Get the current date and time", CurrentTimeArgs),
    tool_from_model("execute_python", "Execute a snippet of Python code and return whatever it printed. Use calculate for plain arithmetic instead.", ExecutePythonArgs),
    tool_from_model("get_quote", "Current price and day change for a stock ticker, from Finnhub.", TickerArgs),
    tool_from_model("get_price_history", "Daily closing prices for a ticker over the last N days, from Finnhub.", PriceHistoryArgs),
    tool_from_model("get_fundamentals", "Company fundamentals: PE ratio, market cap, dividend yield, from Alpha Vantage.", TickerArgs),
    tool_from_model("get_earnings", "Last four quarters of earnings vs estimates for a ticker, from Alpha Vantage.", TickerArgs),
    tool_from_model("get_volatility", "Annualized volatility (price swing risk) for a stock ticker.", VolatilityArgs),
    tool_from_model("compare_stocks", "Side by side fundamentals comparison for up to 5 stock tickers.", CompareArgs),
    tool_from_model("compute_portfolio", "Allocation, unrealized gain/loss, concentration risk, and volatility for a set of holdings.", PortfolioArgs),
    tool_from_model("plot_price_history", "Display a price history chart for a ticker.", PlotPriceHistoryArgs),
    tool_from_model("plot_portfolio_allocation", "Display a pie chart of portfolio allocation by market value.", PortfolioArgs),
    tool_from_model("add_account", "Create a local finance account (checking, savings, etc), no bank linking.", AddAccountArgs),
    tool_from_model("log_expense", "Log a transaction against an existing local account.", LogExpenseArgs),
    tool_from_model("get_net_worth", "Current balance of every local account and total net worth.", NetWorthArgs),
    tool_from_model("get_spending_by_category", "Local spending grouped by category over the last N days.", SpendingArgs),
]

DISPATCH = {
    "read_file": utility.read_file,
    "write_file": utility.write_file,
    "list_files": utility.list_files,
    "calculate": utility.calculate,
    "web_search": utility.web_search,
    "current_time": utility.current_time,
    "execute_python": utility.execute_python,
    "get_quote": market_data.get_quote,
    "get_price_history": market_data.get_price_history,
    "get_fundamentals": market_data.get_fundamentals,
    "get_earnings": market_data.get_earnings,
    "get_volatility": market_data.get_volatility,
    "compare_stocks": market_data.compare_stocks,
    "compute_portfolio": portfolio.compute_portfolio,
    "plot_price_history": charts.plot_price_history,
    "plot_portfolio_allocation": charts.plot_portfolio_allocation,
    "add_account": budget.add_account,
    "log_expense": budget.log_expense,
    "get_net_worth": budget.get_net_worth,
    "get_spending_by_category": budget.get_spending_by_category,
}

# take_notes/read_notes have schemas here but no entry in DISPATCH: the Agent
# registers them itself as closures over its per-instance notes list.


def schema_for(name: str) -> dict:
    """Look up a tool schema by name, so nothing depends on list order."""
    return next(s for s in TOOL_SCHEMAS if s["function"]["name"] == name)
