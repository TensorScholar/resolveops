"""Optional FastAPI adapter."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from resolveops._version import __version__
from resolveops.bootstrap import build_service
from resolveops.domain.errors import InvalidTransitionError, NotFoundError, PolicyDeniedError
from resolveops.domain.models import CustomerProfile, KnowledgeArticle, Outcome, Ticket


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer: str = Field(min_length=1, max_length=320)
    approve: bool = True
    note: str = Field(default="", max_length=2_000)


def create_app(database: str | Path = "resolveops.db") -> object:
    try:
        from fastapi import FastAPI, HTTPException
    except ImportError as exc:
        raise RuntimeError("Install ResolveOps with the 'web' extra.") from exc

    service = build_service(database)
    app = FastAPI(title="ResolveOps", version=__version__)

    def domain_error(exc: Exception) -> HTTPException:
        if isinstance(exc, NotFoundError):
            return HTTPException(status_code=404, detail=str(exc))
        if isinstance(exc, (InvalidTransitionError, PolicyDeniedError)):
            return HTTPException(status_code=409, detail=str(exc))
        return HTTPException(status_code=400, detail="Request could not be processed.")

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
        except (NotFoundError, InvalidTransitionError, PolicyDeniedError) as exc:
            raise domain_error(exc) from exc

    @app.post("/analyses/{analysis_id}/approve")
    def approve(analysis_id: str, request: ReviewRequest) -> dict[str, object]:
        try:
            approval, execution = service.review(
                analysis_id,
                reviewer=request.reviewer,
                approve=request.approve,
                note=request.note,
            )
        except (NotFoundError, InvalidTransitionError, PolicyDeniedError) as exc:
            raise domain_error(exc) from exc
        return {
            "approval": approval.model_dump(mode="json"),
            "execution": execution.model_dump(mode="json") if execution else None,
        }

    @app.post("/outcomes")
    def outcome(item: Outcome) -> dict[str, str]:
        try:
            service.record_outcome(item)
        except (NotFoundError, InvalidTransitionError, PolicyDeniedError) as exc:
            raise domain_error(exc) from exc
        return {"status": "recorded"}

    @app.get("/metrics")
    def metrics() -> dict[str, object]:
        return service.metrics()

    return app
