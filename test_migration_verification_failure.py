
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

import server.database.core.documents_migration as migration


class SimulatedFailure(Exception):
    pass


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

    real_connect = migration.sqlcipher3.connect

    def controlled_connect(*args, **kwargs):
        # Allow the export connection, but fail when
        # the function opens the destination for verification.
        if args and str(args[0]) == str(destination):
            assert destination.exists()
            print("PASS 1: Destination existed before failure")
            raise SimulatedFailure("VERIFICATION_FAILURE")

        return real_connect(*args, **kwargs)

    with patch.object(
        migration.sqlcipher3,
        "connect",
        side_effect=controlled_connect,
    ):
        try:
            migration.export_encrypted_copy(
                source, destination, "TEST_KEY"
            )
        except SimulatedFailure:
            print("PASS 2: Verification failure detected")
        else:
            raise AssertionError("Expected simulated failure")

    assert not destination.exists()
    assert not Path(str(destination) + "-wal").exists()
    assert not Path(str(destination) + "-shm").exists()
    print("PASS 3: Incomplete destination cleaned up")

    original = sqlite3.connect(str(source))
    try:
        note = original.execute(
            "SELECT note FROM medical_notes"
        ).fetchone()[0]
        assert note == "FAKE_PATIENT_RECORD"
    finally:
        original.close()

    print("PASS 4: Original data preserved")
    print("VERIFICATION FAILURE TEST PASSED")

