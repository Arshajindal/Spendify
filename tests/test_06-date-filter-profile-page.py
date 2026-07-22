"""Tests for the Date Filter for Profile Page feature (Step 6).

Spec: .claude/specs/06-date-filter-profile-page.md

Scope (per spec "Routes" / "Rules for implementation" / "Definition of done"):
- GET /profile accepts optional `date_from` / `date_to` query params (ISO
  YYYY-MM-DD, inclusive bounds). No new routes are introduced.
- No params -> identical to the unfiltered / "All Time" view.
- Valid range -> summary stats, transaction list, and category breakdown are
  all restricted to that range.
- Malformed date value -> silently falls back to unfiltered (no error, no
  flash), the app must not crash.
- date_from > date_to -> flash "Start date must be before end date." and
  fall back to unfiltered.
- Zero expenses in range -> graceful zero/empty state, not an error.
- Auth guard on /profile is unchanged (redirect to /login when logged out),
  and must apply regardless of query params.

Notes on fixture design:
- database/db.py's get_db() always opens a hardcoded file path
  (database.db.DB_PATH), it does not read Flask's app.config. To get a
  clean, isolated database per test we monkeypatch database.db.DB_PATH to a
  per-test temp file and call init_db() against it, rather than relying on
  an in-memory `app.config["DATABASE"]` key (which this codebase does not
  use).
- There is no `create_expense` helper in database/db.py yet (expense
  creation is a Step 7 stub route), so test data is inserted directly via a
  small parameterized-SQL helper in this file, going through get_db() like
  the rest of the app does.
"""

from datetime import date

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


