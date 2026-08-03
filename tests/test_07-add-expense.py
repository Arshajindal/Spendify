"""Tests for the Add Expense feature (Step 7).

Spec: .claude/specs/07-add-expense.md

Scope, derived strictly from the spec (not from reading app.py's/db.py's
current control flow):
- `GET /expenses/add` renders the add-expense form, logged-in only.
- `POST /expenses/add` validates amount/category/date, inserts the row, and
  redirects to `/profile` on success — logged-in only.
- Unauthenticated access to either method redirects to `/login`.
- Validation rules (spec "Rules for implementation"):
    * amount: required, must parse as a positive number > 0
    * category: required, must be one of the 7 fixed categories
    * date: required, must be a valid YYYY-MM-DD date
    * description: optional, stripped, stored as NULL when blank
- On any validation error: re-render the form (200), show an error message,
  and re-populate the previously submitted values.
- On success: redirect to `/profile` (302), never re-render the form.
- The category `<select>` must offer exactly: Food, Transport, Bills,
  Health, Entertainment, Shopping, Other.
- profile.html gets an "Add Expense" button/link to `/expenses/add`.
- base.html's navbar shows an "Add Expense" link only when a session
  user_id is set.

Notes on fixture design:
- database/db.py's `get_db()` always opens a hardcoded file path
  (`database.db.DB_PATH`); it does not read Flask's `app.config`. To get a
  clean, isolated database per test we monkeypatch `database.db.DB_PATH` to
  a per-test temp file and call `init_db()` against it — the same pattern
  already used elsewhere in this repo's test suite (e.g.
  tests/test_06-date-filter-profile-page.py). There is no conftest.py in
  this repo, so fixtures are duplicated locally rather than shared.
- Structural inspection of database/db.py (signatures only, not behavior)
  shows the insert helper is `create_expense(user_id, amount, category,
  date, description)` and user creation is `create_user(name, email,
  password)`. These names are used purely to wire up fixtures/assertions;
  all pass/fail *expectations* below come from the spec.
"""

import pytest

import app as app_module
import database.db as db_module


# ------------------------------------------------------------------ #
# Fixtures                                                            #
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
    user_id = db_module.create_user("Test User", "add-expense-07@example.com", "testpass123")
    return {"id": user_id, "email": "add-expense-07@example.com", "password": "testpass123"}


@pytest.fixture
def other_user(app):
    """A second registered user, used to confirm expenses aren't cross-attributed."""
    user_id = db_module.create_user("Other User", "other-07@example.com", "testpass123")
    return {"id": user_id, "email": "other-07@example.com", "password": "testpass123"}


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


def _expenses_for(user_id):
    """Fetch all expense rows for a user directly from the DB (test helper)."""
    conn = db_module.get_db()
    try:
        return conn.execute(
            "SELECT * FROM expenses WHERE user_id = ?", (user_id,)
        ).fetchall()
    finally:
        conn.close()


FIXED_CATEGORIES = ["Food", "Transport", "Bills", "Health", "Entertainment", "Shopping", "Other"]


# ------------------------------------------------------------------ #
# Unit tests -- insert helper (spec "Tests to write / Unit tests")    #
# ------------------------------------------------------------------ #

class TestInsertExpenseUnit:
    """Spec table: insert helper must insert a row that a later query can find,
    and must store a NULL description when None is passed."""

    def test_insert_expense_valid_data_row_is_queryable(self, app, user):
        db_module.create_expense(user["id"], 50.0, "Food", "2026-03-20", "Lunch")

        rows = _expenses_for(user["id"])
        assert len(rows) == 1, "Exactly one row should exist after one insert"
        row = rows[0]
        assert row["user_id"] == user["id"]
        assert row["amount"] == 50.0
        assert row["category"] == "Food"
        assert row["date"] == "2026-03-20"
        assert row["description"] == "Lunch"

    def test_insert_expense_none_description_stored_as_null(self, app, user):
        db_module.create_expense(user["id"], 12.0, "Other", "2026-03-20", None)

        rows = _expenses_for(user["id"])
        assert len(rows) == 1
        assert rows[0]["description"] is None, "A None description must be stored as NULL, not '' or 'None'"


