"""Encrypted connections for the shared documents database."""

from pathlib import Path

import sqlcipher3 as sqlite3
from server.database.core.connection import get_db


def connect_encrypted_documents(db_path: str | Path) -> sqlite3.Connection:
    """Open a SQLCipher connection using the initialized patient database key."""
    key = get_db().encryption_key
    if not key:
        raise RuntimeError(
            "Database encryption key is unavailable. Initialize the patient database first."
        )

    path = Path(db_path)

    # Existing plaintext databases must be migrated separately before use.
    if path.exists():
        with path.open("rb") as file:
            header = file.read(16)
        if header == b"SQLite format 3\x00":
            raise RuntimeError(
                "Unencrypted documents database detected. Migration is required before opening it."
            )

    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), check_same_thread=False)

    try:
        escaped_key = key.replace("'", "''")
        db.execute(f"PRAGMA key = '{escaped_key}'")
        db.execute("SELECT count(*) FROM sqlite_master")
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA journal_mode=WAL")
        return db
    except Exception:
        db.close()
        raise
