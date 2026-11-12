"""The current administrator access rule."""


def test_administrator_retains_existing_encounter_and_letter_access(api, clinicians, seed_patient):
    alice, _bob, admin = clinicians
    record = seed_patient(alice)
    assert api.get(f"/api/note/id/{record.id}", headers=admin.headers).status_code == 200
    assert (
        api.get(
            "/api/letter/fetch-letter", params={"noteId": record.id}, headers=admin.headers
        ).json()["letter"]
        == record.final_letter
    )
