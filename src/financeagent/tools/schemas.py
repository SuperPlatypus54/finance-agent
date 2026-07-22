"""Pydantic argument models for every tool, and the schema generator."""

from pydantic import BaseModel, Field


def tool_from_model(name: str, description: str, model: type[BaseModel]) -> dict:
    schema = model.model_json_schema()
    schema.pop("title", None)  # Pydantic adds a 'title' the API doesn't need
    return {
        "type": "function",
        "function": {"name": name, "description": description, "parameters": schema},
    }


# --- General utility tools ---

class ReadFileArgs(BaseModel):
    filename: str = Field(description="Name of the file to read, relative to the sandbox directory. Do not include '..' or absolute paths.")


class WriteFileArgs(BaseModel):
    filename: str = Field(description="Name of the file to write, relative to the sandbox directory. Do not include '..' or absolute paths.")
    content: str = Field(description="The text content to write to the file.")
    overwrite: bool = Field(default=False, description="Set to true only if you intend to replace an existing file's contents entirely.")


class ListFilesArgs(BaseModel):
    directory: str = Field(default=".", description="Directory to list, relative to the sandbox directory. Defaults to the sandbox root.")


class CalculateArgs(BaseModel):
    expression: str = Field(description="A basic arithmetic expression to evaluate, e.g. '2 + 3 * 4'. Supports +, -, *, /, **, %, and parentheses.")


class WebSearchArgs(BaseModel):
    query: str = Field(description="What to search for")
    max_results: int = Field(default=3, description="How many results to return")


class TakeNotesArgs(BaseModel):
    note: str = Field(description="The note to save")


class ReadNotesArgs(BaseModel):
    pass  # no arguments needed


class CurrentTimeArgs(BaseModel):
    pass  # no arguments needed


class ExecutePythonArgs(BaseModel):
    code: str = Field(description="Python code to run")


# --- Finance tools ---

class TickerArgs(BaseModel):
    ticker: str = Field(description="Stock ticker symbol, e.g. AAPL")


class PriceHistoryArgs(BaseModel):
    ticker: str = Field(description="Stock ticker symbol, e.g. AAPL")
    days: int = Field(default=30, description="Number of days of history to fetch")


class PlotPriceHistoryArgs(BaseModel):
    ticker: str = Field(description="Stock ticker symbol, e.g. AAPL")
    days: int = Field(default=90, description="Number of days of history to plot")


class VolatilityArgs(BaseModel):
    ticker: str = Field(description="Stock ticker symbol, e.g. AAPL")
    days: int = Field(default=90, description="Number of days of price history to use")


class CompareArgs(BaseModel):
    tickers: str = Field(description="Comma separated ticker symbols to compare, e.g. 'AAPL, MSFT, GOOGL', max 5")


class PortfolioArgs(BaseModel):
    holdings: str = Field(description="Comma separated ticker:shares:cost_basis entries, e.g. 'AAPL:10:150, MSFT:5:300'")


class AddAccountArgs(BaseModel):
    name: str = Field(description="Account name, e.g. Checking")
    account_type: str = Field(description="checking, savings, credit, asset, or liability")


class LogExpenseArgs(BaseModel):
    account_name: str = Field(description="Name of an existing account")
    amount: float = Field(description="Negative for spending, positive for income")
    category: str = Field(description="Spending category, e.g. Groceries")
    note: str = Field(default="", description="Optional note")


class NetWorthArgs(BaseModel):
    pass  # no arguments needed


class SpendingArgs(BaseModel):
    days: int = Field(default=30, description="Number of days to look back")
