"""
database.py — RentWise Module 1

Thin data-access layer over MySQL. Every function opens a pooled
connection, runs one statement, and returns plain dicts/lists so the
route handlers in app.py never touch SQL directly.
"""

import os
from contextlib import contextmanager

import mysql.connector
from mysql.connector import pooling
from mysql.connector.errors import ProgrammingError
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "rentwise"),
}

_pool = pooling.MySQLConnectionPool(
    pool_name="rentwise_pool",
    pool_size=5,
    **DB_CONFIG,
)


@contextmanager
def get_cursor(commit: bool = False):
    """Yield a dictionary cursor from the pool; commits and closes automatically."""
    conn = _pool.get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        yield cursor
        if commit:
            conn.commit()
    finally:
        cursor.close()
        conn.close()


# ---------------------------------------------------------------
# Properties
# ---------------------------------------------------------------

# Module 10: allowed sort orders. The API accepts only these keys and the SQL
# text comes from THIS dictionary - a request value is never pasted into the
# query, so there is no SQL injection route through `sort`. property_id ASC is
# the tie-breaker: equal rents / equal timestamps (all the seed listings share
# one) always come back in the same, predictable order - lowest id first, which
# is also the order the list showed before sorting existed. Without it, MySQL
# is free to return ties in a different order from one request to the next.
SORT_ORDERS = {
    "newest": "created_at DESC, property_id ASC",
    "rent_low": "rent ASC, property_id ASC",
    "rent_high": "rent DESC, property_id ASC",
}


def _order_by(sort: str) -> str:
    return SORT_ORDERS.get(sort, SORT_ORDERS["newest"])


def list_properties(limit: int = 20, offset: int = 0, sort: str = "newest"):
    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT * FROM properties
            WHERE availability = TRUE
            ORDER BY {_order_by(sort)}
            LIMIT %s OFFSET %s
            """,
            (limit, offset),
        )
        return cur.fetchall()


def count_properties():
    with get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM properties WHERE availability = TRUE")
        return cur.fetchone()["total"]


def get_property(property_id: int):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM properties WHERE property_id = %s", (property_id,))
        prop = cur.fetchone()
        if not prop:
            return None
        cur.execute(
            """
            SELECT a.amenity_id, a.amenity_name
            FROM amenities a
            JOIN property_amenities pa ON pa.amenity_id = a.amenity_id
            WHERE pa.property_id = %s
            """,
            (property_id,),
        )
        prop["amenities"] = cur.fetchall()

        # Gallery = main picture first, then any extra rows from
        # property_images. If that table doesn't exist yet (migration not run),
        # fall back to just the main picture instead of breaking every page
        # that calls get_property().
        try:
            cur.execute(
                "SELECT image_url FROM property_images WHERE property_id = %s ORDER BY sort_order, image_id",
                (property_id,),
            )
            extra = [row["image_url"] for row in cur.fetchall()]
        except ProgrammingError:
            extra = []

        images = []
        for url in [prop.get("image_url")] + extra:
            if url and url not in images:
                images.append(url)
        prop["images"] = images
        return prop


def search_properties(query: str, limit: int = 20):
    like = f"%{query}%"
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT * FROM properties
            WHERE availability = TRUE
              AND (location LIKE %s OR city LIKE %s OR title LIKE %s)
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (like, like, like, limit),
        )
        return cur.fetchall()


_STOPWORDS = {
    "a", "an", "the", "in", "at", "with", "for", "and", "or", "of", "to",
    "near", "under", "over", "below", "above", "monthly", "rent", "month",
    "looking", "want", "need", "find", "me", "please", "bhk", "bedroom",
    "bedrooms", "house", "flat", "property", "properties",
}


def keyword_fallback_search(query: str, limit: int = 20):
    """
    Used only when the AI Property Finder's LLM call fails (SRS NFR-7).
    Unlike search_properties() above — which matches the whole phrase and
    suits a short location string from the /properties/search API — this
    splits a full natural-language sentence into words and matches ANY of
    them, since a sentence like "furnished apartment in Kochi" will never
    appear verbatim in a single column.
    """
    words = [w.strip(",.!?") for w in query.lower().split()]
    keywords = [w for w in words if w and w not in _STOPWORDS]
    if not keywords:
        return []

    clauses = []
    params = []
    for word in keywords:
        like = f"%{word}%"
        clauses.append("(location LIKE %s OR city LIKE %s OR title LIKE %s OR property_type LIKE %s)")
        params.extend([like, like, like, like])
    params.append(limit)

    with get_cursor() as cur:
        cur.execute(
            f"""
            SELECT * FROM properties
            WHERE availability = TRUE AND ({" OR ".join(clauses)})
            ORDER BY created_at DESC
            LIMIT %s
            """,
            tuple(params),
        )
        return cur.fetchall()


def filter_properties(
    city=None, property_type=None, min_rent=None, max_rent=None,
    bedrooms=None, furnishing=None, parking=None, limit: int = 20,
    sort: str = "newest",
):
    clauses = ["availability = TRUE"]
    params = []

    if city:
        clauses.append("city = %s")
        params.append(city)
    if property_type:
        clauses.append("property_type = %s")
        params.append(property_type)
    if min_rent is not None:
        clauses.append("rent >= %s")
        params.append(min_rent)
    if max_rent is not None:
        clauses.append("rent <= %s")
        params.append(max_rent)
    if bedrooms is not None:
        clauses.append("bedrooms = %s")
        params.append(bedrooms)
    if furnishing:
        clauses.append("furnishing = %s")
        params.append(furnishing)
    if parking is not None:
        clauses.append("parking = %s")
        params.append(parking)

    where = " AND ".join(clauses)
    params.append(limit)

    with get_cursor() as cur:
        cur.execute(
            f"SELECT * FROM properties WHERE {where} ORDER BY {_order_by(sort)} LIMIT %s",
            tuple(params),
        )
        return cur.fetchall()


# ---------------------------------------------------------------
# Favorites
# ---------------------------------------------------------------

def add_favorite(user_id: int, property_id: int):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT IGNORE INTO favorites (user_id, property_id)
            VALUES (%s, %s)
            """,
            (user_id, property_id),
        )
        cur.execute(
            "SELECT * FROM favorites WHERE user_id = %s AND property_id = %s",
            (user_id, property_id),
        )
        return cur.fetchone()


