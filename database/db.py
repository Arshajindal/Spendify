"""SQLite data-access layer for Spendly.

All database access must go through this module — never inline SQL in
route handlers. Uses the stdlib sqlite3 module only (no ORM).
"""

import os
import sqlite3
from datetime import datetime

from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "expense_tracker.db")


def get_db():
    """Open a new SQLite connection with row access and FK enforcement.

    SQLite disables foreign key checks by default per-connection, so
    PRAGMA foreign_keys = ON must be set every time a connection opens.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def create_user(name, email, password):
    """Insert a new user with a hashed password.

    Returns the new user's id. Raises sqlite3.IntegrityError if the email
    is already taken (UNIQUE constraint on users.email) — callers must
    catch it.
    """
    conn = get_db()
    try:
        password_hash = generate_password_hash(password)
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name, email, password_hash),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_user_by_email(email):
    """Return the full user row for the given email, or None if no match.

    Used by login() to verify credentials via check_password_hash.
    """
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,),
        ).fetchone()
    finally:
        conn.close()


def get_user_by_id(user_id):
    """Return the full user row for the given id, or None if no match.

    Used by profile() to populate the user info card (name, email,
    created_at) for the logged-in user.
    """
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
    finally:
        conn.close()


def _date_range_clause(date_from, date_to):
    """Build an "AND date ..." SQL fragment plus matching params for an
    optional inclusive date range.

    Returns ("", []) when both bounds are None, so callers can always
    append the fragment and extend their params list unconditionally.
    """
    clause = ""
    params = []
    if date_from is not None:
        clause += " AND date >= ?"
        params.append(date_from)
    if date_to is not None:
        clause += " AND date <= ?"
        params.append(date_to)
    return clause, params


def get_expenses_by_user(user_id, date_from=None, date_to=None):
    """Return all expenses for a user, most recent date first.

    Used by profile() to populate the transaction history table. Ties on
    date are broken by id descending so newer inserts still sort first.
    When date_from/date_to (YYYY-MM-DD strings) are given, results are
    restricted to that inclusive date range.
    """
    conn = get_db()
    try:
        clause, date_params = _date_range_clause(date_from, date_to)
        query = "SELECT * FROM expenses WHERE user_id = ?" + clause + " ORDER BY date DESC, id DESC"
        return conn.execute(query, [user_id] + date_params).fetchall()
    finally:
        conn.close()


def get_expense_summary(user_id, date_from=None, date_to=None):
    """Return total spent, transaction count, and top category for a user.

    Runs two queries against the expenses table and combines them into a
    single dict: {"total": float, "count": int, "top_category": str or
    None, "top_category_amount": float}. If the user has zero expenses,
    total is 0.0, count is 0, and top_category is None. When
    date_from/date_to (YYYY-MM-DD strings) are given, both queries are
    restricted to that inclusive date range.
    """
    conn = get_db()
    try:
        clause, date_params = _date_range_clause(date_from, date_to)
        params = [user_id] + date_params

        totals = conn.execute(
            "SELECT COUNT(*) AS count, COALESCE(SUM(amount), 0) AS total "
            "FROM expenses WHERE user_id = ?" + clause,
            params,
        ).fetchone()
        top = conn.execute(
            "SELECT category, SUM(amount) AS total FROM expenses WHERE user_id = ?"
            + clause
            + " GROUP BY category ORDER BY total DESC LIMIT 1",
            params,
        ).fetchone()
        return {
            "total": totals["total"],
            "count": totals["count"],
            "top_category": top["category"] if top else None,
            "top_category_amount": top["total"] if top else 0,
        }
    finally:
        conn.close()


def get_category_breakdown(user_id, date_from=None, date_to=None):
    """Return per-category totals and percentages for a user, highest first.

    Each row is a dict {"category": str, "total": float, "percent": int}.
    Percentages are rounded so they always sum to exactly 100 (the last
    row absorbs any rounding remainder). Returns an empty list if the
    user has zero expenses. When date_from/date_to (YYYY-MM-DD strings)
    are given, results are restricted to that inclusive date range.
    """
    conn = get_db()
    try:
        clause, date_params = _date_range_clause(date_from, date_to)
        query = (
            "SELECT category, SUM(amount) AS total FROM expenses WHERE user_id = ?"
            + clause
            + " GROUP BY category ORDER BY total DESC"
        )
        rows = conn.execute(query, [user_id] + date_params).fetchall()
        if not rows:
            return []

        grand_total = sum(row["total"] for row in rows)
        breakdown = []
        running_percent = 0
        for i, row in enumerate(rows):
            if i == len(rows) - 1:
                percent = 100 - running_percent
            else:
                percent = round(row["total"] / grand_total * 100)
                running_percent += percent
            breakdown.append(
                {"category": row["category"], "total": row["total"], "percent": percent}
            )
        return breakdown
    finally:
        conn.close()


def init_db():
    """Create the users and expenses tables if they don't exist yet.

    Safe to call on every app startup.
    """
    conn = get_db()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                category TEXT NOT NULL,
                date TEXT NOT NULL,
                description TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def seed_db():
    """Insert one demo user and 8 sample expenses, once only.

    Idempotent: if any row already exists in users, does nothing.
    """
    conn = get_db()
    try:
        row = conn.execute("SELECT 1 FROM users LIMIT 1").fetchone()
        if row is not None:
            return

        password_hash = generate_password_hash("demo123")
        cursor = conn.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            ("Demo User", "demo@spendly.com", password_hash),
        )
        user_id = cursor.lastrowid

        today = datetime.now()
        # Day values are all <= 28 so .replace(day=...) is valid in every
        # calendar month (including February).
        sample_expenses = [
            (12.50, "Food", 2, "Grocery shopping"),
            (8.75, "Transport", 4, "Bus fare"),
            (60.00, "Bills", 6, "Electricity bill"),
            (22.30, "Food", 9, "Dinner with friends"),
            (15.99, "Entertainment", 13, "Movie tickets"),
            (45.00, "Health", 17, "Pharmacy - medicines"),
            (34.20, "Shopping", 21, "New t-shirt"),
            (10.00, "Other", 26, "Miscellaneous expense"),
        ]
        rows = [
            (
                user_id,
                amount,
                category,
                today.replace(day=day).strftime("%Y-%m-%d"),
                description,
            )
            for amount, category, day, description in sample_expenses
        ]
        conn.executemany(
            """
            INSERT INTO expenses (user_id, amount, category, date, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()
