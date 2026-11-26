
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from server.database.core import documents_db
from server.pdf_forms.storage import PDFFormStore
from server.rag.backends.sqlite_vec import SqliteVecBackend

with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    path = Path(folder) / "documents.sqlite"
    fake_db = SimpleNamespace(encryption_key="TEST_KEY_ONLY")

    with (
        patch(
            "server.database.core.encrypted_documents.get_db",
            return_value=fake_db,
        ),
        patch.object(documents_db, "DOCUMENTS_DB_PATH", path),
        patch.object(documents_db, "_simple_connection", None),
    ):
        try:
            # Initialize the real PDF storage.
            pdf_store = PDFFormStore()

            # Initialize the real vector storage on the same file.
            vector_store = SqliteVecBackend(str(path))

            # Check tables created by both components.
            db = documents_db.get_documents_connection()
            tables = {
                row[0]
                for row in db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }

            assert "pdf_form_templates" in tables
            assert {"collections", "source_documents", "chunks"} <= tables

            print("PASS 1: PDF and Vector tables share one database")

            # Verify that ordinary SQLite cannot read the file.
            plain = sqlite3.connect(str(path))
            try:
                try:
                    plain.execute(
                        "SELECT name FROM sqlite_master"
                    ).fetchall()
                except sqlite3.DatabaseError:
                    print("PASS 2: Shared database cannot be read without key")
                else:
                    raise AssertionError("FAIL: Shared database is not encrypted")
            finally:
                plain.close()

            print("SHARED DATABASE TEST PASSED")

        finally:
            if documents_db._simple_connection is not None:
                documents_db._simple_connection.close()
                documents_db._simple_connection = None
