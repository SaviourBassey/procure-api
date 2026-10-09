import logging

from app.services.escrow import ESCROW_EVENT_KEY, fund_escrow

logger = logging.getLogger(__name__)


def register_escrow_listeners(app_emitter) -> None:
    """Fund escrow after msflib-payments verifies the Paystack transaction."""

    @app_emitter.on(f"payment-queue-execute-{ESCROW_EVENT_KEY}")
    async def fund_escrow_after_payment(queue, options):
        session = options["session"]
        payload = queue.data or {}
        order_id = payload.get("order_id")
        if order_id is None:
            raise RuntimeError("Payment queue is missing order_id.")
        logger.info("Funding escrow for order %s", order_id)
        fund_escrow(session, int(order_id))
