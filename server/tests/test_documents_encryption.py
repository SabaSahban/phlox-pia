"""Regression tests for encryption of the shared documents database."""

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
import sqlcipher3

from server.database.core import documents_db
from server.database.core import documents_migration as migration
from server.database.core.documents_migration import export_encrypted_copy
from server.database.core.encrypted_documents import connect_encrypted_documents
from server.pdf_forms.storage import PDFFormStore
from server.rag.backends.sqlite_vec import SqliteVecBackend


def _create_plain_database(path: Path, value: str = "FAKE_PATIENT_RECORD") -> None:
    db = sqlite3.connect(str(path))
    try:
        db.execute("CREATE TABLE medical_notes (note TEXT)")
        db.execute("INSERT INTO medical_notes VALUES (?)", (value,))
        db.commit()
    finally:
        db.close()


def _read_encrypted_value(path: Path, key: str) -> str:
    db = sqlcipher3.connect(str(path))
    try:
        escaped_key = key.replace("'", "''")
        db.execute(f"PRAGMA key = '{escaped_key}'")
        return db.execute("SELECT note FROM medical_notes").fetchone()[0]
    finally:
        db.close()


def _read_plain_value(path: Path) -> str:
    db = sqlite3.connect(str(path))
    try:
        return db.execute("SELECT note FROM medical_notes").fetchone()[0]
    finally:
        db.close()


def _assert_plain_sqlite_cannot_read(path: Path) -> None:
    db = sqlite3.connect(str(path))
    try:
        with pytest.raises(sqlite3.DatabaseError):
            db.execute("SELECT name FROM sqlite_master").fetchall()
    finally:
        db.close()


def test_encrypted_documents_round_trip(tmp_path):
    path = tmp_path / "documents.sqlite"
    fake_db = SimpleNamespace(encryption_key="test_password_123")

    with patch("server.database.core.encrypted_documents.get_db", return_value=fake_db):
        db = connect_encrypted_documents(path)
        try:
            db.execute("CREATE TABLE medical_notes (note TEXT)")
            db.execute("INSERT INTO medical_notes VALUES (?)", ("CONFIDENTIAL_TEST_NOTE",))
            db.commit()
        finally:
            db.close()

        _assert_plain_sqlite_cannot_read(path)

        db = connect_encrypted_documents(path)
        try:
            assert db.execute("SELECT note FROM medical_notes").fetchone()[0] == (
                "CONFIDENTIAL_TEST_NOTE"
            )
        finally:
            db.close()


def test_plaintext_documents_database_requires_migration(tmp_path):
    path = tmp_path / "documents.sqlite"
    _create_plain_database(path)
    fake_db = SimpleNamespace(encryption_key="test_password_123")

    with (
        patch("server.database.core.encrypted_documents.get_db", return_value=fake_db),
        pytest.raises(RuntimeError, match="Migration is required"),
    ):
        connect_encrypted_documents(path)


def test_export_encrypted_copy_preserves_source_and_cleans_temporary_files(tmp_path):
    source = tmp_path / "original.sqlite"
    destination = tmp_path / "encrypted.sqlite"
    key = "TEST_MIGRATION_KEY"
    _create_plain_database(source)

    export_encrypted_copy(source, destination, key)

    assert _read_encrypted_value(destination, key) == "FAKE_PATIENT_RECORD"
    assert _read_plain_value(source) == "FAKE_PATIENT_RECORD"
    _assert_plain_sqlite_cannot_read(destination)
    assert not list(tmp_path.glob(".documents_migration_*"))


def test_export_rejects_existing_destination_without_overwriting(tmp_path):
    source = tmp_path / "original.sqlite"
    destination = tmp_path / "encrypted.sqlite"
    _create_plain_database(source)
    destination.write_bytes(b"EXISTING_IMPORTANT_FILE")

    with pytest.raises(FileExistsError):
        export_encrypted_copy(source, destination, "TEST_KEY")

    assert destination.read_bytes() == b"EXISTING_IMPORTANT_FILE"
    assert not list(tmp_path.glob(".documents_migration_*"))


def test_export_rejects_invalid_inputs(tmp_path):
    source = tmp_path / "original.sqlite"
    destination = tmp_path / "encrypted.sqlite"
    _create_plain_database(source)

    with pytest.raises(ValueError, match="Encryption key is required"):
        export_encrypted_copy(source, destination, "")
    with pytest.raises(ValueError, match="must be different"):
        export_encrypted_copy(source, source, "TEST_KEY")
    with pytest.raises(FileNotFoundError):
        export_encrypted_copy(tmp_path / "missing.sqlite", destination, "TEST_KEY")

    assert _read_plain_value(source) == "FAKE_PATIENT_RECORD"
    assert not destination.exists()


