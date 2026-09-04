"""Dedicated FastAPI ingress for authenticated Stripe webhooks."""

from resolveops.application.outcomes import OutcomeVerificationUnavailableError
from resolveops.application.stripe_webhooks import (
    StripeWebhookProcessor,
    StripeWebhookProtocolError,
    StripeWebhookSignatureError,
)
from resolveops.domain.errors import IntegrityError, NotFoundError

_MAX_WEBHOOK_BODY_BYTES = 256 * 1024
_MAX_SIGNATURE_HEADER_BYTES = 8 * 1024


def create_stripe_webhook_app(processor: StripeWebhookProcessor) -> object:
    """Create a minimal Stripe-only webhook ingress surface."""
    try:
        from fastapi import FastAPI, HTTPException, Request
    except ImportError as exc:
        raise RuntimeError("Install ResolveOps with the 'web' extra.") from exc

    app = FastAPI(title="ResolveOps Stripe Webhook")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/webhooks/stripe")
    async def stripe_webhook(request: Request) -> dict[str, str]:
        signature = request.headers.get("stripe-signature")
        if not signature or len(signature.encode()) > _MAX_SIGNATURE_HEADER_BYTES:
            raise HTTPException(status_code=400, detail="Invalid Stripe webhook signature.")
        body = await request.body()
        if len(body) > _MAX_WEBHOOK_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Stripe webhook body is too large.")
        try:
            return processor.process(body, signature)
        except (StripeWebhookSignatureError, StripeWebhookProtocolError) as exc:
            raise HTTPException(status_code=400, detail="Invalid Stripe webhook.") from exc
        except (NotFoundError, OutcomeVerificationUnavailableError) as exc:
            # A valid event can race local execution persistence or a provider-current read can be
            # temporarily unavailable. A non-2xx response preserves Stripe's retry path; neither
            # condition consumes the event identity.
            raise HTTPException(
                status_code=503,
                detail="Stripe webhook processing is temporarily unavailable.",
            ) from exc
        except IntegrityError as exc:
            raise HTTPException(
                status_code=409,
                detail="Stripe webhook conflicts with persisted execution state.",
            ) from exc

    return app