def _insert_expense(user_id, amount, category, date_str, description):
    """Insert a single expense row using parameterized SQL (test helper)."""
    conn = db_module.get_db()
    try:
        conn.execute(
            "INSERT INTO expenses (user_id, amount, category, date, description) "
            "VALUES (?, ?, ?, ?, ?)",
            (user_id, amount, category, date_str, description),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def user(app):
    """A single registered user, created directly against the isolated DB."""
    user_id = db_module.create_user("Test User", "filtertest@example.com", "testpass123")
    return {"id": user_id, "email": "filtertest@example.com", "password": "testpass123"}


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


@pytest.fixture
def expenses(user):
    """Three expenses spanning two months, used across filter scenarios.

    - Two expenses fall inside 2024-01-01..2024-01-31 ("in range").
    - One expense falls in February, outside that range ("out of range").
    """
    _insert_expense(user["id"], 12.50, "Food", "2024-01-05", "Groceries Alpha")
    _insert_expense(user["id"], 8.75, "Transport", "2024-01-15", "Bus Beta")
    _insert_expense(user["id"], 60.00, "Bills", "2024-02-10", "Electricity Gamma")
    return user


# ------------------------------------------------------------------ #
# Tests                                                                #
# ------------------------------------------------------------------ #

class TestProfileDateFilter:
    """Behavioral tests for GET /profile?date_from=&date_to=."""

    # -- No params: identical to unfiltered / All Time --------------- #

    def test_profile_no_query_params_returns_unfiltered_data(self, auth_client, expenses):
        """Spec DoD: 'Visiting /profile with no query params returns the
        same data as ... unfiltered, all expenses'."""
        response = auth_client.get("/profile")
        body = response.get_data(as_text=True)

        assert response.status_code == 200, "Unfiltered /profile should return 200"
        assert "Groceries Alpha" in body, "In-range Jan expense should be listed"
        assert "Bus Beta" in body, "In-range Jan expense should be listed"
        assert "Electricity Gamma" in body, "Feb expense should be listed with no filter"

        total = 12.50 + 8.75 + 60.00
        assert f"₹{total:.2f}" in body, "Total spent should sum every expense (₹81.25)"

        assert "Food" in body and "Transport" in body and "Bills" in body, (
            "Category breakdown should include every category when unfiltered"
        )
        assert "Start date must be before end date." not in body, (
            "No flash error expected when no filter is applied"
        )

    # -- Valid range: all three sections restricted ------------------- #

    def test_profile_valid_date_range_filters_all_sections(self, auth_client, expenses):
        """Spec DoD: 'Submitting a custom date range with valid date_from
        and date_to shows only expenses within that range in all three
        sections'."""
        response = auth_client.get(
            "/profile", query_string={"date_from": "2024-01-01", "date_to": "2024-01-31"}
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200

        # Transaction list restricted to the range (inclusive bounds).
        assert "Groceries Alpha" in body, "2024-01-05 is within the range"
        assert "Bus Beta" in body, "2024-01-15 is within the range"
        assert "Electricity Gamma" not in body, "2024-02-10 is outside the range"

        # Summary stats restricted to the range.
        in_range_total = 12.50 + 8.75
        assert f"₹{in_range_total:.2f}" in body, "Total spent should only include the two Jan expenses"

        # Category breakdown restricted to the range.
        assert "Food" in body, "Food category has an in-range expense"
        assert "Transport" in body, "Transport category has an in-range expense"
        assert "Bills" not in body, "Bills category has no in-range expense and should be excluded"

        # Filter bar reflects the active custom range (Templates section of the spec).
        assert 'value="2024-01-01"' in body, "date_from input should be pre-filled with the active value"
        assert 'value="2024-01-31"' in body, "date_to input should be pre-filled with the active value"

        assert "Start date must be before end date." not in body

    def test_profile_valid_date_range_boundary_dates_are_inclusive(self, auth_client, expenses):
        """Spec: date_from/date_to are 'inclusive lower/upper bound'."""
        response = auth_client.get(
            "/profile", query_string={"date_from": "2024-01-05", "date_to": "2024-01-05"}
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Groceries Alpha" in body, "An expense dated exactly on date_from must be included"
        assert "Bus Beta" not in body
        assert "Electricity Gamma" not in body
        assert f"₹{12.50:.2f}" in body

    # -- Malformed date: silent fallback, no crash --------------------- #

    def test_profile_malformed_date_falls_back_to_unfiltered(self, auth_client, expenses):
        """Spec DoD: 'Submitting a malformed date string (e.g.
        date_from=not-a-date) does not crash the app -- it silently falls
        back to the unfiltered view'."""
        response = auth_client.get("/profile", query_string={"date_from": "not-a-date"})
        body = response.get_data(as_text=True)

        assert response.status_code == 200, "A malformed date must not error the request"
        assert "Groceries Alpha" in body
        assert "Bus Beta" in body
        assert "Electricity Gamma" in body, "Malformed filter should fall back to showing everything"

        total = 12.50 + 8.75 + 60.00
        assert f"₹{total:.2f}" in body

        assert "Start date must be before end date." not in body, (
            "A malformed date is a silent fallback, not a validation error -- no flash expected"
        )

    @pytest.mark.parametrize(
        "bad_value",
        [
            "not-a-date",
            "2024-13-45",
            "01/01/2024",
            "2024-01-01' OR '1'='1",
            "'; DROP TABLE expenses; --",
        ],
        ids=[
            "non-date-text",
            "invalid-calendar-date",
            "wrong-format",
            "sql-injection-or-clause",
            "sql-injection-drop-table",
        ],
    )
    def test_profile_malformed_or_malicious_date_value_does_not_crash(
        self, auth_client, expenses, bad_value
    ):
        """Malformed values -- including SQL-injection-shaped strings --
        must be handled as 'malformed' per spec, never crash the app, and
        must never affect stored data (parameterized queries only)."""
        response = auth_client.get("/profile", query_string={"date_from": bad_value})
        assert response.status_code == 200, f"date_from={bad_value!r} must not crash /profile"

        # Data integrity check: a normal follow-up request still sees all
        # original data, proving no injection altered/dropped anything.
        follow_up = auth_client.get("/profile")
        follow_up_body = follow_up.get_data(as_text=True)
        assert follow_up.status_code == 200
        assert "Groceries Alpha" in follow_up_body
        assert "Bus Beta" in follow_up_body
        assert "Electricity Gamma" in follow_up_body

    # -- Inverted range: flash + fallback ------------------------------ #

    def test_profile_inverted_range_flashes_error_and_falls_back_to_unfiltered(
        self, auth_client, expenses
    ):
        """Spec rule: 'If date_from > date_to after validation, treat both
        as absent (no filter) and flash ... "Start date must be before end
        date."'."""
        response = auth_client.get(
            "/profile", query_string={"date_from": "2024-02-01", "date_to": "2024-01-01"}
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert "Start date must be before end date." in body, (
            "Inverted range must produce the exact spec'd flash message"
        )

        # Falls back to the unfiltered view.
        assert "Groceries Alpha" in body
        assert "Bus Beta" in body
        assert "Electricity Gamma" in body
        total = 12.50 + 8.75 + 60.00
        assert f"₹{total:.2f}" in body

    # -- Zero results: graceful empty state ---------------------------- #

    def test_profile_zero_expenses_in_range_shows_empty_state(self, auth_client, expenses):
        """Spec DoD: 'A user with no expenses in the selected range sees
        ₹0.00 total spent, 0 transactions, and an empty category breakdown
        -- no errors'."""
        response = auth_client.get(
            "/profile", query_string={"date_from": "2019-01-01", "date_to": "2019-01-31"}
        )
        body = response.get_data(as_text=True)

        assert response.status_code == 200, "A valid range with no matches must not error"
        assert "Groceries Alpha" not in body
        assert "Bus Beta" not in body
        assert "Electricity Gamma" not in body

        assert '<span class="profile-stat-value">₹0.00</span>' in body, (
            "Total spent should render as ₹0.00 for an empty range"
        )
        assert '<span class="profile-stat-value">0</span>' in body, (
            "Transaction count should render as 0 for an empty range"
        )
        assert "profile-breakdown-row" not in body, (
            "Category breakdown should be empty (no rows) for an empty range"
        )
        assert "Start date must be before end date." not in body, (
            "A valid, non-inverted empty range is not a validation error"
        )

    def test_profile_zero_expenses_for_new_user_shows_empty_state_unfiltered(self, auth_client, user):
        """No-expenses-at-all case (unfiltered) should also degrade
        gracefully, matching the same zero/empty-state expectations."""
        response = auth_client.get("/profile")
        body = response.get_data(as_text=True)

        assert response.status_code == 200
        assert '<span class="profile-stat-value">₹0.00</span>' in body
        assert '<span class="profile-stat-value">0</span>' in body
        assert "profile-breakdown-row" not in body

    # -- Auth guard: unchanged, applies regardless of query params ----- #

    def test_profile_unauthenticated_redirects_to_login(self, client):
        """Spec depends on Step 4/5 auth guard being unchanged for /profile."""
        response = client.get("/profile")
        assert response.status_code == 302, "Unauthenticated /profile must redirect"
        assert "/login" in response.headers.get("Location", ""), (
            "Unauthenticated /profile should redirect to the login page"
        )

    def test_profile_unauthenticated_with_filter_params_still_redirects_to_login(self, client):
        """The auth guard must apply before -- or regardless of -- date
        filter processing; query params must not bypass it."""
        response = client.get(
            "/profile", query_string={"date_from": "2024-01-01", "date_to": "2024-01-31"}
        )
        assert response.status_code == 302
        assert "/login" in response.headers.get("Location", "")

    def test_profile_unauthenticated_with_inverted_range_still_redirects_to_login(self, client):
        """Even an inverted range (which would normally flash) must not be
        processed for a logged-out visitor -- the auth guard comes first."""
        response = client.get(
            "/profile", query_string={"date_from": "2024-02-01", "date_to": "2024-01-01"}
        )
        assert response.status_code == 302
        assert "/login" in response.headers.get("Location", "")


# ------------------------------------------------------------------ #
# shift_months_back -- preset date math                                #
# ------------------------------------------------------------------ #

class TestShiftMonthsBack:
    """Unit tests for app.shift_months_back, which powers the 'Last 3
    Months' / 'Last 6 Months' presets. Covers the day-clamping edge case
    called out in its docstring (e.g. Mar 31 minus 1 month -> Feb 28)."""

    def test_shift_back_one_month_simple_case(self):
        assert app_module.shift_months_back(date(2026, 7, 22), 1) == date(2026, 6, 22)

    def test_shift_back_clamps_day_for_shorter_target_month(self):
        """Mar 31 - 1 month has no Feb 31, so it must clamp to Feb 28."""
        assert app_module.shift_months_back(date(2026, 3, 31), 1) == date(2026, 2, 28)

    def test_shift_back_clamps_day_for_leap_year_february(self):
        """2024 is a leap year, so Feb 29 is valid and should not clamp."""
        assert app_module.shift_months_back(date(2024, 3, 31), 1) == date(2024, 2, 29)

    def test_shift_back_crosses_year_boundary(self):
        assert app_module.shift_months_back(date(2026, 1, 15), 3) == date(2025, 10, 15)

    def test_shift_back_six_months_crosses_year_boundary(self):
        assert app_module.shift_months_back(date(2026, 1, 31), 6) == date(2025, 7, 31)
