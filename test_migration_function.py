
import sqlite3
import tempfile
from pathlib import Path

import sqlcipher3

from server.database.core.documents_migration import export_encrypted_copy

with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    source = Path(folder) / "migration_test_plain.sqlite"
    destination = Path(folder) / "documents_encrypted.sqlite"
    key = "TEST_MIGRATION_KEY"

    # Create a temporary database with fake medical data.
    with sqlite3.connect(str(source)) as db:
        db.execute("CREATE TABLE medical_notes (note TEXT)")
        db.execute(
            "INSERT INTO medical_notes (note) VALUES (?)",
            ("FAKE_PATIENT_MEDICAL_RECORD",),
        )
        db.commit()
        
    # Export using the actual Phlox migration function.
    export_encrypted_copy(source, destination, key)

    # Verify the encrypted copy contains the original data.
    db = sqlcipher3.connect(str(destination))
    try:
        db.execute("PRAGMA key = 'TEST_MIGRATION_KEY'")

        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        note = db.execute(
            "SELECT note FROM medical_notes"
        ).fetchone()[0]

        assert integrity == "ok"
        assert note == "FAKE_PATIENT_MEDICAL_RECORD"

        print("PASS 1: Migration function preserved the data")
    finally:
        db.close()

    # Verify that SQLite cannot read the encrypted copy.
    plain = sqlite3.connect(str(destination))
    try:
        try:
            plain.execute("SELECT note FROM medical_notes").fetchone()
        except sqlite3.DatabaseError:
            print("PASS 2: Migrated copy is encrypted")
        else:
            raise AssertionError("FAIL: Database is readable without key")
    finally:
        plain.close()

    # Verify that the original file remains unchanged.
    original = sqlite3.connect(
        f"file:{source.resolve().as_posix()}?mode=ro",
        uri=True,
    )
    try:
        assert original.execute(
            "SELECT note FROM medical_notes"
        ).fetchone()[0] == "FAKE_PATIENT_MEDICAL_RECORD"
    finally:
        original.close()

    print("PASS 3: Original database preserved")
    print("MIGRATION FUNCTION TEST PASSED")