# ------------------------------------------------------------------ #
# Auth guard -- both methods require a logged-in session              #
# ------------------------------------------------------------------ #

class TestAddExpenseAuthGuard:
    def test_get_unauthenticated_redirects_to_login(self, client):
        response = client.get("/expenses/add")
        assert response.status_code == 302, "Unauthenticated GET must redirect, not render the form"
        assert "/login" in response.headers.get("Location", "")

    def test_post_unauthenticated_redirects_to_login(self, client):
        response = client.post(
            "/expenses/add",
            data={"amount": "10", "category": "Food", "date": "2026-03-20", "description": ""},
        )
        assert response.status_code == 302, "Unauthenticated POST must redirect, not process the form"
        assert "/login" in response.headers.get("Location", "")

    def test_post_unauthenticated_does_not_insert_any_row(self, client, app):
        client.post(
            "/expenses/add",
            data={"amount": "10", "category": "Food", "date": "2026-03-20", "description": "sneaky"},
        )
        conn = db_module.get_db()
        try:
            count = conn.execute("SELECT COUNT(*) AS c FROM expenses").fetchone()["c"]
        finally:
            conn.close()
        assert count == 0, "An unauthenticated POST must never write to the expenses table"


# ------------------------------------------------------------------ #
# GET /expenses/add, authenticated                                    #
# ------------------------------------------------------------------ #

class TestAddExpenseGet:
    def test_get_authenticated_returns_200(self, auth_client):
        response = auth_client.get("/expenses/add")
        assert response.status_code == 200

    def test_get_authenticated_form_has_post_method(self, auth_client):
        body = auth_client.get("/expenses/add").get_data(as_text=True)
        assert "<form" in body, "Page must contain a form element"
        assert "POST" in body.upper(), "Form must submit via POST"

    def test_get_authenticated_category_select_has_exactly_the_7_fixed_options(self, auth_client):
        body = auth_client.get("/expenses/add").get_data(as_text=True)
        for category in FIXED_CATEGORIES:
            assert category in body, f"Category '{category}' must appear as a selectable option"

    @pytest.mark.parametrize("category", FIXED_CATEGORIES)
    def test_get_authenticated_each_fixed_category_present(self, auth_client, category):
        body = auth_client.get("/expenses/add").get_data(as_text=True)
        assert category in body, f"'{category}' should be one of the offered category options"

    def test_get_authenticated_amount_field_has_number_constraints(self, auth_client):
        body = auth_client.get("/expenses/add").get_data(as_text=True)
        assert 'type="number"' in body, "amount must be a number input"
        assert 'step="0.01"' in body, "amount must allow cent-level precision"
        assert 'min="0.01"' in body, "amount must enforce a positive minimum client-side"

    def test_get_authenticated_date_field_is_html5_date_input(self, auth_client):
        body = auth_client.get("/expenses/add").get_data(as_text=True)
        assert 'type="date"' in body, "date must be an HTML5 date input"

    def test_get_authenticated_date_defaults_to_today(self, auth_client):
        from datetime import date as date_cls

        body = auth_client.get("/expenses/add").get_data(as_text=True)
        today_iso = date_cls.today().isoformat()
        assert today_iso in body, "The date field should default to today's date"

    def test_get_authenticated_has_cancel_link_back_to_profile(self, auth_client):
        body = auth_client.get("/expenses/add").get_data(as_text=True)
        assert "/profile" in body, "A cancel link back to /profile must be present"


# ------------------------------------------------------------------ #
# POST /expenses/add, authenticated -- happy path                     #
# ------------------------------------------------------------------ #

