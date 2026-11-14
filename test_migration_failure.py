
import sqlite3
import tempfile
from pathlib import Path

from server.database.core.documents_migration import export_encrypted_copy

with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    source = Path(folder) / "original.sqlite"
    destination = Path(folder) / "encrypted.sqlite"

    db = sqlite3.connect(str(source))
    db.execute("CREATE TABLE medical_notes (note TEXT)")
    db.execute(
        "INSERT INTO medical_notes VALUES (?)",
        ("FAKE_PATIENT_RECORD",),
    )
    db.commit()
    db.close()

    # An empty key must be rejected.
    try:
        export_encrypted_copy(source, destination, "")
    except ValueError:
        print("PASS 1: Empty encryption key rejected")
    else:
        raise AssertionError("FAIL: Empty key accepted")

    # The original data must remain intact.
    db = sqlite3.connect(str(source))
    try:
        note = db.execute(
            "SELECT note FROM medical_notes"
        ).fetchone()[0]
        assert note == "FAKE_PATIENT_RECORD"
    finally:
        db.close()

    assert not destination.exists()

    print("PASS 2: Original data preserved")
    print("PASS 3: No destination created")
    print("MIGRATION FAILURE TEST PASSED")

