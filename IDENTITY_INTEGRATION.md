# Developer 1: audit, contracts, and integration

Audit: 5 October 2026. Initial branch `identity-integration`, clean working tree.
Work continues on `feature/identity-integration`. No frontend or schema changes.

## Audit before implementation

### A. Existing implementation

- `app.py`: application factory, CORS localhost:5173, auth/users blueprints,
  development health/database/user probes.
- `config.py`: environment-based connection URI and JWT secret. Never share `.env`.
- `extensions.py`: shared SQLAlchemy and Flask-Migrate; no migration baseline exists.
- `models/user.py`: User, users table, safe public serializer, role/status/profile.
- `models/user_profile.py`: one-to-one UserProfile through unique id_user; no_hp.
- `routes/auth.py`: register, login, token_required, admin_required, me,
  update_me, profile_photo, admin_test. Existing JWT: HS256, eight-hour expiry.
- `routes/users.py`: admin list/create/update/status; no self-demotion/deactivation;
  locks accounts to preserve an active admin.
- `routes/user_validation.py`: allowlist, lengths, email/role/status/photo validation.
- `routes/profile_photos.py`: decode/re-encode JPEG/PNG/WebP, 2 MB, 16 MP,
  maximum output dimensions 1024, UUID PNG filenames in instance/profile_photos.
- `tests/test_users_api.py`: 14 mocked-session contract/access/photo tests.
- `schema.sql`: 13 existing tables, not a migration. Only User/UserProfile mapped
  before this task. routes/__init__.py was empty; no need to modify it.

Frontend dependencies inspected read-only: auth response token/user, me's direct
user object, users envelope, PATCH response user, nested user_profile.no_hp,
absolute photo URL. Kelola User filters locally; GET /api/users stays compatible.

### B. Issues addressed

- Register/login reject non-object or wrong-type input with 400 rather than 500.
- Register applies existing name/email validation, trims those fields, handles
  duplicate-email race with rollback and 409. Public role/status still forced.
- JWT must contain exp and positive integer id_user; authorization reads current
  database role/status, not a stale or forged role claim.
- Admin create/update now accepts optional no_hp, using the same profile helper.
- PATCH me accepts a photo-only multipart request, retaining existing size/type rules.

### C. Newly added foundation

- Activity mapping and transactional record_activity helper; successful login hook.
- Admin-only paginated activity reads and identity dashboard counts.
- Authenticated leaderboard endpoint explicitly returns 501, not invented scores.
- Isolated SQLite-memory transaction tests alongside existing mock tests.

### D. Schema and integration limits

Existing activity enum supports ONLY login, buka_course, buka_materi,
selesai_materi, selesai_course, mulai_test, selesai_test. It has no fields for
target user, action metadata, or old/new values. Register/profile/photo/admin
changes cannot be represented faithfully. They are NOT logged as another event.
Full identity/admin audit logging needs an explicitly agreed future schema change;
none was made here. Login is the only automatically recorded event in this PR.

Activity's database FKs to course/materi/penilaian remain enforced by MySQL.
Their ORM relationships/FK metadata are intentionally deferred to domain merge;
do not autogenerate a migration from this partial ORM mapping. No placeholder
models/tables for Developer 2 or Developer 3 were created.

Existing limitations retained: users listing is unpaginated; admin updates lock
all users; old uploaded photos are not garbage-collected. Public development
`/user-test` exposes one account identity and database probes expose error details.
Keep these development endpoints private; restrict them before public deployment.
No claim of production readiness is made by the tests.

## API contracts

Existing URLs and successful response shapes remain unchanged:

| Method | URL | Access / result |
|---|---|---|
| POST | /api/auth/register | Public; 201 message, duplicate 409; role=user/status=aktif |
| POST | /api/auth/login | Public; 200 message/token/user; inactive 403, wrong credentials 401 |
| GET | /api/auth/me | Active bearer account; direct user object |
| PATCH | /api/auth/me | Own profile only; 200 message/user |
| GET | /api/auth/admin-test | Active admin |
| GET | /api/auth/profile-photos/filename | Public UUID PNG reference |
| GET | /api/users | Active admin; users array |
| POST | /api/users | Active admin; 201 message/user |
| PATCH | /api/users/id | Active admin; 200 message/user |
| GET | /api/activity | Active admin; activities/pagination |
| GET | /api/dashboard | Active admin; identity statistics and dependency markers |
| GET | /api/leaderboard | Active bearer account; 501 pending_dependencies |

