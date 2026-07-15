# Spec: Profile Page Backend Routes

## Overview
This feature replaces the hardcoded demo data in the `/profile` view (built in Step 4) with real queries against the `users` and `expenses` tables. The user info card, summary stats, transaction history, and category breakdown must all reflect the actual logged-in user's data instead of static Python dicts. This is the "backend-connection" step explicitly called out in the Step 4 spec — the templates and layout are already correct and untouched; only the data source changes.

## Depends on
- Step 1: Database setup (schema must exist)
- Step 2: Registration (user accounts must be creatable)
- Step 3: Login + Logout (session must be set; `/profile` must be a protected route)
- Step 4: Profile Page (template and route scaffold with hardcoded data)

## Routes
No new routes. The existing `GET /profile` route is modified in place to source its context from the database instead of hardcoded values. Access level remains logged-in only (redirect to `/login` if not authenticated).

## Database changes
No schema changes. The existing `users` and `expenses` tables are sufficient. New read-only query functions are added to `database/db.py`:
- `get_user_by_id(user_id)` — fetch the user row for the info card (name, email, created_at)
- `get_expenses_by_user(user_id)` — fetch all expenses for a user, ordered by date descending, for the transaction history table
- `get_expense_summary(user_id)` — compute total spent, transaction count, and top category for the stats row
- `get_category_breakdown(user_id)` — compute per-category totals and percentages for the breakdown section

All functions use parameterized queries (`?` placeholders) via `get_db()`. No raw SQL in `app.py`.

## Templates
- **Create:** none
- **Modify:** none — `templates/profile.html` already consumes `user`, `stats`, `transactions`, and `categories` in the exact shape needed; only the Python-side data source changes in `app.py`

## Files to change
- `app.py` — replace hardcoded `user`, `stats`, `transactions`, and `categories` dicts in the `profile()` view with calls to the new `database/db.py` functions; compute `initials` and `member_since` (formatted from `created_at`) in the route, and map each expense's `category` to the correct `badge_class` (reuse the same category → CSS class mapping already implied by the hardcoded data: food, bills, transport, entertainment, default)
- `database/db.py` — add `get_user_by_id`, `get_expenses_by_user`, `get_expense_summary`, `get_category_breakdown`

## Files to create
None.

## New dependencies
No new dependencies.

## Rules for implementation
- No SQLAlchemy or ORMs — raw `sqlite3` via `get_db()` only
- Parameterised queries only — never string-format SQL, never f-strings in SQL
- Passwords hashed with werkzeug (no changes to auth in this step)
- Use CSS variables — never hardcode hex values
- All templates extend `base.html`
- All DB logic lives in `database/db.py` — no inline SQL in `app.py`
- Authentication guard unchanged: check `session.get("user_id")`; if absent, `redirect(url_for("login"))`
- Format currency values consistently with the existing hardcoded style (e.g. `₹12.50`) when building template context in `app.py`
- If a user has zero expenses, stats/transactions/categories must degrade gracefully (empty list / zero values) — do not error
- Category badge class mapping must stay consistent with the CSS classes already defined for `profile.css` (food, bills, transport, entertainment, default)

## Definition of done
- [ ] Visiting `/profile` without being logged in redirects to `/login`
- [ ] Visiting `/profile` while logged in returns HTTP 200
- [ ] The user info card shows the real logged-in user's name, email, and initials
- [ ] The "member since" date is derived from the user's actual `created_at` value
- [ ] The summary stats row shows the real total spent, real transaction count, and real top category for that user
- [ ] The transaction history table lists the logged-in user's actual expenses (not another user's)
- [ ] The category breakdown section reflects real per-category totals and percentages that sum to 100%
- [ ] Logging in as a different seeded user shows different profile data (proves the queries are scoped by `user_id`)
- [ ] A user with zero expenses sees an empty/zero-state profile page instead of a server error
- [ ] No hardcoded demo data (`"Demo User"`, `"demo@spendly.com"`, etc.) remains in `app.py`
