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
