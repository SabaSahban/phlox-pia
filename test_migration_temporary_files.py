
import sqlite3
import sqlcipher3
import tempfile
from pathlib import Path

from server.database.core.documents_migration import export_encrypted_copy


with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    directory = Path(folder)
    source = directory / "original.sqlite"
    destination = directory / "encrypted.sqlite"

    db = sqlite3.connect(str(source))
    try:
        db.execute("CREATE TABLE medical_notes (note TEXT)")
        db.execute(
            "INSERT INTO medical_notes VALUES (?)",
            ("FAKE_PATIENT_RECORD",),
        )
        db.commit()
    finally:
        db.close()

    export_encrypted_copy(source, destination, "TEST_KEY")

    assert destination.exists()
    print("PASS 1: Encrypted destination exists")

    leftovers = list(directory.glob(".documents_migration_*"))

    assert not leftovers, (
        f"Temporary files remain: {leftovers}"
    )
    print("PASS 2: No temporary files remain")
    
    encrypted = sqlcipher3.connect(str(destination))
    try:
        encrypted.execute("PRAGMA key = 'TEST_KEY'")

        result = encrypted.execute(
            "SELECT note FROM medical_notes"
        ).fetchone()[0]

        assert result == "FAKE_PATIENT_RECORD"
        print("PASS 3: Published database is readable with the correct key")
    finally:
        encrypted.close()

    print("TEMPORARY FILE TEST PASSED")


    print("TEMPORARY FILE TEST PASSED")
