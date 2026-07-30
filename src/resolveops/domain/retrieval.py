"""Small, inspectable lexical retriever."""

from __future__ import annotations

import math
import re
from datetime import UTC, datetime

from resolveops.domain.models import Citation, KnowledgeArticle

_TOKEN = re.compile(r"[a-z0-9][a-z0-9_-]+", re.IGNORECASE)


def tokenize(text: str) -> frozenset[str]:
    return frozenset(token.casefold() for token in _TOKEN.findall(text))


def _freshness(article: KnowledgeArticle, now: datetime) -> float:
    age = max(0, (now - article.updated_at).days)
    return 1 / (1 + age / 180)


def retrieve(
    query: str,
    articles: list[KnowledgeArticle],
    *,
    limit: int = 3,
    now: datetime | None = None,
) -> tuple[Citation, ...]:
    current_time = now or datetime.now(UTC)
    query_tokens = tokenize(query)
    if not query_tokens:
        return ()
    ranked: list[tuple[float, KnowledgeArticle]] = []
    for article in articles:
        if not article.approved:
            continue
        if article.expires_at is not None and article.expires_at <= current_time:
            continue
        article_tokens = tokenize(f"{article.title} {article.body}")
        overlap = len(query_tokens & article_tokens)
        if overlap == 0:
            continue
        lexical = overlap / math.sqrt(len(query_tokens) * max(1, len(article_tokens)))
        score = min(1.0, lexical * 1.6 + _freshness(article, current_time) * 0.15)
        ranked.append((score, article))
    ranked.sort(key=lambda pair: (-pair[0], pair[1].id))
    citations: list[Citation] = []
    for score, article in ranked[:limit]:
        excerpt = article.body.strip().split("\n", 1)[0][:320]
        citations.append(
            Citation(
                article_id=article.id,
                title=article.title,
                source_uri=article.source_uri,
                excerpt=excerpt,
                score=round(score, 4),
                updated_at=article.updated_at,
            )
        )
    return tuple(citations)
