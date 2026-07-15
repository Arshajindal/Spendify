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


def get_expenses_by_user(user_id):
    """Return all expenses for a user, most recent date first.

    Used by profile() to populate the transaction history table. Ties on
    date are broken by id descending so newer inserts still sort first.
    """
    conn = get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE user_id = ? ORDER BY date DESC, id DESC",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()


def get_expense_summary(user_id):
    """Return total spent, transaction count, and top category for a user.

    Runs two queries against the expenses table and combines them into a
    single dict: {"total": float, "count": int, "top_category": str or
    None, "top_category_amount": float}. If the user has zero expenses,
    total is 0.0, count is 0, and top_category is None.
    """
    conn = get_db()
    try:
        totals = conn.execute(
            "SELECT COUNT(*) AS count, COALESCE(SUM(amount), 0) AS total "
            "FROM expenses WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        top = conn.execute(
            """
            SELECT category, SUM(amount) AS total
            FROM expenses
            WHERE user_id = ?
            GROUP BY category
            ORDER BY total DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        return {
            "total": totals["total"],
            "count": totals["count"],
            "top_category": top["category"] if top else None,
            "top_category_amount": top["total"] if top else 0,
        }
    finally:
        conn.close()


def get_category_breakdown(user_id):
    """Return per-category totals and percentages for a user, highest first.

    Each row is a dict {"category": str, "total": float, "percent": int}.
    Percentages are rounded so they always sum to exactly 100 (the last
    row absorbs any rounding remainder). Returns an empty list if the
    user has zero expenses.
    """
    conn = get_db()
    try:
        rows = conn.execute(
            """
            SELECT category, SUM(amount) AS total
            FROM expenses
            WHERE user_id = ?
            GROUP BY category
            ORDER BY total DESC
            """,
            (user_id,),
        ).fetchall()
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
