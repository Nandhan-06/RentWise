# RentWise — Module 1: Database + Core APIs

This is the foundation module: the MySQL schema plus the FastAPI CRUD
layer for properties, favorites, and visits. Every later module (AI
property finder, AI chatbot with RAG, frontend) is built on top of this.

## What's included

```
rentwise-backend/
  app.py              FastAPI routes (properties, favorites, visits)
  database.py         All SQL — nothing else touches the DB directly
  schemas.py          Pydantic request models
  requirements.txt
  .env.example
  db/
    schema.sql        6-table schema (see SRS Section 6)
    seed_data.sql     10 sample properties + amenities for local testing
```

## Setup

1. **Install MySQL 8** (or MariaDB) locally if you don't already have it running.

2. **Create the database and load sample data:**
   ```bash
   mysql -u root -p < db/schema.sql
   mysql -u root -p rentwise < db/seed_data.sql
   ```

3. **Create a dedicated app user** (recommended over using root):
   ```sql
   CREATE USER 'rentwise_user'@'%' IDENTIFIED BY 'your_password_here';
   GRANT ALL PRIVILEGES ON rentwise.* TO 'rentwise_user'@'%';
   FLUSH PRIVILEGES;
   ```

4. **Copy `.env.example` to `.env`** and fill in your credentials:
   ```
   DB_HOST=localhost
   DB_PORT=3306
   DB_USER=rentwise_user
   DB_PASSWORD=your_password_here
   DB_NAME=rentwise
   ```

5. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

6. **Run the server:**
   ```bash
   uvicorn app:app --reload
   ```

7. **Try it out** — interactive docs are auto-generated at
   `http://127.0.0.1:8000/docs`.

## Endpoints implemented

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/properties` | Paginated listing (`?page=1&page_size=20`) |
| GET | `/properties/{id}` | Single property with amenities |
| GET | `/properties/search?q=...` | Text search (title/location/city) |
| GET | `/properties/filter` | Filter by city, type, rent range, bedrooms, furnishing, parking |
| POST | `/favorites` | Save a property (`{user_id, property_id}`) |
| GET | `/favorites?user_id=...` | List a user's favorites |
| DELETE | `/favorites/{id}?user_id=...` | Remove a favorite |
| GET | `/visits/availability?property_id=...&visit_date=YYYY-MM-DD` | Open time slots |
| POST | `/visits` | Schedule a visit (rejects double-booked slots with 409) |
| GET | `/visits/{id}` | Single visit record |
| GET | `/visits/user/{user_id}` | A user's visit history |

All endpoints have been tested end-to-end against a live MySQL-compatible
database during development, including the double-booking conflict path.

## Notable design decisions

- **`database.py` owns all SQL.** Route handlers in `app.py` never write
  raw queries — this keeps the AI modules (which will also need to query
  properties) consistent and makes the whole layer easier to unit test.
- **Connection pooling** via `mysql.connector.pooling` (pool size 5) rather
  than opening a fresh connection per request.
- **Visit slots are fixed** (`10:00`–`17:00`, hourly with a lunch gap) for
  simplicity in V1; availability is computed by subtracting already-booked,
  non-cancelled slots for that property and date.
- **`GET /properties/{id}` is declared after `/properties/search` and
  `/properties/filter`** — FastAPI matches routes in order, so the static
  paths must come first or `"search"`/`"filter"` would be parsed as an
  integer `property_id` and 422 instead of routing correctly.

## Known gaps (intentionally out of scope for Module 1)

- No authentication yet — `user_id` is passed directly by the client.
  `users.password` is stored as plaintext for now; hashing arrives with
  the auth module.
- No AI endpoints — `/ai/property-search`, `/ai/property-compare`,
  `/ai/rental-insights`, `/ai/chatbot` come in later modules and will
  import from `database.py` rather than duplicating query logic.
- No frontend — this module is API-only, verified via `/docs` and curl.

## Module 2 — Minimal frontend (new)

A server-rendered property list and filter page, added on top of Module 1
with no changes to the API layer.

```
templates/
  base.html          Shared layout: header, nav, footer
  properties.html    The property list page (filter form + results grid)
static/
  css/style.css      All page styling
  js/properties.js   Fetches from /properties and /properties/filter,
                      renders cards, and lazy-loads amenities from
                      /properties/{id} when a card is expanded
```

Visiting `http://127.0.0.1:8000/` now renders this page directly (this
also replaces the old 404 you saw at the root URL). The page is plain
HTML/CSS/JS with no build step — just refresh the browser after editing
any of these files.

**One extra install step:** this module added `jinja2` to
`requirements.txt`. If you already ran `pip install -r requirements.txt`
before this update, re-run it to pick up the new dependency:
```bash
pip install -r requirements.txt
```

## Module 3 — Favorites & Visits UI (new)

Two new pages, built on the existing Favorites and Visits APIs with no
backend changes:

