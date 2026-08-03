"""Tests for the Add Expense feature (Step 7).

Spec: .claude/specs/07-add-expense.md

Scope (per spec "Routes" / "Rules for implementation" / "Definition of done"):
- GET /expenses/add renders the add-expense form, logged-in only.
- POST /expenses/add validates amount/category/date, inserts via
  database.db.create_expense, and redirects to /profile on success.
- Both methods redirect to /login when unauthenticated.
- Validation failures re-render the form with a flashed error and the
  submitted values preserved; no row is inserted.
- description is optional -- a blank value is stored as NULL.

Notes on fixture design:
- database/db.py's get_db() always opens a hardcoded file path
  (database.db.DB_PATH), it does not read Flask's app.config. To get a
  clean, isolated database per test we monkeypatch database.db.DB_PATH to a
  per-test temp file and call init_db() against it, matching the pattern in
  tests/test_06-date-filter-profile-page.py. There is no conftest.py in this
  repo, so fixtures are duplicated here rather than shared.
"""

import pytest

import app as app_module
import database.db as db_module


# ------------------------------------------------------------------ #
# Fixtures                                                             #
# ------------------------------------------------------------------ #

@pytest.fixture
def app(tmp_path, monkeypatch):
    """Point the app at a fresh, isolated SQLite file for this test only."""
    db_path = tmp_path / "test_spendly.db"
    monkeypatch.setattr(db_module, "DB_PATH", str(db_path))
    db_module.init_db()

    app_module.app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
    })
    yield app_module.app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def user(app):
    """A single registered user, created directly against the isolated DB."""
    user_id = db_module.create_user("Test User", "addexpense@example.com", "testpass123")
    return {"id": user_id, "email": "addexpense@example.com", "password": "testpass123"}


@pytest.fixture
def auth_client(client, user):
    """A test client logged in as `user` via the real /login route."""
    response = client.post(
        "/login",
        data={"email": user["email"], "password": user["password"]},
        follow_redirects=True,
    )
    assert response.status_code == 200, "Login via test client failed in fixture setup"
    return client


# ------------------------------------------------------------------ #
# create_expense -- unit tests                                        #
# ------------------------------------------------------------------ #

class TestCreateExpense:
    def test_create_expense_inserts_row_with_all_fields(self, app, user):
        expense_id = db_module.create_expense(user["id"], 50.0, "Food", "2026-03-20", "Lunch")

        conn = db_module.get_db()
        try:
            row = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        finally:
            conn.close()

        assert row is not None
        assert row["user_id"] == user["id"]
        assert row["amount"] == 50.0
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-20"
        assert row["description"] == "Lunch"

    def test_create_expense_with_none_description_stores_null(self, app, user):
        expense_id = db_module.create_expense(user["id"], 12.0, "Other", "2026-03-20", None)

        conn = db_module.get_db()
        try:
            row = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        finally:
            conn.close()

        assert row["description"] is None

    def test_create_expense_returns_matching_lastrowid(self, app, user):
        expense_id = db_module.create_expense(user["id"], 5.0, "Other", "2026-03-20", "")

        conn = db_module.get_db()
        try:
            row = conn.execute("SELECT id FROM expenses WHERE id = ?", (expense_id,)).fetchone()
        finally:
            conn.close()

        assert row["id"] == expense_id


# ------------------------------------------------------------------ #
# GET/POST /expenses/add -- route tests                               #
# ------------------------------------------------------------------ #

