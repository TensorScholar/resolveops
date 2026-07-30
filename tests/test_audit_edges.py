import pytest

from resolveops.domain.audit import make_event, verify_chain
from resolveops.domain.errors import IntegrityError


def test_chain_detects_sequence_gap() -> None:
    event = make_event(
        sequence=2,
        event_type="x",
        entity_id="x",
        payload={},
        previous_hash="0" * 64,
    )
    with pytest.raises(IntegrityError):
        verify_chain([event])
