"""Optional FastAPI adapter."""

from __future__ import annotations

from pathlib import Path

from resolveops.application.bootstrap import build_service
from resolveops.domain.models import CustomerProfile, KnowledgeArticle, Outcome, Ticket


def create_app(database: str | Path = "resolveops.db") -> object:
    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as exc:
        raise RuntimeError("Install ResolveOps with the 'web' extra.") from exc

    service = build_service(database)
    app = FastAPI(title="ResolveOps", version="0.1.0rc1")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/customers")
    def create_customer(customer: CustomerProfile) -> dict[str, object]:
        service.seed_customer(customer)
        return customer.model_dump(mode="json")

    @app.post("/knowledge")
    def create_article(article: KnowledgeArticle) -> dict[str, object]:
        service.seed_article(article)
        return article.model_dump(mode="json")

    @app.post("/tickets/analyze")
    def analyze(ticket: Ticket) -> dict[str, object]:
        try:
            return service.analyze(ticket).model_dump(mode="json")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/analyses/{analysis_id}/approve")
    def approve(analysis_id: str, reviewer: str, approve: bool = True) -> dict[str, object]:
        try:
            approval, execution = service.review(
                analysis_id, reviewer=reviewer, approve=approve
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {
            "approval": approval.model_dump(mode="json"),
            "execution": execution.model_dump(mode="json") if execution else None,
        }

    @app.post("/outcomes")
    def outcome(item: Outcome) -> dict[str, str]:
        service.record_outcome(item)
        return {"status": "recorded"}

    @app.get("/metrics")
    def metrics() -> dict[str, object]:
        return service.metrics()

    return app
