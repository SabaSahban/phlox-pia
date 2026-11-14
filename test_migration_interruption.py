
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from server.database.core.documents_migration import export_encrypted_copy

with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    source = Path(folder) / "original.sqlite"
    destination = Path(folder) / "encrypted.sqlite"

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

    # Simulate a failure during SQLCipher export.
    with patch(
        "server.database.core.documents_migration.sqlcipher3.connect",
        side_effect=RuntimeError("SIMULATED_CONNECTION_FAILURE"),
    ):
        try:
            export_encrypted_copy(source, destination, "TEST_KEY")
        except RuntimeError as error:
            assert str(error) == "SIMULATED_CONNECTION_FAILURE"
            print("PASS 1: Simulated failure detected")
        else:
            raise AssertionError("FAIL: Expected an exception")

    # Verify that the original database still contains its data.
    original = sqlite3.connect(str(source))
    try:
        note = original.execute(
            "SELECT note FROM medical_notes"
        ).fetchone()[0]
        assert note == "FAKE_PATIENT_RECORD"
    finally:
        original.close()

    print("PASS 2: Original data preserved")
    print("INTERRUPTION TEST PASSED")