def test_export_connection_failure_preserves_source_and_cleans_up(tmp_path):
    source = tmp_path / "original.sqlite"
    destination = tmp_path / "encrypted.sqlite"
    _create_plain_database(source)

    with (
        patch(
            "server.database.core.documents_migration.sqlcipher3.connect",
            side_effect=RuntimeError("SIMULATED_CONNECTION_FAILURE"),
        ),
        pytest.raises(RuntimeError, match="SIMULATED_CONNECTION_FAILURE"),
    ):
        export_encrypted_copy(source, destination, "TEST_KEY")

    assert _read_plain_value(source) == "FAKE_PATIENT_RECORD"
    assert not destination.exists()
    assert not list(tmp_path.glob(".documents_migration_*"))


def test_export_verification_failure_cleans_up(tmp_path):
    source = tmp_path / "original.sqlite"
    destination = tmp_path / "encrypted.sqlite"
    _create_plain_database(source)
    real_connect = migration.sqlcipher3.connect

    def controlled_connect(path, *args, **kwargs):
        if path != ":memory:" and Path(path).name.startswith(".documents_migration_"):
            raise RuntimeError("VERIFICATION_FAILURE")
        return real_connect(path, *args, **kwargs)

    with (
        patch.object(migration.sqlcipher3, "connect", side_effect=controlled_connect),
        pytest.raises(RuntimeError, match="VERIFICATION_FAILURE"),
    ):
        export_encrypted_copy(source, destination, "TEST_KEY")

    assert not destination.exists()
    assert not list(tmp_path.glob(".documents_migration_*"))
    assert _read_plain_value(source) == "FAKE_PATIENT_RECORD"


def test_export_includes_committed_wal_data(tmp_path):
    source = tmp_path / "original.sqlite"
    destination = tmp_path / "encrypted.sqlite"
    db = sqlite3.connect(str(source))
    try:
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA wal_autocheckpoint=0")
        db.execute("CREATE TABLE medical_notes (note TEXT)")
        db.commit()
        db.execute("INSERT INTO medical_notes VALUES (?)", ("FAKE_WAL_MEDICAL_RECORD",))
        db.commit()
        assert Path(f"{source}-wal").exists()

        export_encrypted_copy(source, destination, "TEST_WAL_KEY")
        assert _read_encrypted_value(destination, "TEST_WAL_KEY") == "FAKE_WAL_MEDICAL_RECORD"
    finally:
        db.close()


def test_vector_database_is_encrypted(tmp_path):
    path = tmp_path / "documents.sqlite"
    fake_db = SimpleNamespace(encryption_key="test_password_123")

    with patch("server.database.core.encrypted_documents.get_db", return_value=fake_db):
        backend = SqliteVecBackend(str(path))
        db = backend._connect()
        try:
            tables = {
                row[0]
                for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            assert {"collections", "source_documents", "chunks"} <= tables
        finally:
            db.close()

    _assert_plain_sqlite_cannot_read(path)


def test_pdf_and_vector_storage_share_encrypted_database(tmp_path):
    path = tmp_path / "documents.sqlite"
    fake_db = SimpleNamespace(encryption_key="TEST_KEY_ONLY")

    with (
        patch("server.database.core.encrypted_documents.get_db", return_value=fake_db),
        patch.object(documents_db, "DOCUMENTS_DB_PATH", path),
        patch.object(documents_db, "_simple_connection", None),
    ):
        try:
            PDFFormStore()
            SqliteVecBackend(str(path))
            db = documents_db.get_documents_connection()
            tables = {
                row[0]
                for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            assert "pdf_form_templates" in tables
            assert {"collections", "source_documents", "chunks"} <= tables
            _assert_plain_sqlite_cannot_read(path)
        finally:
            if documents_db._simple_connection is not None:
                documents_db._simple_connection.close()
                documents_db._simple_connection = None


def test_claim_unowned_collections_uses_encrypted_connection(tmp_path):
    from server.database.repositories import users

    path = tmp_path / "documents.sqlite"
    fake_db = SimpleNamespace(encryption_key="TEST_KEY_ONLY")

    with (
        patch("server.database.core.encrypted_documents.get_db", return_value=fake_db),
        patch("server.constants.DATA_DIR", tmp_path),
    ):
        db = connect_encrypted_documents(path)
        try:
            db.execute("CREATE TABLE collections (name TEXT PRIMARY KEY, owner_id INTEGER)")
            db.execute("INSERT INTO collections (name, owner_id) VALUES ('legacy', NULL)")
            db.commit()
        finally:
            db.close()

        users._claim_unowned_collections(42)

        db = connect_encrypted_documents(path)
        try:
            assert db.execute("SELECT owner_id FROM collections WHERE name = 'legacy'").fetchone()[
                0
            ] == 42
        finally:
            db.close()
