from dataclasses import replace

import pytest

from resolveops.domain.audit import make_event, verify_chain
from resolveops.domain.errors import IntegrityError


def test_chain_verifies() -> None:
    first = make_event(
        sequence=1,
        event_type="one",
        entity_id="a",
        payload={"value": 1},
        previous_hash="0" * 64,
    )
    second = make_event(
        sequence=2,
        event_type="two",
        entity_id="b",
        payload={"value": 2},
        previous_hash=first.event_hash,
    )
    verify_chain([first, second])


def test_chain_detects_payload_tamper() -> None:
    event = make_event(
        sequence=1,
        event_type="one",
        entity_id="a",
        payload={"value": 1},
        previous_hash="0" * 64,
    )
    tampered = event.model_copy(update={"payload": {"value": 999}})
    with pytest.raises(IntegrityError):
        verify_chain([tampered])
