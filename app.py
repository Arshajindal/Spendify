import sqlite3
from datetime import datetime

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import (
    create_user,
    get_category_breakdown,
    get_db,
    get_expense_summary,
    get_expenses_by_user,
    get_user_by_email,
    get_user_by_id,
    init_db,
    seed_db,
)

app = Flask(__name__)
app.secret_key = "spendly-dev-secret-key-change-in-production"

with app.app_context():
    init_db()
    seed_db()


# ------------------------------------------------------------------ #
# Routes                                                              #
# ------------------------------------------------------------------ #

@app.route("/")
def landing():
    return render_template("landing.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if not name or not email or not password or not confirm_password:
            flash("All fields are required.", "error")
            return render_template("register.html")

        if password != confirm_password:
            flash("Passwords do not match.", "error")
            return render_template("register.html")

        try:
            create_user(name, email, password)
        except sqlite3.IntegrityError:
            flash("Email already registered.", "error")
            return render_template("register.html")

        flash("Account created successfully. Please sign in.", "success")
        return redirect(url_for("login"))

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("user_id"):
        return redirect(url_for("profile"))

    if request.method == "GET":
        return render_template("login.html")

    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")

        if not email or not password:
            flash("Both fields are required.", "error")
            return render_template("login.html")

        user = get_user_by_email(email)
        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return render_template("login.html")

        session["user_id"] = user["id"]
        session["user_name"] = user["name"]
        return redirect(url_for("profile"))

    abort(405)


@app.route("/terms")
def terms():
    return render_template("terms.html")


@app.route("/privacy")
def privacy():
    return render_template("privacy.html")


# ------------------------------------------------------------------ #
# Placeholder routes — students will implement these                  #
# ------------------------------------------------------------------ #

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("landing"))


# ------------------------------------------------------------------ #
# Profile page presentation helpers                                   #
# ------------------------------------------------------------------ #

CATEGORY_BADGE_CLASSES = {
    "Food": "food",
    "Bills": "bills",
    "Transport": "transport",
    "Entertainment": "entertainment",
}


def get_badge_class(category):
    """Map an expense category name to its CSS badge/fill class suffix.

    Categories without a dedicated CSS class (Health, Shopping, Other,
    and any future/unknown category) fall back to "default", matching
    the classes defined in static/css/profile.css.
    """
    return CATEGORY_BADGE_CLASSES.get(category, "default")


def format_currency(amount):
    """Format a numeric amount as a rupee string, e.g. 12.5 -> "₹12.50"."""
    return f"₹{amount:.2f}"


def get_initials(name):
    """Derive up to 2 uppercase initials from a user's display name.

    Takes the first letter of the first two whitespace-separated words.
    Falls back to the first two letters if the name is a single word.
    """
    parts = name.split()
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    if parts:
        return parts[0][:2].upper()
    return "?"


def format_member_since(created_at):
    """Format a users.created_at value ("YYYY-MM-DD HH:MM:SS") as "March 2025"."""
    return datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S").strftime("%B %Y")


def format_transaction_date(date_str):
    """Format an expenses.date value ("YYYY-MM-DD") as "Jul 11, 2026"."""
    return datetime.strptime(date_str, "%Y-%m-%d").strftime("%b %d, %Y")


def build_profile_transactions(user_id):
    """Build the transactions list for the profile template.

    Fetches all expenses for the user (most recent first) and formats
    each into the date/description/category/amount/badge_class shape
    profile.html expects. Returns [] if the user has no expenses.
    """
    expenses = get_expenses_by_user(user_id)
    return [
        {
            "date": format_transaction_date(expense["date"]),
            "description": expense["description"],
            "category": expense["category"],
            "amount": format_currency(expense["amount"]),
            "badge_class": get_badge_class(expense["category"]),
        }
        for expense in expenses
    ]


def build_profile_stats(user_id):
    """Build the 3-item stats row: total spent, transaction count, top category."""
    summary = get_expense_summary(user_id)
    has_top = summary["top_category"] is not None
    return [
        {"label": "Total spent", "value": format_currency(summary["total"]), "sublabel": "All time"},
        {"label": "Transactions", "value": str(summary["count"]), "sublabel": "Logged"},
        {
            "label": "Top category",
            "value": summary["top_category"] if has_top else "—",
            "sublabel": f"{format_currency(summary['top_category_amount'])} spent" if has_top else "No expenses yet",
        },
    ]


def build_profile_categories(user_id):
    """Build the category breakdown list for the profile template."""
    breakdown = get_category_breakdown(user_id)
    return [
        {
            "name": row["category"],
            "amount": format_currency(row["total"]),
            "percent": row["percent"],
            "badge_class": get_badge_class(row["category"]),
        }
        for row in breakdown
    ]


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user_id = session["user_id"]
    user_row = get_user_by_id(user_id)

    user = {
        "name": user_row["name"],
        "email": user_row["email"],
        "initials": get_initials(user_row["name"]),
        "member_since": format_member_since(user_row["created_at"]),
    }
    stats = build_profile_stats(user_id)
    transactions = build_profile_transactions(user_id)
    categories = build_profile_categories(user_id)

    return render_template(
        "profile.html",
        user=user,
        stats=stats,
        transactions=transactions,
        categories=categories,
    )


@app.route("/expenses/add")
def add_expense():
    return "Add expense — coming in Step 7"


@app.route("/expenses/<int:id>/edit")
def edit_expense(id):
    return "Edit expense — coming in Step 8"


@app.route("/expenses/<int:id>/delete")
def delete_expense(id):
    return "Delete expense — coming in Step 9"


if __name__ == "__main__":
    app.run(debug=True, port=5001)
