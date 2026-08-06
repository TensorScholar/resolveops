from datetime import datetime

import pytest
from pydantic import ValidationError

from resolveops.domain.models import Ticket


def test_extra_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        Ticket.model_validate({"customer_id": "c", "message": "x", "unexpected": True})


def test_naive_timestamp_rejected() -> None:
    with pytest.raises(ValidationError):
        Ticket(customer_id="c", message="x", received_at=datetime.now())
