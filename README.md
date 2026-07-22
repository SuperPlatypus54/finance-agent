# Finance Agent

A personal finance ReAct agent (converted from the `Fibo` notebook prototype) with a
streaming chat API and a web chat UI. The agent talks to an LLM through OpenRouter and
has 22 tools: market data (Finnhub / Alpha Vantage), portfolio math, chart generation,
a local SQLite budget/net-worth ledger, and general utilities (sandboxed files, web
search, notes, calculator, python execution).

## Setup

```bash
python3.12 -m venv .venv          # or: uv venv --python 3.12 .venv
.venv/bin/pip install -e .        # or: uv pip install -e . --python .venv/bin/python
cp .env.example .env.local        # then fill in your API keys (.env.local is gitignored)
```

Keys needed (all have free tiers): [OpenRouter](https://openrouter.ai/keys),
[Tavily](https://app.tavily.com), [Finnhub](https://finnhub.io),
[Alpha Vantage](https://www.alphavantage.co).

## Run

```bash
.venv/bin/uvicorn financeagent.api.main:app --reload
```

Open http://127.0.0.1:8000 — the chat UI is served from `frontend/`.

## Project layout

```
src/financeagent/
  config.py          env vars, data paths, API clients
  agent/core.py      Agent class; ReAct loop as a generator of streaming events
  agent/__init__.py  finance system prompt + make_finance_agent() factory
  tools/
    schemas.py       Pydantic arg models -> JSON schemas
    utility.py       sandboxed read/write/list files, calculate, web_search,
                     current_time, execute_python
    market_data.py   get_quote, get_price_history, get_fundamentals, get_earnings,
                     get_volatility, compare_stocks
    charts.py        plot_price_history, plot_portfolio_allocation (headless Agg ->
                     base64 PNG)
    portfolio.py     compute_portfolio (allocation, gain/loss, concentration, volatility)
    budget.py        SQLite ledger: add_account, log_expense, get_net_worth,
                     get_spending_by_category
    __init__.py      TOOL_SCHEMAS + DISPATCH registry
  api/main.py        FastAPI app: SSE chat endpoint, session store, static frontend
frontend/            chat UI (implements the "Finance Agent Chat" Claude Design mock)
data/                created at runtime: sandbox/ for file tools, finance.db ledger
```

## Chat API

### `POST /api/chat`

Request body:

```json
{ "message": "How has AAPL moved this quarter?", "session_id": null }
```

- `message` (string, required): the user's message.
- `session_id` (string or null): pass the id from a previous response to continue
  that conversation with full history. Omit or send `null` to start a new one.

Response: a **Server-Sent Events** stream (`text/event-stream`). Each frame has an
`event:` type and a `data:` line containing a JSON object. Frames may be separated by
`\r\n`; comment lines starting with `:` (keep-alive pings) should be ignored.

Events, in the order they can occur:

| event         | data payload                                                                 | meaning                                                                                                                                                                                                                                                                                     |
| ------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `session`     | `{"session_id": "abc123"}`                                                   | Always first. Echo this id in your next request to continue the conversation.                                                                                                                                                                                                               |
| `token`       | `{"text": "The "}`                                                           | A fragment of streamed assistant text. Concatenate fragments in order. Text may arrive before tool calls (thinking-out-loud) and after them (the answer).                                                                                                                                   |
| `tool_call`   | `{"id": "call_1", "name": "get_quote", "args": {"ticker": "AAPL"}}`          | The agent invoked a tool. Show a "working" row keyed by `id`.                                                                                                                                                                                                                               |
| `tool_result` | `{"id": "call_1", "name": "get_quote", "result": "AAPL: price $189.44 ..."}` | The tool finished; matches a prior `tool_call` by `id`. `result` is the text summary. For the two chart tools the payload also has `"image_base64"`: a PNG to render (`data:image/png;base64,...`). The image is **only** delivered here — it is never in the model's history or in `done`. |
| `done`        | `{"text": "full final answer"}`                                              | The turn is complete; `text` is the concatenation of the final answer's tokens. The stream closes after this.                                                                                                                                                                               |
| `error`       | `{"message": "..."}`                                                         | Something failed server-side; the stream closes after this.                                                                                                                                                                                                                                 |

A turn can interleave several rounds of `token` / `tool_call` / `tool_result` before
`done` (the agent loops up to 8 ReAct turns, then is forced to summarize).

Notes for UI authors:

- One streaming response per session at a time: a second `POST` for the same
  `session_id` while one is open returns **409**.
- Empty `message` returns **422**.
- `token` text is markdown-ish: `**bold**`, numbered/bulleted lists, `` `code` ``.
- Sessions live in process memory; a server restart clears them.

### Other endpoints

- `DELETE /api/sessions/{session_id}` — discard a conversation (204).
- `GET /api/health` — `{"status": "ok"}`.

## Deferred / notes

- **Plan mode** (the notebook's draft-plan -> human-approval flow) was dropped: pausing
  a request mid-stream for approval needs a two-request design (persist pending plan,
  approve via a second call) that deserves real design work if wanted later.
- `execute_python` is **not** sandboxed. Run the API in a container in any deployment
  that keeps this tool enabled.
- Sessions are in-memory; horizontal scaling or restarts need an external store.
- The design mock's portfolio sidebar (hardcoded brokerage numbers) was intentionally
  not implemented — there is no live data source for it yet.