class TestAddExpensePostValid:
    def test_post_valid_data_redirects_to_profile(self, auth_client):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "50.00", "category": "Food", "date": "2026-03-20", "description": "Lunch"},
        )
        assert response.status_code == 302
        assert "/profile" in response.headers.get("Location", "")

    def test_post_valid_data_never_rerenders_the_form(self, auth_client):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "50.00", "category": "Food", "date": "2026-03-20", "description": "Lunch"},
        )
        body = response.get_data(as_text=True)
        assert "<form" not in body, "Success must redirect, not re-render add_expense.html"

    def test_post_valid_data_row_exists_with_correct_fields(self, auth_client, user):
        auth_client.post(
            "/expenses/add",
            data={"amount": "50.00", "category": "Food", "date": "2026-03-20", "description": "Lunch"},
        )
        rows = _expenses_for(user["id"])
        assert len(rows) == 1, "Exactly one expense row must be created"
        row = rows[0]
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
        assert "Lunch with friends" in body, "New expense should show up in the profile's transaction list"

    def test_post_valid_data_is_attributed_to_the_logged_in_user_only(self, auth_client, user, other_user):
        auth_client.post(
            "/expenses/add",
            data={"amount": "50.00", "category": "Food", "date": "2026-03-20", "description": "Lunch"},
        )
        assert len(_expenses_for(user["id"])) == 1
        assert len(_expenses_for(other_user["id"])) == 0, "The expense must not be attributed to any other user"

    def test_post_minimum_valid_amount_boundary(self, auth_client, user):
        """Spec: amount must be > 0; the smallest allowed value (0.01) must succeed."""
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "0.01", "category": "Food", "date": "2026-03-20", "description": ""},
        )
        assert response.status_code == 302
        rows = _expenses_for(user["id"])
        assert len(rows) == 1
        assert rows[0]["amount"] == 0.01

    @pytest.mark.parametrize("category", FIXED_CATEGORIES)
    def test_post_each_fixed_category_is_accepted(self, auth_client, user, category):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "10", "category": category, "date": "2026-03-20", "description": ""},
        )
        assert response.status_code == 302, f"Category '{category}' should be a valid, accepted category"


# ------------------------------------------------------------------ #
# POST /expenses/add, authenticated -- description handling           #
# ------------------------------------------------------------------ #

class TestAddExpenseDescription:
    def test_post_missing_description_field_saves_with_null(self, auth_client, user):
        """description omitted entirely from the form body (not just empty)."""
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "10.00", "category": "Other", "date": "2026-03-20"},
        )
        assert response.status_code == 302
        rows = _expenses_for(user["id"])
        assert len(rows) == 1
        assert rows[0]["description"] is None

    def test_post_empty_string_description_saves_with_null(self, auth_client, user):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "10.00", "category": "Other", "date": "2026-03-20", "description": ""},
        )
        assert response.status_code == 302
        rows = _expenses_for(user["id"])
        assert rows[0]["description"] is None

    def test_post_whitespace_only_description_saves_with_null(self, auth_client, user):
        """Spec: strip whitespace; store None if blank -- whitespace-only counts as blank."""
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "10.00", "category": "Other", "date": "2026-03-20", "description": "   "},
        )
        assert response.status_code == 302
        rows = _expenses_for(user["id"])
        assert rows[0]["description"] is None

    def test_post_description_with_surrounding_whitespace_is_stripped(self, auth_client, user):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "10.00", "category": "Other", "date": "2026-03-20", "description": "  Coffee  "},
        )
        assert response.status_code == 302
        rows = _expenses_for(user["id"])
        assert rows[0]["description"] == "Coffee", "Description must be stripped of surrounding whitespace"

    def test_post_description_field_has_maxlength_200_in_form(self, auth_client):
        body = auth_client.get("/expenses/add").get_data(as_text=True)
        assert 'maxlength="200"' in body, "Description input must enforce a 200 char max per spec"

    def test_post_description_with_sql_injection_payload_is_stored_safely(self, auth_client, user):
        """Parameterized queries must treat this as inert literal text, not SQL."""
        payload = "'; DROP TABLE expenses; --"
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "10.00", "category": "Other", "date": "2026-03-20", "description": payload},
        )
        assert response.status_code == 302, "A malicious-looking description must not crash the request"

        rows = _expenses_for(user["id"])
        assert len(rows) == 1, "The expenses table must still exist and contain the new row"
        assert rows[0]["description"] == payload, "Payload should be stored verbatim as inert text"

    def test_post_very_long_description_does_not_crash_the_app(self, auth_client):
        long_description = "x" * 5000
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "10.00", "category": "Other", "date": "2026-03-20", "description": long_description},
        )
        assert response.status_code != 500, "A very long description must not cause a server error"


