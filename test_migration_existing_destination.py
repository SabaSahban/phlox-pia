
import sqlite3
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

    # Simulate a destination that already belongs to another process.
    original_content = b"EXISTING_IMPORTANT_FILE"
    destination.write_bytes(original_content)

    try:
        export_encrypted_copy(source, destination, "TEST_KEY")
    except FileExistsError:
        print("PASS 1: Existing destination rejected")
    else:
        raise AssertionError("FAIL: Existing destination was accepted")

    assert destination.read_bytes() == original_content
    print("PASS 2: Existing file preserved")

    leftovers = list(directory.glob(".documents_migration_*"))
    assert not leftovers
    print("PASS 3: No temporary files created")
    
import sqlcipher3

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
    
    print("EXISTING DESTINATION TEST PASSED")
