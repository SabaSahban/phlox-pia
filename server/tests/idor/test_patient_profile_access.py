"""Patient profile associations and the name lookup candidate list."""

from server.database.core.connection import get_db
from server.database.repositories.patient_search import get_patient_name_index
from server.utils.current_user import CurrentUser, set_current_user


def test_unassociated_clinician_cannot_create_encounter_for_foreign_profile(api, clinicians, seed_patient, stored_records, make_patient):
    alice, bob, _admin = clinicians
    foreign = seed_patient(alice)
    before = stored_records(foreign.ur_number, foreign.id)
    draft = make_patient(ur_number=foreign.ur_number)
    with get_db().read() as cursor:
        count_before = cursor.execute(
            "SELECT COUNT(*) FROM encounters WHERE created_by = ?", (bob.id,)
        ).fetchone()[0]

    response = api.post(
        "/api/note/save", headers=bob.headers, json={"patientData": draft.model_dump()}
    )

    assert response.status_code == 404
    assert stored_records(foreign.ur_number, foreign.id) == before
    with get_db().read() as cursor:
        count_after = cursor.execute(
            "SELECT COUNT(*) FROM encounters WHERE created_by = ?", (bob.id,)
        ).fetchone()[0]
    assert count_after == count_before


def test_unassociated_clinician_cannot_move_encounter_to_foreign_profile(api, clinicians, seed_patient, stored_records):
    alice, bob, _admin = clinicians
    foreign = seed_patient(alice)
    own = seed_patient(bob)
    foreign_before = stored_records(foreign.ur_number, foreign.id)
    own_before = stored_records(own.ur_number, own.id)
    edited = own.model_copy(update={"ur_number": foreign.ur_number})

    response = api.post(
        "/api/note/save", headers=bob.headers, json={"patientData": edited.model_dump()}
    )

    assert response.status_code == 404
    assert stored_records(own.ur_number, own.id) == own_before
    assert stored_records(foreign.ur_number, foreign.id) == foreign_before


def test_patient_name_index_only_lists_accessible_profiles(clinicians, seed_patient):
    alice, bob, _admin = clinicians
    foreign = seed_patient(alice)
    own = seed_patient(bob)

    set_current_user(CurrentUser(bob.id, bob.name, bob.role))
    try:
        visible_urs = {entry["ur_number"] for entry in get_patient_name_index()}
    finally:
        set_current_user(None)

    assert own.ur_number in visible_urs
    assert foreign.ur_number not in visible_urs
