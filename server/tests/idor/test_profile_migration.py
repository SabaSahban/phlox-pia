"""Focused migration SQL contract, independent of production data."""

import sqlite3

from server.database.core.migrations.v12_profile_ownership import migrate


def test_profile_creator_backfill_keeps_shared_associations_and_orphans():
    db = sqlite3.connect(":memory:")
    try:
        db.executescript("""
            CREATE TABLE patient_profiles(ur_number TEXT PRIMARY KEY);
            CREATE TABLE encounters(id INTEGER PRIMARY KEY, ur_number TEXT, created_by INTEGER, created_at TEXT);
            INSERT INTO patient_profiles VALUES ('shared'), ('orphan');
            INSERT INTO encounters VALUES (1,'shared',11,'2026-01-01'), (2,'shared',22,'2026-02-01');
        """)
        migrate(db.cursor(), db)
        assert (
            db.execute(
                "SELECT created_by FROM patient_profiles WHERE ur_number='shared'"
            ).fetchone()[0]
            == 11
        )
        assert (
            db.execute(
                "SELECT created_by FROM patient_profiles WHERE ur_number='orphan'"
            ).fetchone()[0]
            is None
        )
        assert (
            db.execute(
                "SELECT COUNT(DISTINCT created_by) FROM encounters WHERE ur_number='shared'"
            ).fetchone()[0]
            == 2
        )
    finally:
        db.close()
