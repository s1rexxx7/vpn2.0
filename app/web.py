import logging
from aiohttp import web

from app.services import SubscriptionService

logger = logging.getLogger(__name__)


def create_web_app(service: SubscriptionService):
    app = web.Application()

    async def yookassa_webhook(request: web.Request):
        try:
            logger.info("Webhook request received: method=%s path=%s", request.method, request.path)

            data = await request.json()
            logger.info("YooKassa webhook payload: %s", data)

            event = data.get("event")
            obj = data.get("object", {})
            payment_id = obj.get("id")

            logger.info("Parsed webhook: event=%s payment_id=%s", event, payment_id)

            if not payment_id:
                logger.warning("Webhook without payment_id: %s", data)
                return web.json_response({"ok": False, "error": "no payment id"}, status=400)

            if event == "payment.succeeded":
                logger.info("Processing successful payment webhook: payment_id=%s", payment_id)

                order = await service.process_success_payment(payment_id)

                if order:
                    logger.info(
                        "Order processed successfully: order_id=%s tg_id=%s sub_url=%s",
                        order.id,
                        order.tg_id,
                        order.sub_url,
                    )
                    await service.send_success_message(order)
                    logger.info("Success message sent to tg_id=%s for order_id=%s", order.tg_id, order.id)
                else:
                    logger.warning(
                        "Webhook payment.succeeded received, but order not processed: payment_id=%s",
                        payment_id,
                    )
            else:
                logger.info("Webhook ignored: unsupported event=%s payment_id=%s", event, payment_id)

            return web.json_response({"ok": True})

        except Exception:
            logger.exception("Webhook processing error")
            return web.json_response({"ok": False}, status=500)

    app.router.add_post("/yookassa/webhook", yookassa_webhook)
    return app