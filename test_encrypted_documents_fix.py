
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from server.database.core.encrypted_documents import connect_encrypted_documents

with tempfile.TemporaryDirectory() as folder:
    path = Path(folder) / "documents.sqlite"

    # Simulate an initialized database with a test-only key.
    fake_db = SimpleNamespace(encryption_key="test_password_123")

    with patch(
        "server.database.core.encrypted_documents.get_db",
        return_value=fake_db,
    ):
        db = connect_encrypted_documents(path)
        try:
            db.execute("CREATE TABLE medical_notes (text TEXT)")
            db.execute(
                "INSERT INTO medical_notes VALUES (?)",
                ("CONFIDENTIAL_TEST_NOTE",),
            )
            db.commit()
        finally:
            db.close()

    # Verify that ordinary SQLite cannot read the encrypted database.
    reader = sqlite3.connect(str(path))
    try:
        try:
            reader.execute("SELECT text FROM medical_notes").fetchone()
        except sqlite3.DatabaseError:
            print("PASS 1: Database cannot be read without key")
        else:
            raise AssertionError("FAIL: Database is readable without key")
    finally:
        reader.close()

    # Verify that the encrypted connection can read the saved data.
    with patch(
        "server.database.core.encrypted_documents.get_db",
        return_value=fake_db,
    ):
        db = connect_encrypted_documents(path)
        try:
            result = db.execute(
                "SELECT text FROM medical_notes"
            ).fetchone()[0]
            assert result == "CONFIDENTIAL_TEST_NOTE"
        finally:
            db.close()

    print("PASS 2: Correct key reads encrypted data")
    print("ENCRYPTION FIX TEST PASSED")
