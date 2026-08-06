"""Command-line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from resolveops._version import __version__
from resolveops.bootstrap import build_service
from resolveops.demo import run_demo
from resolveops.domain.models import CustomerProfile, KnowledgeArticle, Ticket
from resolveops.evaluation import load_cases

app = typer.Typer(help="Evidence-grounded support operations with approval-gated actions.")
console = Console()


def _version(value: bool) -> None:
    if value:
        console.print(f"resolveops {__version__}")
        raise typer.Exit()


@app.callback()
def callback(
    version: Annotated[
        bool | None,
        typer.Option("--version", callback=_version, is_eager=True, help="Show version."),
    ] = None,
) -> None:
    del version


@app.command()
def demo(
    database: Annotated[str | None, typer.Option(help="Optional SQLite database path.")] = None,
) -> None:
    """Run a complete offline support workflow."""
    console.print_json(data=run_demo(database))


@app.command()
def analyze(
    message: Annotated[str, typer.Argument(help="Customer message.")],
    customer_id: Annotated[str, typer.Option()] = "cust_cli",
) -> None:
    """Analyze one message with demo context."""
    service = build_service()
    service.seed_customer(CustomerProfile(id=customer_id, plan="pro"))
    service.seed_article(
        KnowledgeArticle(
            id="kb_general",
            title="General support policy",
            body=(
                "Support requests must be answered from approved evidence. "
                "Financial actions require human approval."
            ),
            source_uri="kb://general",
            owner="support-operations",
        )
    )
    result = service.analyze(Ticket(customer_id=customer_id, message=message))
    console.print_json(data=result.model_dump(mode="json"))


@app.command()
def evaluate(
    fixture: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    """Run an offline evaluation corpus."""
    service = build_service()
    service.seed_article(
        KnowledgeArticle(
            id="kb_refund",
            title="Refund policy",
            body="Refunds require human approval and cannot exceed $250.",
            source_uri="kb://billing/refunds",
            owner="support-operations",
        )
    )
    summary = service.evaluate_cases(load_cases(fixture))
    table = Table(title="ResolveOps evaluation")
    table.add_column("Metric")
    table.add_column("Value", justify="right")
    for key, value in summary.model_dump().items():
        table.add_row(key, str(value))
    console.print(table)


@app.command("verify-audit")
def verify_audit(
    database: Annotated[Path, typer.Argument(exists=True, readable=True)],
) -> None:
    """Verify the hash chain in a SQLite ledger."""
    service = build_service(database)
    service.verify_audit()
    console.print("audit chain valid")


@app.command()
def serve(
    database: Annotated[str, typer.Option()] = "resolveops.db",
    host: Annotated[str, typer.Option()] = "127.0.0.1",
    port: Annotated[int, typer.Option()] = 8080,
) -> None:
    """Run the optional FastAPI service."""
    try:
        import uvicorn
    except ImportError as exc:
        raise typer.BadParameter("Install with: pip install 'resolveops[web]'") from exc
    uvicorn.run("resolveops.web.app:create_app", factory=True, host=host, port=port)


@app.command("export-example")
def export_example(
    path: Annotated[Path, typer.Argument()] = Path("resolveops-example.json"),
) -> None:
    """Write a deterministic demo result."""
    path.write_text(json.dumps(run_demo(), indent=2, default=str), encoding="utf-8")
    console.print(str(path))
