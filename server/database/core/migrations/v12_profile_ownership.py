"""Retain profile authorization before the first encounter is saved."""


def migrate(cursor, _db):
    cursor.execute("ALTER TABLE patient_profiles ADD COLUMN created_by INTEGER")
    # Assign existing profiles to the creator of their earliest encounter.
    cursor.execute(
        """UPDATE patient_profiles SET created_by = (
            SELECT e.created_by FROM encounters e
            WHERE e.ur_number = patient_profiles.ur_number AND e.created_by IS NOT NULL
            ORDER BY e.created_at, e.id LIMIT 1
        )"""
    )
    cursor.execute("CREATE INDEX idx_patient_profiles_created_by ON patient_profiles(created_by)")