def list_favorites(user_id: int):
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT f.favorite_id, f.created_at, p.*
            FROM favorites f
            JOIN properties p ON p.property_id = f.property_id
            WHERE f.user_id = %s
            ORDER BY f.created_at DESC
            """,
            (user_id,),
        )
        return cur.fetchall()


def remove_favorite(favorite_id: int, user_id: int):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "DELETE FROM favorites WHERE favorite_id = %s AND user_id = %s",
            (favorite_id, user_id),
        )
        return cur.rowcount > 0


# ---------------------------------------------------------------
# Visits
# ---------------------------------------------------------------

BOOKABLE_SLOTS = ["10:00", "11:00", "12:00", "14:00", "15:00", "16:00", "17:00"]


def _format_visit(row):
    """mysql-connector returns TIME columns as timedelta; render as HH:MM:SS for JSON."""
    if row and row.get("visit_time") is not None:
        total_seconds = int(row["visit_time"].total_seconds())
        h, rem = divmod(total_seconds, 3600)
        m, s = divmod(rem, 60)
        row["visit_time"] = f"{h:02d}:{m:02d}:{s:02d}"
    return row


def get_visit_availability(property_id: int, visit_date: str):
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT visit_time FROM visits
            WHERE property_id = %s AND visit_date = %s AND status != 'Cancelled'
            """,
            (property_id, visit_date),
        )
        taken = {str(row["visit_time"])[:5] for row in cur.fetchall()}
    return [slot for slot in BOOKABLE_SLOTS if slot not in taken]


def create_visit(user_id: int, property_id: int, visit_date: str, visit_time: str):
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO visits (user_id, property_id, visit_date, visit_time)
            VALUES (%s, %s, %s, %s)
            """,
            (user_id, property_id, visit_date, visit_time),
        )
        visit_id = cur.lastrowid
        cur.execute("SELECT * FROM visits WHERE visit_id = %s", (visit_id,))
        return _format_visit(cur.fetchone())


def create_contact_message(user_id, name: str, email: str, topic: str, message: str) -> int:
    """Module 9: store a Contact-page message. user_id is None for guests."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO contact_messages (user_id, name, email, topic, message)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (user_id, name, email, topic, message),
        )
        return cur.lastrowid


def count_recent_contact_messages(email: str | None = None, minutes: int = 60) -> int:
    """How many messages were stored in the last `minutes` minutes — for one
    email address, or (email=None) across everyone. Used as a simple
    anti-spam limit on POST /contact."""
    sql = "SELECT COUNT(*) AS n FROM contact_messages WHERE created_at >= (NOW() - INTERVAL %s MINUTE)"
    params = [minutes]
    if email is not None:
        sql += " AND email = %s"
        params.append(email)
    with get_cursor() as cur:
        cur.execute(sql, tuple(params))
        return cur.fetchone()["n"]


def get_visit(visit_id: int):
    with get_cursor() as cur:
        cur.execute("SELECT * FROM visits WHERE visit_id = %s", (visit_id,))
        return _format_visit(cur.fetchone())


def list_visits_for_user(user_id: int):
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT v.*, p.title, p.location, p.city, p.image_url
            FROM visits v
            JOIN properties p ON p.property_id = v.property_id
            WHERE v.user_id = %s
            ORDER BY v.visit_date DESC, v.visit_time DESC
            """,
            (user_id,),
        )
        return [_format_visit(row) for row in cur.fetchall()]


# ---------------------------------------------------------------
# Users (Module 6 — Profile page)
#
# NOTE: no auth yet (see README "Known gaps"). This lets a user view/edit
# their own name, phone, and email. There is no "preferences" table in
# the Module 1 schema, so the profile page only exposes the columns that
# actually exist on `users` — see the README for that scope call.
# ---------------------------------------------------------------

def get_user(user_id: int):
    """Safe fields only — never includes password_hash. See get_user_by_email_with_hash()
    for the one place (login) that legitimately needs the hash."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT user_id, name, phone, email, role, created_at FROM users WHERE user_id = %s",
            (user_id,),
        )
        return cur.fetchone()


