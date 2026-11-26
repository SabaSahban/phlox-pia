"""Access to an existing patient's consent decision."""


def test_unassociated_clinician_cannot_read_consent(api, clinicians, seed_patient):
    alice, bob, _admin = clinicians
    record = seed_patient(alice)
    decision = {"ur_number": record.ur_number, "consented": False}
    assert api.post("/api/note/consent", headers=alice.headers, json=decision).status_code == 200

    response = api.get(
        "/api/note/consent", params={"ur_number": record.ur_number}, headers=bob.headers
    )

    assert response.status_code == 404
    assert "scribe_consent_declined_at" not in response.json()


def test_unassociated_clinician_cannot_change_consent(api, clinicians, seed_patient, stored_records):
    alice, bob, _admin = clinicians
    record = seed_patient(alice)
    decision = {"ur_number": record.ur_number, "consented": False}
    assert api.post("/api/note/consent", headers=alice.headers, json=decision).status_code == 200
    before = stored_records(record.ur_number, record.id)["profile"]

    response = api.post(
        "/api/note/consent",
        headers=bob.headers,
        json={"ur_number": record.ur_number, "consented": True},
    )

    assert response.status_code == 404
    assert stored_records(record.ur_number, record.id)["profile"] == before