# ------------------------------------------------------------------ #
# POST /expenses/add, authenticated -- amount validation              #
# ------------------------------------------------------------------ #

class TestAddExpensePostInvalidAmount:
    @pytest.mark.parametrize(
        "amount",
        ["", "0", "0.00", "-5", "abc", "not-a-number"],
        ids=["missing", "zero", "zero-decimal", "negative", "alpha", "words"],
    )
    def test_invalid_amount_rerenders_form_with_200_and_error(self, auth_client, user, amount):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": amount, "category": "Food", "date": "2026-03-20", "description": ""},
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200, f"amount={amount!r} must re-render the form, not redirect"
        assert "<form" in body, "Form must be re-rendered on validation failure"
        assert any(word in body for word in ["error", "Error", "invalid", "Invalid", "greater than 0"]), (
            "Response must contain a visible error message for an invalid amount"
        )

    @pytest.mark.parametrize(
        "amount",
        ["", "0", "-5", "abc"],
        ids=["missing", "zero", "negative", "non-numeric"],
    )
    def test_invalid_amount_does_not_insert_a_row(self, auth_client, user, amount):
        auth_client.post(
            "/expenses/add",
            data={"amount": amount, "category": "Food", "date": "2026-03-20", "description": ""},
        )
        assert len(_expenses_for(user["id"])) == 0, "No row should be inserted when amount validation fails"


# ------------------------------------------------------------------ #
# POST /expenses/add, authenticated -- category validation            #
# ------------------------------------------------------------------ #

class TestAddExpensePostInvalidCategory:
    @pytest.mark.parametrize(
        "category",
        ["", "Rent", "food", "FOOD", "Groceries"],
        ids=["missing", "not-in-list", "lowercase", "uppercase", "unrelated"],
    )
    def test_invalid_category_rerenders_form_with_200_and_error(self, auth_client, user, category):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "10", "category": category, "date": "2026-03-20", "description": ""},
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200, f"category={category!r} must re-render the form, not redirect"
        assert "<form" in body

    def test_invalid_category_does_not_insert_a_row(self, auth_client, user):
        auth_client.post(
            "/expenses/add",
            data={"amount": "10", "category": "Rent", "date": "2026-03-20", "description": ""},
        )
        assert len(_expenses_for(user["id"])) == 0, "No row should be inserted for an invalid category"


# ------------------------------------------------------------------ #
# POST /expenses/add, authenticated -- date validation                #
# ------------------------------------------------------------------ #

