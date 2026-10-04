"""
migrate_auth.py — one-time migration for Module 7 (Auth)

Run this ONCE against your existing database:

    python migrate_auth.py

Why a Python script instead of a plain .sql file: the existing `password`
column holds a plaintext demo value, and turning that into a real Argon2
hash has to happen in Python (MySQL can't compute Argon2 itself). A pure
.sql migration would have to either drop the column's data or leave a
plaintext value sitting next to a column named "hash," which defeats the
point.

Safe to run more than once — it checks for each column before adding it.
Does NOT touch your existing favorites/visits/properties data.
"""

import os
import sys

from dotenv import load_dotenv

load_dotenv()

import database as db
from auth import hash_password

DEMO_PASSWORD = "changeme123"  # only used for the pre-existing seeded demo user


def column_exists(cur, table, column) -> bool:
    cur.execute(
        """
        SELECT COUNT(*) AS n FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
        """,
        (table, column),
    )
    return cur.fetchone()["n"] > 0


def main():
    with db.get_cursor(commit=True) as cur:
        if not column_exists(cur, "users", "password_hash"):
            print("Adding users.password_hash ...")
            cur.execute("ALTER TABLE users ADD COLUMN password_hash VARCHAR(255) NULL AFTER password")
        else:
            print("users.password_hash already exists, skipping.")

        if not column_exists(cur, "users", "role"):
            print("Adding users.role ...")
            cur.execute(
                "ALTER TABLE users ADD COLUMN role ENUM('renter','landlord') "
                "NOT NULL DEFAULT 'renter' AFTER password_hash"
            )
        else:
            print("users.role already exists, skipping.")

    # Backfill password_hash for any existing users who don't have one yet
    # (i.e. the demo user seeded before this module existed).
    with db.get_cursor() as cur:
        cur.execute("SELECT user_id, email FROM users WHERE password_hash IS NULL")
        needs_hash = cur.fetchall()

    if needs_hash:
        print(f"\n{len(needs_hash)} existing user(s) need a password_hash backfilled.")
        print(f'Setting their password to "{DEMO_PASSWORD}" (change it after logging in):')
        for user in needs_hash:
            hashed = hash_password(DEMO_PASSWORD)
            with db.get_cursor(commit=True) as cur:
                cur.execute(
                    "UPDATE users SET password_hash = %s WHERE user_id = %s",
                    (hashed, user["user_id"]),
                )
            print(f"  - {user['email']}")

    # Only drop the old plaintext column once every row has a real hash.
    with db.get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM users WHERE password_hash IS NULL")
        remaining = cur.fetchone()["n"]

    if remaining == 0:
        with db.get_cursor(commit=True) as cur:
            if column_exists(cur, "users", "password"):
                print("\nAll users have a password_hash now — dropping the old plaintext `password` column.")
                cur.execute("ALTER TABLE users DROP COLUMN password")
            # Column was added as NULL-able (so ALTER TABLE wouldn't fail on
            # existing rows before backfilling); now that every row has a
            # real hash, enforce NOT NULL going forward like schema.sql does
            # for fresh installs.
            cur.execute("ALTER TABLE users MODIFY password_hash VARCHAR(255) NOT NULL")
    else:
        print(f"\n{remaining} user(s) still missing a password_hash — not dropping the old column yet.")

    print("\nMigration complete. Restart uvicorn.")


if __name__ == "__main__":
    main()
