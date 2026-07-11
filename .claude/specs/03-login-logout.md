# Spec: Login and Logout

## Overview
Implement session-based authentication so registered users can sign in and out of Spendly. This step upgrades the existing stub `GET /login` route (currently render-only) into a fully functional form that accepts a POST, verifies credentials against the `users` table, and starts a Flask session. It also implements the `GET /logout` stub, clearing the session and returning the user to the login page. This is the foundation every future authenticated route (profile, expenses) will depend on to know who is signed in.

## Depends on
- Step 01 — Database setup (`users` table, `get_db()`)
- Step 02 — Registration (`create_user()`, users exist to log in with)

## Routes
- `GET /login` — render login form — public (already exists, minor template cleanup only)
- `POST /login` — verify email/password, start session, redirect to `/profile` — public
- `GET /logout` — clear session, flash confirmation, redirect to `/login` — logged-in (replaces stub)

## Database changes
No new tables or columns. The existing `users` table (id, name, email, password_hash, created_at) covers all requirements.

A new DB helper must be added to `database/db.py`:
- `get_user_by_email(email)` — returns the full user row (id, name, email, password_hash) for the given email, or `None` if no match. Used to verify credentials during login.

## Templates
- **Modify:** `templates/login.html`
  - Change the form `action` from the hardcoded `/login` to `url_for('login')`
  - Remove the local `{% if error %}` block — rely on `base.html`'s existing flashed-message rendering, matching the pattern already used in `register.html`
  - Keep all existing visual design
- **Modify:** `templates/base.html`
  - Nav links must reflect session state: when no user is logged in, show the existing "Sign in" / "Get started" links; when a user is logged in, show a "Profile" link (`url_for('profile')`) and a "Logout" link (`url_for('logout')`) instead

## Files to change
- `app.py` — upgrade `login()` to handle `GET` and `POST`; add credential verification, session creation, and flash/redirect logic; upgrade `logout()` to clear the session and redirect
- `database/db.py` — add `get_user_by_email()` helper
- `templates/login.html` — wire up form action and remove redundant error block
- `templates/base.html` — conditionally render nav links based on session state

## Files to create
None.

## New dependencies
No new dependencies. Uses Flask's built-in `session`, `flash`, `redirect`, `url_for`, and `werkzeug.security.check_password_hash` (werkzeug is already installed).

## Rules for implementation
- No SQLAlchemy or ORMs
- Parameterised queries only — never use f-strings in SQL
- Verify passwords with `werkzeug.security.check_password_hash` — never compare plaintext
- On successful login, store at minimum `session["user_id"]` (and `session["user_name"]` for display); do not store the password hash in the session
- Server-side validation on `POST /login` must check:
  1. Both fields are non-empty
  2. Email exists in `users` (via `get_user_by_email`)
  3. Password matches the stored hash
- On any validation failure, flash a generic error (e.g. "Invalid email or password") and re-render the form — do not reveal whether the email exists
- On success, redirect to `url_for('profile')` (the profile route remains a stub per the roadmap — do not implement it in this step)
- `GET /logout` must call `session.clear()`, flash a confirmation message, and redirect to `url_for('login')`
- Use `abort(405)` if an unsupported HTTP method reaches `/login`
- Do not implement `/profile`, `/expenses/add`, `/expenses/<id>/edit`, or `/expenses/<id>/delete` — they remain stubs out of scope for this step
- All templates extend `base.html`
- Use CSS variables — never hardcode hex values
- Use `url_for()` for every internal link — never hardcode URLs

## Definition of done
- [ ] `GET /login` renders the login form without errors
- [ ] Submitting valid credentials starts a session and redirects to `/profile`
- [ ] Submitting an unknown email flashes "Invalid email or password", no session created
- [ ] Submitting a known email with the wrong password flashes "Invalid email or password", no session created
- [ ] Submitting with an empty field re-renders the form with a validation error
- [ ] After login, the navbar shows "Profile" and "Logout" instead of "Sign in" / "Get started"
- [ ] Visiting `/logout` while logged in clears the session and redirects to `/login` with a confirmation message
- [ ] After logout, the navbar reverts to "Sign in" / "Get started"
- [ ] No plaintext password ever appears in the session or is logged
