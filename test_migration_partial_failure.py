
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch

from server.database.core.documents_migration import export_encrypted_copy


class SimulatedFailure(Exception):
    pass


with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
    source = Path(folder) / "original.sqlite"
    destination = Path(folder) / "encrypted.sqlite"

    original = sqlite3.connect(str(source))
    try:
        original.execute("CREATE TABLE medical_notes (note TEXT)")
        original.execute(
            "INSERT INTO medical_notes VALUES (?)",
            ("FAKE_PATIENT_RECORD",),
        )
        original.commit()
    finally:
        original.close()

    real_connect = sqlite3.connect

    def failing_connect(*args, **kwargs):
        # This is only a controlled test of cleanup after an error.
        if args and args[0] == ":memory:":
            raise SimulatedFailure("SIMULATED_FAILURE")
        return real_connect(*args, **kwargs)

    # Create a mock destination file to test cleanup.
    destination.write_bytes(b"INCOMPLETE_ENCRYPTED_DATABASE")

    # Remove it before calling the function, so the
    # destination-exists guard does not reject the request.
    destination.unlink()

    with patch(
        "server.database.core.documents_migration.sqlcipher3.connect",
        side_effect=failing_connect,
    ):
        try:
            export_encrypted_copy(source, destination, "TEST_KEY")
        except SimulatedFailure:
            print("PASS 1: Simulated error detected")

    assert not destination.exists()
    print("PASS 2: No incomplete destination remains")

    check = sqlite3.connect(str(source))
    try:
        result = check.execute(
            "SELECT note FROM medical_notes"
        ).fetchone()[0]
        assert result == "FAKE_PATIENT_RECORD"
    finally:
        check.close()

    print("PASS 3: Original database preserved")
    print("PARTIAL FAILURE TEST PASSED")
