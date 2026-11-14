
import sqlite3
import tempfile
from pathlib import Path

import sqlcipher3

from server.database.core.documents_migration import export_encrypted_copy

with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    source = Path(folder) / "old_documents.sqlite"
    destination = Path(folder) / "new_documents.sqlite"

    db = sqlite3.connect(str(source))
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA wal_autocheckpoint=0")
        db.execute("CREATE TABLE medical_notes (note TEXT)")
        db.commit()

        db.execute(
            "INSERT INTO medical_notes VALUES (?)",
            ("FAKE_WAL_MEDICAL_RECORD",),
        )
        db.commit()

        assert Path(str(source) + "-wal").exists()
        print("PASS 1: WAL file exists")

        # Keep the source connection open to simulate an active database.
        export_encrypted_copy(source, destination, "TEST_WAL_KEY")

        encrypted = sqlcipher3.connect(str(destination))
        try:
            encrypted.execute("PRAGMA key = 'TEST_WAL_KEY'")
            result = encrypted.execute(
                "SELECT note FROM medical_notes"
            ).fetchone()
            assert result == ("FAKE_WAL_MEDICAL_RECORD",)
            print("PASS 2: WAL data preserved")
        finally:
            encrypted.close()

    finally:
        db.close()

print("WAL MIGRATION TEST PASSED")
