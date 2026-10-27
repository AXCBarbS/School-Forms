# SF4 Portal – District & School Enrollment Data Management (Django)

Django 5.2 web system for SDO Benguet. Users register with a DepEd email, verify with an emailed OTP, are approved by
their district administrator, then enter SF4 enrollment figures only for schools in their own district.

Built from the consolidated workbook: **14 districts, 430 schools**. Each school's form contains the workbook's actual
fields: male/female counts for Kinder–Grade 6, SNED (ES), Grades 7–10, SNED (JHS), Grade 11/12 ACAD/TVL/SPORTS. All
totals are calculated by the application with the same rules as the workbook formulas
(see `docs/RECONCILIATION.md`).

## 1. Quick start (development)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # for local use set DJANGO_DEBUG=1 in .env
python manage.py migrate
python manage.py import_master /path/to/Consolidated_2026-2027_SF4.xlsx --dry-run          # validate first
python manage.py import_master /path/to/Consolidated_2026-2027_SF4.xlsx --with-enrollment --reconcile
python manage.py createsuperuser                  # system administrator (email + password)
python manage.py create_district_admin juan@deped.gov.ph "Juan Dela Cruz" "La Trinidad"   # one per district
python manage.py runserver
python manage.py test                             # 93 tests
```
With `DJANGO_DEBUG=1` and no `EMAIL_HOST`, OTP emails are printed in the console (development only).
`--with-enrollment` loads the workbook figures as **pre-filled drafts** ("Pre-filled – needs review"); omit it to start
every school at "Not Started". Portal-entered or submitted data is never overwritten by a re-import.

## 2. Workflow

Register → email OTP → (district admin approves) → sign in → district dashboard (own schools only, search + status
filter) → open school → enter/save draft (resumable) → Save and review → Submit (confirmation) → locked.
District administrators and system administrators can reopen a submitted record.

Status per school: **Not Started** (no record), **Pre-filled – needs review** (imported, untouched), **In Progress**
(draft edited in portal), **Completed** (submitted).

## 3. Roles and permissions

| Capability | District user | District admin | System admin |
|---|:-:|:-:|:-:|
| See / edit schools of own district | ✔ | ✔ | all districts |
| Submit a school record | ✔ | ✔ | ✔ |
| Reopen a submitted record | – | own district | ✔ |
| Approve / reject / suspend users | – | ordinary users of own district | everyone except self |
| Progress report, audit log | – | own district | all |
| Export Excel | own district | own district | all / filter |
| Import workbook, Django admin (districts, schools, accounts) | – | – | ✔ |

Authorization is enforced on the server in `enrollment/access.py`; other districts' schools return **404**, so IDs
cannot be probed by editing URLs, form fields or `?district=` parameters.

## 4. Security features

PBKDF2 password hashing (10-char minimum + Django validators) · OTPs stored only as HMAC-SHA256 (keyed with
`SECRET_KEY`), 10-minute expiry, 60-second resend cooldown, 5 attempts, 5 sends/hour, only newest code valid ·
exact-match DepEd domain allow-list (`DEPED_EMAIL_DOMAINS`; `mydeped.com` and `deped.gov.ph.evil.com` are rejected) ·
login lockout (5 failures / 15 min per IP+email) and per-IP limits on register/OTP/resend/reset · accounts that are
unverified, unapproved, rejected or suspended cannot authenticate, and live sessions die when status changes ·
CSRF, POST-only state changes, 8-hour sessions, secure/HttpOnly cookies, HSTS and SSL redirect in production ·
secrets only from environment variables; the app refuses to start in production without `DJANGO_SECRET_KEY` ·
audit log (no passwords, OTPs or enrollment values) · upload checks (.xlsx, 15 MB, parse errors handled).

## 5. Production deployment

1. Server with Python 3.12+, PostgreSQL, Nginx, valid HTTPS certificate.
2. `pip install -r requirements.txt`; create `.env` from `.env.example`: `DJANGO_DEBUG=0`, a long random
   `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`, `DB_*`, SMTP `EMAIL_*`,
   `DJANGO_BEHIND_PROXY=1` only if Nginx sets `X-Forwarded-Proto`.
3. `python manage.py migrate && python manage.py collectstatic --noinput && python manage.py check --deploy`
4. Run `gunicorn config.wsgi:application --workers 3 --bind 127.0.0.1:8000` under systemd; Nginx proxies to it and
   sets `X-Forwarded-Proto`. WhiteNoise serves static files.
5. **Rate limits use Django's cache. The default LocMemCache is per process;** with several workers configure a shared
   cache (Redis) in `CACHES` or the limits are per worker.
6. Bootstrap is loaded from a CDN. For an offline/intranet deployment, download Bootstrap 5.3.3 into `static/` and
   change the two URLs in `templates/base.html`.

## 6. Backup and restore

PostgreSQL: `pg_dump -Fc -U $DB_USER $DB_NAME > sf4_$(date +%F).dump` (schedule daily, store off-server, encrypt).
Restore: `createdb sf4_restore && pg_restore -d sf4_restore sf4_YYYY-MM-DD.dump`, point `.env` at it, run
`python manage.py migrate --check`. SQLite (dev only): copy `db.sqlite3` while the server is stopped.
Test a restore regularly.

## 7. User guide (short)

**Teacher / school head:** Register with your DepEd email and district → enter the 6-digit code → wait for approval →
sign in → choose your school → type Male/Female counts (blank = not offered; use 0 when a level exists but has no
learners; totals update as you type) → *Save draft* any time → *Save and review* → *Submit…* and tick the confirmation.
**District admin:** *Users* → approve/reject registrations of your district; *Progress* for completion by status;
*Export Excel* for your district; reopen a submitted school from its review page if corrections are needed.
**System admin:** *Import* (dry run first), *Admin* for districts/schools/accounts, audit log for all districts.

## 8. Project layout

`config/` settings & urls · `accounts/` user model, OTP, registration/login, throttling · `organization/` District,
School, Excel importer + `import_master` · `enrollment/` schema (workbook fields), records, calculations, entry/review/
submit views, manage views, Excel export · `audit/` audit log · `templates/`, `static/` · `docs/RECONCILIATION.md`.
Models: `District`, `School`, `User`, `OTPChallenge`, `EnrollmentRecord` (unique per school and school year),
`EnrollmentEntry` (one row per level, unique per record), `AuditLog`.

## 9. Assumptions and limitations (please review)

* **DepEd email domains:** the default allow-list contains only `deped.gov.ph`. I could not verify the complete list of
  official DepEd domains; add any others to `DEPED_EMAIL_DOMAINS`.
* **District membership** cannot be proven by email, so approval by a district administrator is required. The first
  district administrator of each district must be created by a system administrator (`create_district_admin`).
* **Access is per district, not per school:** the workbook assigns schools to districts only, so every approved user
  of a district may edit any school of that district. Per-school assignment would need a new mapping.
* **Fields:** the workbook contains only enrollment counts per grade/strand and sex (plus school ID, name, district,
  sector). No other fields were invented. All 430 schools are "Public"; no private schools exist in the workbook.
* **Typed totals in the source** (3 schools) disagree with their own counts; the portal calculates (see reconciliation).
* **One school year** is active at a time (`CURRENT_SCHOOL_YEAR`); the model supports several years.
* **Users cannot change their own district;** a system admin edits it in Django admin.
* **Not tested here:** PostgreSQL, real SMTP delivery, multi-worker rate limiting, browsers and the JavaScript that
  shows live totals (the server recomputes everything on save and review), accessibility audit, load testing.
  The 93 automated tests ran on SQLite with the in-memory email backend.
* The Data Privacy Act of 2012 compliance requires organisational measures (retention policy, access agreements,
  breach procedure) that software alone does not provide; the data stored is aggregate school counts and staff
  names/emails, not student-level records.