def get_user_by_email_with_hash(email: str):
    """
    Used ONLY by the login endpoint, which is the one legitimate place
    that needs password_hash to verify a login attempt. Every other part
    of the app uses get_user(), which deliberately excludes this column.
    """
    with get_cursor() as cur:
        cur.execute(
            "SELECT user_id, name, phone, email, role, password_hash FROM users WHERE email = %s",
            (email,),
        )
        return cur.fetchone()


def create_user(name: str, email: str, password_hash: str, phone: str = None, role: str = "renter"):
    with get_cursor(commit=True) as cur:
        cur.execute(
            "INSERT INTO users (name, phone, email, password_hash, role) VALUES (%s, %s, %s, %s, %s)",
            (name, phone, email, password_hash, role),
        )
        user_id = cur.lastrowid
    return get_user(user_id)


def update_user(user_id: int, **fields):
    """Only updates columns actually passed (dynamic SET clause)."""
    allowed = {"name", "phone", "email"}
    updates = {k: v for k, v in fields.items() if k in allowed and v is not None}
    if not updates:
        return get_user(user_id)

    set_clause = ", ".join(f"{col} = %s" for col in updates)
    params = list(updates.values()) + [user_id]

    with get_cursor(commit=True) as cur:
        cur.execute(f"UPDATE users SET {set_clause} WHERE user_id = %s", tuple(params))
    return get_user(user_id)


# ---------------------------------------------------------------
# Rental preferences (Module 11)
# ---------------------------------------------------------------

PREFERENCE_FIELDS = (
    "preferred_city", "min_budget", "max_budget", "bedrooms",
    "property_type", "furnishing", "needs_parking",
)


def get_preferences(user_id: int) -> dict:
    """A user's saved preferences. Someone who never saved any gets the same
    shape with every field empty, so callers never have to special-case it."""
    with get_cursor() as cur:
        cur.execute(
            f"SELECT {', '.join(PREFERENCE_FIELDS)} FROM user_preferences WHERE user_id = %s",
            (user_id,),
        )
        row = cur.fetchone()
    if not row:
        return {**{f: None for f in PREFERENCE_FIELDS}, "needs_parking": False}
    row["needs_parking"] = bool(row["needs_parking"])
    return row


def save_preferences(user_id: int, prefs: dict) -> dict:
    """Create or replace the user's preferences (one row per user)."""
    columns = ", ".join(PREFERENCE_FIELDS)
    placeholders = ", ".join(["%s"] * len(PREFERENCE_FIELDS))
    updates = ", ".join(f"{f} = VALUES({f})" for f in PREFERENCE_FIELDS)
    with get_cursor(commit=True) as cur:
        cur.execute(
            f"INSERT INTO user_preferences (user_id, {columns}) VALUES (%s, {placeholders}) "
            f"ON DUPLICATE KEY UPDATE {updates}",
            (user_id, *[prefs.get(f) for f in PREFERENCE_FIELDS]),
        )
    return get_preferences(user_id)


# ---------------------------------------------------------------
# AI Rental Insights (Module 6 — FR-12)
# ---------------------------------------------------------------

def get_favorite_stats(user_id: int):
    """Aggregates over a user's saved properties: count, avg rent, most
    common city and property type. Returns count=0 and nulls if the user
    has no favorites yet, so the caller can skip the AI call entirely."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) AS count, AVG(p.rent) AS avg_rent
            FROM favorites f JOIN properties p ON p.property_id = f.property_id
            WHERE f.user_id = %s
            """,
            (user_id,),
        )
        totals = cur.fetchone()

        if not totals or totals["count"] == 0:
            return {"count": 0, "avg_rent": None, "top_city": None, "top_property_type": None}

        cur.execute(
            """
            SELECT p.city, COUNT(*) AS n
            FROM favorites f JOIN properties p ON p.property_id = f.property_id
            WHERE f.user_id = %s
            GROUP BY p.city ORDER BY n DESC LIMIT 1
            """,
            (user_id,),
        )
        top_city = cur.fetchone()

        cur.execute(
            """
            SELECT p.property_type, COUNT(*) AS n
            FROM favorites f JOIN properties p ON p.property_id = f.property_id
            WHERE f.user_id = %s
            GROUP BY p.property_type ORDER BY n DESC LIMIT 1
            """,
            (user_id,),
        )
        top_type = cur.fetchone()

        return {
            "count": totals["count"],
            "avg_rent": float(totals["avg_rent"]) if totals["avg_rent"] is not None else None,
            "top_city": top_city["city"] if top_city else None,
            "top_property_type": top_type["property_type"] if top_type else None,
        }