class TestAddExpense:
    # -- Auth guard ---------------------------------------------------- #

    def test_get_unauthenticated_redirects_to_login(self, client):
        response = client.get("/expenses/add")
        assert response.status_code == 302
        assert "/login" in response.headers.get("Location", "")

    def test_post_unauthenticated_redirects_to_login(self, client):
        response = client.post("/expenses/add", data={"amount": "10", "category": "Food", "date": "2026-03-20"})
        assert response.status_code == 302
        assert "/login" in response.headers.get("Location", "")

    # -- GET, authenticated --------------------------------------------- #

    def test_get_authenticated_renders_form(self, auth_client):
        response = auth_client.get("/expenses/add")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert '<form' in body
        assert 'method="POST"' in body

        for category in ["Food", "Bills", "Transport", "Entertainment", "Health", "Shopping", "Other"]:
            assert f'>{category}</option>' in body, f"{category} should be a selectable option"

    def test_get_authenticated_date_defaults_to_today(self, auth_client):
        from datetime import date as date_cls

        response = auth_client.get("/expenses/add")
        body = response.get_data(as_text=True)

        assert f'value="{date_cls.today().isoformat()}"' in body

    # -- POST, valid data -------------------------------------------------- #

    def test_post_valid_data_redirects_to_profile_and_inserts_row(self, auth_client, user):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "50.00", "category": "Food", "date": "2026-03-20", "description": "Lunch"},
        )
        assert response.status_code == 302
        assert "/profile" in response.headers.get("Location", "")

        conn = db_module.get_db()
        try:
            row = conn.execute(
                "SELECT * FROM expenses WHERE user_id = ?", (user["id"],)
            ).fetchone()
        finally:
            conn.close()

        assert row is not None
        assert row["amount"] == 50.0
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-20"
        assert row["description"] == "Lunch"

    def test_post_valid_data_appears_on_profile_page(self, auth_client):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "50.00", "category": "Food", "date": "2026-03-20", "description": "Lunch with friends"},
            follow_redirects=True,
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Lunch with friends" in body

    def test_post_no_description_saves_with_null(self, auth_client, user):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "10.00", "category": "Other", "date": "2026-03-20", "description": ""},
        )
        assert response.status_code == 302
        assert "/profile" in response.headers.get("Location", "")

        conn = db_module.get_db()
        try:
            row = conn.execute(
                "SELECT * FROM expenses WHERE user_id = ?", (user["id"],)
            ).fetchone()
        finally:
            conn.close()

        assert row["description"] is None

    # -- POST, invalid amount -------------------------------------------- #

    @pytest.mark.parametrize(
        "amount",
        ["", "0", "-5", "abc"],
        ids=["missing", "zero", "negative", "non-numeric"],
    )
    def test_post_invalid_amount_rerenders_form_with_error(self, auth_client, user, amount):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": amount, "category": "Food", "date": "2026-03-20", "description": ""},
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Enter an amount greater than 0." in body

        conn = db_module.get_db()
        try:
            row = conn.execute(
                "SELECT * FROM expenses WHERE user_id = ?", (user["id"],)
            ).fetchone()
        finally:
            conn.close()
        assert row is None, "No row should be inserted on validation failure"

    # -- POST, invalid category -------------------------------------------- #

    def test_post_invalid_category_rerenders_form_with_error(self, auth_client, user):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "10", "category": "Rent", "date": "2026-03-20", "description": ""},
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Select a valid category." in body

        conn = db_module.get_db()
        try:
            row = conn.execute(
                "SELECT * FROM expenses WHERE user_id = ?", (user["id"],)
            ).fetchone()
        finally:
            conn.close()
        assert row is None

    # -- POST, invalid date -------------------------------------------- #

    def test_post_invalid_date_rerenders_form_with_error(self, auth_client, user):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "10", "category": "Food", "date": "not-a-date", "description": ""},
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Enter a valid date." in body

        conn = db_module.get_db()
        try:
            row = conn.execute(
                "SELECT * FROM expenses WHERE user_id = ?", (user["id"],)
            ).fetchone()
        finally:
            conn.close()
        assert row is None

    # -- POST, validation failure preserves submitted values ------------ #

    def test_post_validation_failure_preserves_submitted_values(self, auth_client):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "0", "category": "Bills", "date": "2026-03-20", "description": "Rent"},
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert 'value="0"' in body
        assert 'value="2026-03-20"' in body
        assert 'value="Rent"' in body
        assert 'value="Bills" selected' in body
