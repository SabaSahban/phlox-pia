
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from server.rag.backends.sqlite_vec import SqliteVecBackend

with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    path = Path(folder) / "documents.sqlite"
    fake_db = SimpleNamespace(encryption_key="test_password_123")

    with patch(
        "server.database.core.encrypted_documents.get_db",
        return_value=fake_db,
    ):
        backend = SqliteVecBackend(str(path))

        # Check that Phlox created its real metadata tables.
        db = backend._connect()
        try:
            tables = {
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert {"collections", "source_documents", "chunks"} <= tables
        finally:
            db.close()

    # Try opening the database without its encryption key.
    plain = sqlite3.connect(str(path))
    try:
        try:
            plain.execute("SELECT name FROM sqlite_master").fetchall()
        except sqlite3.DatabaseError:
            print("PASS 1: Vector database cannot be read without key")
        else:
            raise AssertionError("FAIL: Vector database is unencrypted")
    finally:
        plain.close()

    print("PASS 2: Phlox vector tables created successfully")
    print("VECTOR ENCRYPTION TEST PASSED")
