from datetime import UTC, datetime, timedelta

from resolveops.domain.models import KnowledgeArticle
from resolveops.domain.retrieval import retrieve


def article(identifier: str, body: str, **kwargs: object) -> KnowledgeArticle:
    return KnowledgeArticle(
        id=identifier,
        title=identifier,
        body=body,
        source_uri=f"kb://{identifier}",
        owner="test",
        **kwargs,
    )


def test_retrieval_ranks_overlap() -> None:
    results = retrieve(
        "refund duplicate charge",
        [
            article("refund", "Duplicate charges may qualify for a refund."),
            article("password", "Reset your password."),
        ],
    )
    assert [item.article_id for item in results] == ["refund"]


def test_retrieval_excludes_unapproved_and_expired() -> None:
    now = datetime.now(UTC)
    results = retrieve(
        "refund",
        [
            article("unapproved", "refund", approved=False),
            article("expired", "refund", expires_at=now - timedelta(seconds=1)),
        ],
        now=now,
    )
    assert results == ()


def test_retrieval_excludes_future_dated_articles() -> None:
    now = datetime.now(UTC)
    results = retrieve(
        "refund",
        [article("future", "refund", updated_at=now + timedelta(days=1))],
        now=now,
    )
    assert results == ()
