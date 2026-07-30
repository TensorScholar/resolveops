from resolveops.domain.models import (
    CustomerProfile,
    Disposition,
    EvaluationCase,
    IntentKind,
    Ticket,
)


def test_evaluation_summary(service) -> None:
    summary = service.evaluate_cases(
        [
            EvaluationCase(
                id="case",
                ticket=Ticket(
                    id="eval-ticket",
                    customer_id="eval-customer",
                    message="refund $49",
                ),
                customer=CustomerProfile(id="eval-customer"),
                expected_intent=IntentKind.REFUND,
                expected_disposition=Disposition.REVIEW_REQUIRED,
                expected_article_ids=frozenset({"kb_refund"}),
            )
        ]
    )
    assert summary.intent_accuracy == 1.0
    assert summary.disposition_accuracy == 1.0
    assert summary.citation_recall == 1.0
    assert summary.unsafe_action_rate == 0.0
