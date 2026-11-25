"""Shared setup for the patient access tests. All records are synthetic."""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.api import auth, letter, patient
from server.database.core.connection import get_db
from server.database.repositories import encounter, users
from server.middleware import LocalTokenMiddleware
from server.schemas.patient import Patient
from server.utils.current_user import CurrentUser, set_current_user
from server.utils.identity_cache import identity_cache


def as_user(person):
    set_current_user(CurrentUser(person.id, person.name, person.role))


@pytest.fixture
def clinicians():
    people = []
    for role in ["clinician", "clinician", "admin"]:
        name = "idor_" + uuid.uuid4().hex[:10]
        digest, salt = auth._new_credentials("Synthetic-IDOR-Password-Only")
        uid = users.create_user(name, digest, salt, role)
        token = users.create_session(uid)
        people.append(
            SimpleNamespace(
                id=uid, name=name, role=role, headers={"Authorization": f"Bearer {token}"}
            )
        )
    yield people
    set_current_user(None)
    identity_cache.invalidate()
    with get_db().transaction() as cursor:
        for person in people:
            cursor.execute("DELETE FROM encounters WHERE created_by = ?", (person.id,))
            cursor.execute("DELETE FROM sessions WHERE user_id = ?", (person.id,))
            cursor.execute("DELETE FROM users WHERE id = ?", (person.id,))
        cursor.execute("DELETE FROM patient_profiles WHERE ur_number LIKE 'IDOR-%'")


@pytest.fixture
def api(monkeypatch):
    from server import constants

    monkeypatch.setattr(constants, "IS_DOCKER", True)
    monkeypatch.setattr(constants, "PHLOX_ALLOW_UNAUTHENTICATED", False)
    identity_cache.invalidate()

    async def no_model(**_kwargs):
        return None

    # Summarization is unrelated to object authorization; never invoke live AI.
    monkeypatch.setattr(patient, "process_encounter_summarization", no_model)
    app = FastAPI()
    app.include_router(patient.router, prefix="/api/note")
    app.include_router(letter.router, prefix="/api/letter")
    app.add_middleware(LocalTokenMiddleware)
    with TestClient(app) as client:
        yield client
    identity_cache.invalidate()


def _new_patient(**changes):
    fields = {
        "name": "Example, Alice",
        "first_name": "Alice",
        "last_name": "Example",
        "dob": "1980-01-01",
        "gender": "F",
        "address": "Synthetic address",
        "phone": "555-SYNTHETIC",
        "ur_number": "IDOR-" + uuid.uuid4().hex,
        "encounter_date": "2026-11-03",
        "template_key": "phlox_01",
        "template_data": {"plan": "Synthetic follow up"},
        "raw_transcription": "SYNTHETIC_PRIVATE_TRANSCRIPT",
        "final_letter": "SYNTHETIC_PRIVATE_LETTER",
    }
    fields.update(changes)
    return Patient(**fields)


def _seed_patient(person, **changes):
    as_user(person)
    record = _new_patient(**changes)
    record.id = encounter.save_patient(record)
    set_current_user(None)
    return record


def _stored_records(ur, note_id):
    """Read the stored profile and encounter for before-and-after checks."""
    set_current_user(None)
    with get_db().read() as cursor:
        profile = cursor.execute(
            "SELECT * FROM patient_profiles WHERE ur_number = ?", (ur,)
        ).fetchone()
        note = cursor.execute("SELECT * FROM encounters WHERE id = ?", (note_id,)).fetchone()
    return {
        "profile": dict(profile) if profile else None,
        "encounter": dict(note) if note else None,
    }


@pytest.fixture
def make_patient():
    return _new_patient


@pytest.fixture
def seed_patient():
    return _seed_patient


@pytest.fixture
def stored_records():
    return _stored_records
