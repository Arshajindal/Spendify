import sqlite3

from flask import Flask, abort, flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from database.db import create_user, get_db, get_user_by_email, init_db, seed_db

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


@app.route("/profile")
def profile():
    if not session.get("user_id"):
        return redirect(url_for("login"))

    user = {
        "name": "Demo User",
        "email": "demo@spendly.com",
        "initials": "DU",
        "member_since": "March 2025",
    }
    stats = [
        {"label": "Total spent", "value": "₹208.74", "sublabel": "All time"},
        {"label": "Transactions", "value": "8", "sublabel": "Logged"},
        {"label": "Top category", "value": "Bills", "sublabel": "₹60.00 spent"},
    ]
    transactions = [
        {"date": "Jul 11, 2026", "description": "Grocery shopping", "category": "Food", "amount": "₹12.50", "badge_class": "food"},
        {"date": "Jul 09, 2026", "description": "Electricity bill", "category": "Bills", "amount": "₹60.00", "badge_class": "bills"},
        {"date": "Jul 07, 2026", "description": "Bus fare", "category": "Transport", "amount": "₹8.75", "badge_class": "transport"},
        {"date": "Jul 05, 2026", "description": "Movie tickets", "category": "Entertainment", "amount": "₹15.99", "badge_class": "entertainment"},
        {"date": "Jul 02, 2026", "description": "Pharmacy - medicines", "category": "Health", "amount": "₹45.00", "badge_class": "default"},
    ]
    categories = [
        {"name": "Bills", "amount": "₹60.00", "percent": 29, "badge_class": "bills"},
        {"name": "Health", "amount": "₹45.00", "percent": 22, "badge_class": "default"},
        {"name": "Food", "amount": "₹34.80", "percent": 17, "badge_class": "food"},
        {"name": "Shopping", "amount": "₹34.20", "percent": 16, "badge_class": "default"},
        {"name": "Entertainment", "amount": "₹15.99", "percent": 8, "badge_class": "entertainment"},
    ]

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
