"""Offline deterministic response generator."""

from __future__ import annotations

from resolveops.domain.models import Citation, CustomerProfile, Ticket


class DeterministicResponseGenerator:
    """A testable baseline; replace through the ResponseGenerator port."""

    def generate(
        self,
        *,
        ticket: Ticket,
        customer: CustomerProfile,
        citations: tuple[object, ...],
        intent: str,
    ) -> tuple[str, str, float]:
        typed = tuple(item for item in citations if isinstance(item, Citation))
        if typed:
            primary = typed[0]
            summary = f"{intent.replace('_', ' ').title()} request grounded in {primary.title}."
            answer = (
                f"I reviewed your request for account {customer.id}. {primary.excerpt} "
                f"Source: {primary.title} ({primary.source_uri})."
            )
            confidence = min(0.95, 0.65 + sum(item.score for item in typed[:2]) / 3)
            return summary, answer, confidence
        return (
            f"{intent.replace('_', ' ').title()} request without sufficient evidence.",
            (
                "I could not verify the relevant policy from approved sources. "
                "A human specialist should review this request."
            ),
            0.25,
        )
