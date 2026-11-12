"""Encounter and letter access between clinicians."""


def test_unassociated_clinician_cannot_read_encounter(api, clinicians, seed_patient):
    alice, bob, _admin = clinicians
    record = seed_patient(alice)

    response = api.get(f"/api/note/id/{record.id}", headers=bob.headers)

    assert response.status_code == 404


def test_unassociated_clinician_cannot_delete_encounter(api, clinicians, seed_patient, stored_records):
    alice, bob, _admin = clinicians
    record = seed_patient(alice)
    before = stored_records(record.ur_number, record.id)

    response = api.delete(f"/api/note/id/{record.id}", headers=bob.headers)

    assert response.status_code == 404
    assert stored_records(record.ur_number, record.id) == before


def test_unassociated_clinician_cannot_read_letter(api, clinicians, seed_patient):
    alice, bob, _admin = clinicians
    record = seed_patient(alice)

    response = api.get(
        "/api/letter/fetch-letter",
        params={"noteId": record.id},
        headers=bob.headers,
    )

    assert response.status_code == 200
    assert response.json() == {"letter": None}


def test_unassociated_clinician_cannot_edit_letter(api, clinicians, seed_patient, stored_records):
    alice, bob, _admin = clinicians
    record = seed_patient(alice)
    before = stored_records(record.ur_number, record.id)

    response = api.post(
        "/api/letter/save",
        json={"noteId": record.id, "letter": "BOB_EDIT"},
        headers=bob.headers,
    )

    assert response.status_code == 404
    assert stored_records(record.ur_number, record.id) == before
