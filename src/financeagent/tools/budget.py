"""Local SQLite budget/net-worth ledger. The DB lives under the project data dir."""

import sqlite3
from datetime import datetime, timedelta

from ..config import DB_PATH


def _get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            type TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY,
            date TEXT NOT NULL,
            account_id INTEGER NOT NULL,
            category TEXT,
            amount REAL NOT NULL,
            note TEXT,
            FOREIGN KEY (account_id) REFERENCES accounts(id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS net_worth_snapshots (
            id INTEGER PRIMARY KEY,
            date TEXT NOT NULL,
            total REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


def add_account(name: str, account_type: str) -> str:
    """Create an account, e.g. name='Checking', account_type='checking' (or savings/credit/asset/liability)."""
    conn = _get_db()
    conn.execute("INSERT INTO accounts (name, type) VALUES (?, ?)", (name, account_type))
    conn.commit()
    account_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.close()
    return f"Created account '{name}' ({account_type}), id {account_id}"


def log_expense(account_name: str, amount: float, category: str, note: str = "") -> str:
    """Log a transaction. Use a negative amount for spending, positive for income."""
    conn = _get_db()
    account = conn.execute("SELECT id FROM accounts WHERE name = ?", (account_name,)).fetchone()
    if not account:
        conn.close()
        return f"Error: no account named '{account_name}'. Create it first with add_account."

    conn.execute(
        "INSERT INTO transactions (date, account_id, category, amount, note) VALUES (?, ?, ?, ?, ?)",
        (datetime.now().strftime("%Y-%m-%d"), account[0], category, amount, note),
    )
    conn.commit()
    conn.close()
    return f"Logged {amount:+.2f} in '{account_name}' under '{category}'."


def get_net_worth() -> str:
    """Sum of all account balances (transaction totals) right now."""
    conn = _get_db()
    rows = conn.execute("""
        SELECT accounts.name, accounts.type, COALESCE(SUM(transactions.amount), 0) AS balance
        FROM accounts
        LEFT JOIN transactions ON transactions.account_id = accounts.id
        GROUP BY accounts.id
    """).fetchall()
    conn.close()

    if not rows:
        return "No accounts yet. Use add_account to create one."

    total = sum(r[2] for r in rows)
    lines = ["Balances by account:"]
    for name, acc_type, balance in rows:
        lines.append(f"- {name} ({acc_type}): ${balance:,.2f}")
    lines.append(f"Net worth: ${total:,.2f}")
    return "\n".join(lines)


def get_spending_by_category(days: int = 30) -> str:
    """Total spending (negative amounts) grouped by category over the last N days."""
    conn = _get_db()
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    rows = conn.execute("""
        SELECT category, SUM(amount) AS total
        FROM transactions
        WHERE amount < 0 AND date >= ?
        GROUP BY category
        ORDER BY total ASC
    """, (cutoff,)).fetchall()
    conn.close()

    if not rows:
        return f"No spending logged in the last {days} days."

    lines = [f"Spending by category, last {days} days:"]
    for category, total in rows:
        lines.append(f"- {category or 'Uncategorized'}: ${abs(total):,.2f}")
    return "\n".join(lines)