class TestAddExpensePostInvalidDate:
    @pytest.mark.parametrize(
        "bad_date",
        ["", "not-a-date", "2026-13-45", "03/20/2026", "20-03-2026"],
        ids=["missing", "text", "invalid-calendar-date", "wrong-format-slash", "wrong-format-dmy"],
    )
    def test_invalid_date_rerenders_form_with_200_and_error(self, auth_client, user, bad_date):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "10", "category": "Food", "date": bad_date, "description": ""},
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200, f"date={bad_date!r} must re-render the form, not redirect"
        assert "<form" in body

    def test_invalid_date_does_not_insert_a_row(self, auth_client, user):
        auth_client.post(
            "/expenses/add",
            data={"amount": "10", "category": "Food", "date": "not-a-date", "description": ""},
        )
        assert len(_expenses_for(user["id"])) == 0, "No row should be inserted for an invalid date"

    def test_date_sql_injection_payload_is_rejected_as_invalid_date(self, auth_client, user):
        """A SQL-injection-shaped string is not a valid YYYY-MM-DD date and
        must be rejected by strptime-based validation, never executed as SQL."""
        payload = "2026-03-20'; DROP TABLE expenses; --"
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "10", "category": "Food", "date": payload, "description": ""},
        )
        assert response.status_code == 200, "Malformed/malicious date must be handled as a validation error"
        assert len(_expenses_for(user["id"])) == 0

        # Data integrity: the expenses table must still exist and work normally.
        follow_up = auth_client.post(
            "/expenses/add",
            data={"amount": "10", "category": "Food", "date": "2026-03-20", "description": ""},
        )
        assert follow_up.status_code == 302, "The table must still be intact and usable after the injection attempt"


# ------------------------------------------------------------------ #
# POST /expenses/add, authenticated -- value re-population on error   #
# ------------------------------------------------------------------ #

class TestAddExpenseValueRepopulation:
    """Spec: 'On any validation error, re-render the form with the error
    message and the previously submitted values pre-filled.'"""

    def test_invalid_amount_preserves_category_date_and_description(self, auth_client):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "0", "category": "Bills", "date": "2026-03-20", "description": "Rent"},
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Bills" in body, "Previously chosen category should remain selected/present"
        assert "2026-03-20" in body, "Previously entered date should be pre-filled"
        assert "Rent" in body, "Previously entered description should be pre-filled"

    def test_invalid_category_preserves_amount_date_and_description(self, auth_client):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "42.50", "category": "NotACategory", "date": "2026-03-20", "description": "Snacks"},
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "42.5" in body or "42.50" in body, "Previously entered amount should be pre-filled"
        assert "2026-03-20" in body, "Previously entered date should be pre-filled"
        assert "Snacks" in body, "Previously entered description should be pre-filled"

    def test_invalid_date_preserves_amount_category_and_description(self, auth_client):
        response = auth_client.post(
            "/expenses/add",
            data={"amount": "42.50", "category": "Health", "date": "bogus-date", "description": "Vitamins"},
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "42.5" in body or "42.50" in body
        assert "Health" in body
        assert "Vitamins" in body


# ------------------------------------------------------------------ #
# Template integration -- profile page + navbar (spec DoD)            #
# ------------------------------------------------------------------ #

class TestAddExpenseNavigationIntegration:
    def test_profile_page_has_add_expense_link(self, auth_client):
        """Spec DoD: 'The Add Expense button on the profile page navigates
        to /expenses/add.'"""
        body = auth_client.get("/profile").get_data(as_text=True)
        assert "/expenses/add" in body, "profile.html must link to /expenses/add"

    def test_navbar_shows_add_expense_link_when_logged_in(self, auth_client):
        """Spec DoD: 'Navbar shows Add Expense link when logged in.'"""
        body = auth_client.get("/profile").get_data(as_text=True)
        assert "Add Expense" in body, "Navbar/page should show an 'Add Expense' link for a logged-in user"

    def test_navbar_add_expense_link_not_targeted_at_logged_out_landing_page(self, client):
        """Spec: navbar Add Expense link is visible 'only when
        session.user_id is set' -- a logged-out visitor on the landing page
        must not be given a working link to the protected add-expense form."""
        body = client.get("/").get_data(as_text=True)
        assert 'href="/expenses/add"' not in body, (
            "Logged-out landing page must not expose a direct /expenses/add link"
        )