```
templates/
  favorites.html     Grid of saved properties, with a Remove button
  visits.html        List of scheduled visits with date/time/status
static/js/
  common.js          Shared DEMO_USER_ID, money(), specsLine() helpers
  favorites.js        Lists + removes favorites
  visits.js           Lists scheduled visits
  properties.js        (updated) — each card now has Save and
                        Schedule Visit actions in addition to View Details
```

**Routes added:** `GET /my-favorites` and `GET /my-visits`. These are
deliberately *not* `/favorites` and `/visits` — those exact paths are
already the JSON API routes from Module 1. A page and a JSON API can't
share one path and method in FastAPI, so the browser-facing pages get
their own names while the API keeps the paths documented in the SRS.

**No auth yet** (see Module 1's "Known gaps"), so every page acts as a
single demo user — `DEMO_USER_ID = 1` in `common.js`, matching the user
seeded in `db/seed_data.sql`. Every "Save" and "Schedule visit" action
will show up under this same user across all pages. This constant is the
one line you'll change once a real login exists.

**Scheduling flow:** on the properties page, "Schedule visit" reveals a
date picker → "Check availability" calls `/visits/availability` → open
slots render as buttons → clicking one books it and shows a confirmation,
with a graceful message if the slot was just taken by someone else
(mirrors the existing 409 conflict response).

This was tested end-to-end against a live server: save → list → check
availability → book → attempted double-booking correctly rejected →
appears in My Visits → remove favorite → confirmed removed.

## Module 4 — AI Property Finder (new)

Natural-language search, using structured RAG exactly as described in the
SRS (Section 7.2): the LLM only extracts filters and writes a summary —
it never invents a property. Retrieval (your existing `filter_properties`
query) always runs first; the LLM only ever talks about rows that came
back from that query.

```
ai_service.py             LLM calls, isolated from database.py and app.py
templates/ai_finder.html  The search page
static/js/ai_finder.js    Renders results, filter chips, and the summary
```

**New endpoint:** `POST /ai/property-search` — body `{"query": "..."}`,
returns the extracted `filters`, matching `results`, a short grounded
`summary`, and a `used_fallback` flag.
**New page:** `GET /ai-finder`.

### You need to add your own API key — Gemini edition

This module calls Google's Gemini API (switched from Anthropic since it
has a usable free tier with no card required):

1. Get a free key at https://aistudio.google.com/app/apikey (sign in with
   any Google account — no credit card needed for the free tier).
2. Add it to `.env`:
   ```
   GEMINI_API_KEY=your_key_here
   AI_MODEL=gemini-3.1-flash-lite
   ```
3. Re-run `pip install -r requirements.txt` (this module uses the
   `google-genai` package — note: **not** `google-generativeai`, which is
   an older, now-deprecated package with a similar name).

**Precautions specific to Gemini:**

- **Don't use `gemini-2.5-flash`** even though many tutorials still show
  it — Google has it scheduled for shutdown on **16 October 2026**. This
  project defaults to `gemini-3.1-flash-lite` instead: stable (not a
  preview model) and free-tier eligible, with no shutdown date announced
  as of this writing. Re-check
  https://ai.google.dev/gemini-api/docs/models occasionally — Google
  updates its free-tier lineup every few months.
- **Restrict your API key** in AI Studio to "Gemini API only" right after
  creating it. Google has been moving toward requiring key restrictions;
  an unrestricted key is more exposed if it ever leaks.
- **Never commit `.env`** to git — it holds your key. If this project
  isn't already a git repo with `.env` in `.gitignore`, add that before
  your first commit.
- **Free-tier rate limits aren't published as fixed numbers** — Google
  shows your account's actual current limits at
  https://aistudio.google.com/rate-limit. If you hit a rate limit
  mid-demo, `ai_service.py` raises and `/ai/property-search`
  automatically falls back to keyword search rather than erroring out
  (see below) — so a rate limit won't crash your demo, it'll just
  silently degrade to non-AI search for that request.
- You may see a one-line SDK warning in your terminal about "automatic
  function calling" when the server starts handling AI requests — that's
  informational only (this project doesn't use function calling) and can
  be ignored.

### Graceful fallback (SRS NFR-7)

If the key is missing, invalid, rate-limited, or the API call fails for
any other reason, `/ai/property-search` does **not** error out — it
automatically falls back to a plain keyword search (`db.keyword_fallback_search`,
a function separate from the existing `/properties/search` API, since a
full sentence needs word-by-word matching rather than one phrase match).
The response includes `"used_fallback": true` so the frontend can tell
the user the AI is temporarily unavailable rather than pretending
everything's normal.

This was tested with three real scenarios: no key configured, a fake key
that fails at Gemini's servers, and the filter/summary pipeline with a
manually-simulated valid response — all three behave correctly. The one
thing I could not test end-to-end myself is an actual successful Gemini
API call, since that needs your personal key — try it after adding yours
and let me know if a response looks off.

## Next module

Module 5 (AI Chatbot with RAG) is the natural next step — it reuses
`ai_service.py`'s structured-RAG path for search-style questions and adds
a new semantic-RAG path (vector search) for general questions.
