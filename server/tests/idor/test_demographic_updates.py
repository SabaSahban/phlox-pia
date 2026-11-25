"""An unauthorized update must leave both stored records unchanged."""


def test_foreign_encounter_update_cannot_change_any_patient_demographics(api, clinicians, seed_patient, stored_records):
    alice, bob, _admin = clinicians
    record = seed_patient(alice)
    before = stored_records(record.ur_number, record.id)
    altered = record.model_copy(
        update={
            "first_name": "CORRUPTED",
            "dob": "2001-02-03",
            "phone": "UNAUTHORIZED",
            "template_data": {"plan": "BOB_PLAN"},
        }
    )
    response = api.post(
        "/api/note/save", headers=bob.headers, json={"patientData": altered.model_dump()}
    )

    assert response.status_code == 404
    assert stored_records(record.ur_number, record.id) == before
