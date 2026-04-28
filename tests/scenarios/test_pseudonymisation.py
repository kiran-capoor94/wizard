"""Behaviour tests for PseudonymStore and SecurityService pseudonymisation."""

import pytest
from sqlalchemy import text
from sqlmodel import create_engine

from wizard.security import PseudonymStore, SecurityService


@pytest.fixture
def mem_engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False})
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE pseudonym_map ("
            "id INTEGER PRIMARY KEY, "
            "original_hash TEXT NOT NULL UNIQUE, "
            "entity_type TEXT NOT NULL, "
            "fake_value TEXT NOT NULL, "
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
            ")"
        ))
        conn.commit()
    return engine


@pytest.fixture
def store(mem_engine):
    return PseudonymStore(engine=mem_engine)


class TestPseudonymStore:
    def test_same_input_returns_same_fake(self, store):
        v1 = store.get_or_create("John Smith", "PERSON", lambda: "Fake Name A")
        v2 = store.get_or_create("John Smith", "PERSON", lambda: "Fake Name B")
        assert v1 == v2

    def test_case_insensitive_match(self, store):
        v1 = store.get_or_create("john smith", "PERSON", lambda: "Fake Alpha")
        v2 = store.get_or_create("John Smith", "PERSON", lambda: "Fake Beta")
        assert v1 == v2

    def test_different_inputs_different_fakes(self, store):
        v1 = store.get_or_create("Alice Jones", "PERSON", lambda: "Fake 1")
        v2 = store.get_or_create("Bob Davis", "PERSON", lambda: "Fake 2")
        assert v1 != v2

    def test_entity_type_scoped(self, store):
        v1 = store.get_or_create("alice", "PERSON", lambda: "Alice Fake")
        v2 = store.get_or_create("alice", "EMAIL", lambda: "fake@example.com")
        assert v1 == "Alice Fake"
        assert v2 == "fake@example.com"

    def test_generator_called_once(self, store):
        calls = []

        def gen():
            calls.append(1)
            return "Generated Name"

        store.get_or_create("New Person", "PERSON", gen)
        store.get_or_create("New Person", "PERSON", gen)
        assert len(calls) == 1


class TestSecurityServiceWithStore:
    def test_name_replaced_with_fake(self, store):
        sec = SecurityService(store=store)
        result = sec.scrub("Meeting with John Smith today.")
        assert "John Smith" not in result.clean
        assert result.was_modified

    def test_store_none_falls_back_to_stub(self):
        sec = SecurityService(store=None)
        result = sec.scrub("Meeting with John Smith today.")
        assert "John Smith" not in result.clean
        assert "[PERSON_" in result.clean

    def test_existing_patterns_still_work(self, store):
        sec = SecurityService(store=store)
        result = sec.scrub("Email: user@example.com phone: +447911123456")
        assert "user@example.com" not in result.clean
        assert "+447911123456" not in result.clean

    def test_allowlist_skips_name(self):
        sec = SecurityService(allowlist=["John Smith"], store=None)
        result = sec.scrub("Meeting with John Smith today.")
        assert "John Smith" in result.clean

    def test_scrub_none_returns_empty(self, store):
        sec = SecurityService(store=store)
        result = sec.scrub(None)
        assert result.clean == ""
        assert not result.was_modified

    def test_same_name_consistent_across_calls(self, store):
        sec = SecurityService(store=store)
        r1 = sec.scrub("John Smith sent the report.")
        r2 = sec.scrub("Follow up with John Smith.")
        assert "John Smith" not in r1.clean
        assert "John Smith" not in r2.clean
        fake1 = r1.original_to_stub.get("John Smith")
        fake2 = r2.original_to_stub.get("John Smith")
        assert fake1 is not None
        assert fake1 == fake2