New optional admin request field `no_hp`: text up to 30 characters, digits,
optional leading +, spaces, parentheses/hyphens. Empty string clears; omitted
field leaves existing data intact. Storage remains user_profile.no_hp. Response:
`user_profile: {no_hp: string|null}`. No nested profile write or client-supplied
actor ID is accepted on /auth/me. Phone is optional, not a verified contact number.

Login audit and terakhir_login commit atomically. DB failure returns 503 with no
token in the response. Activity table must exist from the original schema import.
Do not recreate an existing database to resolve a missing table; inspect setup.

### Activity reads

GET /api/activity?page=1&per_page=20&id_user=2&jenis_aktivitas=login

- Defaults: page=1, per_page=20. Bounds: page 1..1000000, per_page 1..100.
- id_user and jenis_aktivitas optional; malformed parameters return 400.
- Newest first by waktu_dimulai then id_activity; page beyond end gives empty list.
- Response: activities contains schema fields only; pagination contains page,
  per_page, total, pages. No passwords, tokens, emails, phone numbers, or file data.
- No public write/update/delete activity endpoint.

Shared backend usage (after authenticating actor and checking domain permission):

```python
from services.activity import record_activity

record_activity(actor.id_user, "login")  # Example supported event
# Caller commits its business changes and audit record together.
# Caller rolls back the whole transaction on failure.
```

Optional keyword fields: id_course, id_materi, id_penilaian, durasi (seconds),
waktu_dimulai, waktu_selesai. Times follow existing server-local naive datetime
convention; deployments must agree on server timezone. IDs must be positive.
The helper validates schema-level values, not enrollment/ownership/domain rules.
It never commits and never derives progress or scores.

### Dashboard (implemented Identity scope)

```json
{
  "identity": {
    "total_users": 0, "active_users": 0, "inactive_users": 0,
    "admins": 0, "regular_users": 0
  },
  "learning": null,
  "assessment": null,
  "dependencies": [
    "[DEPENDENCY DEV 2] Learning statistics",
    "[DEPENDENCY DEV 3] Assessment statistics"
  ]
}
```

Numbers above illustrate keys, not seeded values. Counts come from users in one
aggregate query. total_users includes admin and user; active/inactive include both
roles. Null means unavailable, not zero. No course/test query is executed.

### Leaderboard proposal (not a final scoring contract)

Current endpoint: 501 with status=pending_dependencies, message and dependencies.
It does not query learning/test tables and never returns fake rankings.

Proposed future success envelope for team review:
`{period, rule_version, rankings: [{rank, id_user, nama, jabatan, foto_profil,
score}], pagination}`. Do not expose email/no_hp. Eligibility, period boundaries,
score meaning, attempt selection, tie-break and rank across pages remain undecided.

- [DEPENDENCY DEV 2] Authoritative enrollment and completion definitions from
  user_course/user_materi, active/deleted course behavior, reporting read contract.
- [DEPENDENCY DEV 3] Finalized penilaian, incomplete attempt exclusion, best/latest
  attempt choice, retake rules and score aggregation contract.
- Team decision: which roles/statuses qualify and how points/rank are calculated.
- Activity is never the source of progress or leaderboard score.

## Ownership and merge order

Dev 1 owns identity/users, activity/reporting, services helpers and registration
in app.py/models/__init__.py. Config/extensions/requirements unchanged.
Dev 2/3 submit their own model/route files and list required shared-file changes
in PRs; do not create duplicate db instances or edit authentication core.

Merge identity foundation, then Dev 2 learning and Dev 3 assessment/discussion
contracts, then integrate dashboard/leaderboard in a separate reviewed PR.
Agree schema changes explicitly; git pull never updates a database.

## Verification and manual checks

Run `venv\Scripts\python.exe -B -m unittest discover -s tests -v`.
New tests use explicit fixture DDL only in SQLite :memory:, never .env/database
credentials. They cover persistence, rollback, authorization, input validation,
login audit, photo-only upload, filters/pagination and dependency responses.
They do not validate MariaDB row locks, enum enforcement or domain foreign keys.

Before PR merge, manually test in an isolated MariaDB development setup:
login admin/user, edit profile/phone/photo, refresh, manage another user's phone
and status, read activity/dashboard as admin, verify 403 as user. Check exactly
one login event per successful request, none on wrong password, and no password
in API responses. Check concurrent duplicate email and first profile saves.
No frontend changes or real user data belong in this PR.
