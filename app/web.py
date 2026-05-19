import asyncio
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

            if not payment_id:
                logger.warning("Webhook without payment_id: %s", data)
                return web.json_response({"ok": False, "error": "no payment id"}, status=400)

            if event == "payment.succeeded":
                asyncio.create_task(service.handle_successful_payment_webhook(payment_id))
                logger.info("payment.succeeded accepted into background task: %s", payment_id)
            else:
                logger.info("Webhook ignored: event=%s payment_id=%s", event, payment_id)

            return web.json_response({"ok": True})
        except Exception:
            logger.exception("Webhook processing error")
            return web.json_response({"ok": True})

    app.router.add_post("/yookassa/webhook", yookassa_webhook)
    return app