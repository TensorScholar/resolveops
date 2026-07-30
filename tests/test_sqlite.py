from decimal import Decimal

from resolveops.adapters.sqlite import SQLiteStore
from resolveops.domain.models import CustomerProfile, Outcome, Ticket


def test_sqlite_round_trip(tmp_path) -> None:
    store = SQLiteStore(tmp_path / "resolveops.db")
    customer = CustomerProfile(id="c", lifetime_value=Decimal("10"))
    ticket = Ticket(customer_id="c", message="hello")
    store.put_customer(customer)
    store.put_ticket(ticket)
    store.put_outcome(Outcome(ticket_id=ticket.id, resolved=True, escalated=False))
    assert store.get_customer("c") == customer
    assert store.get_ticket(ticket.id) == ticket
    assert len(store.list_outcomes()) == 1
