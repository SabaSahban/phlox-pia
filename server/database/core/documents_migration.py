
"""Utilities for migrating plaintext documents databases to SQLCipher."""

import os
import tempfile
from pathlib import Path

import sqlcipher3


def export_encrypted_copy(
    source_path: str | Path,
    destination_path: str | Path,
    encryption_key: str,
) -> None:
    """Create and verify an encrypted copy without modifying the source."""
    source = Path(source_path).resolve()
    destination = Path(destination_path).resolve()

    if source == destination:
        raise ValueError("Source and destination must be different")

    if not source.is_file():
        raise FileNotFoundError(f"Source database not found: {source}")

    if destination.exists():
        raise FileExistsError(f"Destination already exists: {destination}")

    if not encryption_key:
        raise ValueError("Encryption key is required")

    destination.parent.mkdir(parents=True, exist_ok=True)

    # Create a unique temporary file in the destination directory.
    fd, temporary_name = tempfile.mkstemp(
        prefix=".documents_migration_",
        suffix=".sqlite",
        dir=str(destination.parent),
    )
    os.close(fd)
    temporary = Path(temporary_name)

    db = None

    try:
        # SQLCipher needs a path that does not already contain a database.
        temporary.unlink()

        db = sqlcipher3.connect(":memory:")
        db.execute(
            "ATTACH DATABASE ? AS plaintext KEY ''",
            (str(source),),
        )
        db.execute(
            "ATTACH DATABASE ? AS encrypted KEY ?",
            (str(temporary), encryption_key),
        )
        db.execute("SELECT sqlcipher_export('encrypted', 'plaintext')")
        db.commit()

        db.execute("DETACH DATABASE encrypted")
        db.execute("DETACH DATABASE plaintext")
        db.close()
        db = None

        # Verify the encrypted copy before publishing it.
        check = sqlcipher3.connect(str(temporary))
        try:
            escaped_key = encryption_key.replace("'", "''")
            check.execute(f"PRAGMA key = '{escaped_key}'")

            result = check.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0]

            if result != "ok":
                raise RuntimeError(
                    f"Encrypted database integrity check failed: {result}"
                )
        finally:
            check.close()

        # Publish without overwriting an existing destination.
        os.link(str(temporary), str(destination))

    finally:
        if db is not None:
            db.close()

        for suffix in ("-wal", "-shm", ""):
            candidate = Path(str(temporary) + suffix)
            if candidate.exists():
                candidate.unlink()
