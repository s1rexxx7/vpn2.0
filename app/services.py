import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from yookassa import Configuration, Payment

from app.config import Settings, XUIServerConfig
from app.models import Order, User
from app.keyboards import success_payment_kb

logger = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass(frozen=True)
class Plan:
    code: str
    product_name: str
    months: int
    amount: Decimal
    server_key: str


PLANS: dict[str, Plan] = {
    "germany_1m": Plan(
        code="germany_1m",
        product_name="VPN Германия",
        months=1,
        amount=Decimal("149.00"),
        server_key="germany",
    ),
    "germany_3m": Plan(
        code="germany_3m",
        product_name="VPN Германия",
        months=3,
        amount=Decimal("349.00"),
        server_key="germany",
    ),
    "germany_6m": Plan(
        code="germany_6m",
        product_name="VPN Германия",
        months=6,
        amount=Decimal("600.00"),
        server_key="germany",
    ),
    "germany_12m": Plan(
        code="germany_12m",
        product_name="VPN Германия",
        months=12,
        amount=Decimal("1000.00"),
        server_key="germany",
    ),
    "bypass_1m": Plan(
        code="bypass_1m",
        product_name="Обход глушилок",
        months=1,
        amount=Decimal("299.00"),
        server_key="bypass",
    ),
}


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email.strip()))


class YooKassaService:
    def __init__(self, settings: Settings):
        self.settings = settings
        Configuration.account_id = settings.YOOKASSA_SHOP_ID
        Configuration.secret_key = settings.YOOKASSA_SECRET_KEY
        logger.info("YooKassaService initialized")

    def create_payment(self, order: Order) -> tuple[str, str]:
        payload: dict[str, Any] = {
            "amount": {
                "value": f"{order.amount:.2f}",
                "currency": "RUB",
            },
            "capture": True,
            "confirmation": {
                "type": "redirect",
                "return_url": self.settings.YOOKASSA_RETURN_URL,
            },
            "description": f"{order.product_name} на {order.months} мес.",
            "metadata": {
                "order_id": str(order.id),
                "tg_id": str(order.tg_id),
                "plan_code": order.plan_code,
            },
        }

        if order.receipt_email:
            payload["receipt"] = {
                "customer": {
                    "email": order.receipt_email,
                },
                "items": [
                    {
                        "description": f"{order.product_name} на {order.months} мес.",
                        "quantity": "1.00",
                        "amount": {
                            "value": f"{order.amount:.2f}",
                            "currency": "RUB",
                        },
                        "vat_code": self.settings.YOOKASSA_VAT_CODE,
                        "payment_mode": "full_payment",
                        "payment_subject": "service",
                    }
                ],
                "tax_system_code": self.settings.YOOKASSA_TAX_SYSTEM_CODE,
            }

        logger.info(
            "Creating YooKassa payment: order_id=%s tg_id=%s plan=%s amount=%s receipt_email=%s",
            order.id,
            order.tg_id,
            order.plan_code,
            order.amount,
            order.receipt_email,
        )

        response = Payment.create(payload, str(uuid4()))
        payment_id = response.id
        pay_url = response.confirmation.confirmation_url

        logger.info(
            "YooKassa payment created: order_id=%s payment_id=%s pay_url=%s",
            order.id,
            payment_id,
            pay_url,
        )

        return payment_id, pay_url

    def get_payment(self, payment_id: str):
        logger.info("Fetching YooKassa payment status: payment_id=%s", payment_id)
        payment = Payment.find_one(payment_id)
        logger.info(
            "YooKassa payment fetched: payment_id=%s status=%s paid=%s",
            payment_id,
            getattr(payment, "status", None),
            getattr(payment, "paid", None),
        )
        return payment


class XUIService:
    def __init__(self, server: XUIServerConfig):
        self.server = server

    async def _login(self, client: httpx.AsyncClient) -> None:
        logger.info("3x-ui login start: api_url=%s username=%s", self.server.api_url, self.server.username)

        resp = await client.post(
            "/login",
            data={
                "username": self.server.username,
                "password": self.server.password,
            },
        )
        resp.raise_for_status()

        logger.info("3x-ui login success: api_url=%s", self.server.api_url)

    async def create_client(self, tg_id: int, plan: Plan) -> dict[str, Any]:
        client_uuid = str(uuid4())
        sub_id = uuid4().hex[:16]
        if plan.server_key == "germany":
            email = f"🇩🇪 Германия_{sub_id}"
        elif plan.server_key == "bypass":
            email = f"🚀 Обход глушилок_{sub_id}"
        else:
            email = f"tg{tg_id}"
        expires_at = datetime.utcnow() + timedelta(days=30 * plan.months)
        expiry_ms = int(expires_at.timestamp() * 1000)

        client_payload = {
            "id": client_uuid,
            "flow": self.server.flow,
            "email": email,
            "limitIp": 0,
            "totalGB": 0,
            "expiryTime": expiry_ms,
            "enable": True,
            "tgId": str(tg_id),
            "subId": sub_id,
            "reset": 0,
        }

        logger.info(
            "3x-ui create_client start: tg_id=%s plan=%s inbound_id=%s api_url=%s",
            tg_id,
            plan.code,
            self.server.inbound_id,
            self.server.api_url,
        )
        logger.info("3x-ui client payload: %s", client_payload)

        async with httpx.AsyncClient(
            base_url=self.server.api_url.rstrip("/"),
            verify=False,
            timeout=30.0,
            follow_redirects=True,
        ) as client:
            await self._login(client)

            payload = {
                "id": self.server.inbound_id,
                "settings": json.dumps({"clients": [client_payload]}, ensure_ascii=False),
            }

            logger.info("3x-ui addClient request payload: %s", payload)

            resp = await client.post("/panel/api/inbounds/addClient", json=payload)
            logger.info("3x-ui addClient response status: %s", resp.status_code)
            logger.info("3x-ui addClient response text: %s", resp.text)
            resp.raise_for_status()

            try:
                data = resp.json()
                success = data.get("success", True)
                logger.info("3x-ui addClient response json: %s", data)

                if not success:
                    raise RuntimeError(f"3x-ui addClient error: {data}")
            except Exception:
                logger.exception("Failed to parse 3x-ui addClient JSON or API returned invalid data")
                raise

        sub_url = self.server.sub_template.format(
            public_base_url=self.server.public_base_url.rstrip("/"),
            sub_id=sub_id,
            client_uuid=client_uuid,
            email=email,
        )

        logger.info(
            "3x-ui client created successfully: tg_id=%s plan=%s client_uuid=%s sub_id=%s sub_url=%s expires_at=%s",
            tg_id,
            plan.code,
            client_uuid,
            sub_id,
            sub_url,
            expires_at,
        )

        return {
            "xui_email": email,
            "xui_client_uuid": client_uuid,
            "xui_sub_id": sub_id,
            "sub_url": sub_url,
            "expires_at": expires_at,
        }


class SubscriptionService:
    def __init__(self, settings: Settings, session_maker: async_sessionmaker, bot):
        self.settings = settings
        self.session_maker = session_maker
        self.bot = bot
        self.yookassa = YooKassaService(settings)
        self.xui_services = {
            "germany": XUIService(settings.germany_server),
            "bypass": XUIService(settings.bypass_server),
        }
        logger.info("SubscriptionService initialized")

    async def ensure_user(self, tg_id: int, username: str | None, first_name: str | None) -> None:
        async with self.session_maker() as session:
            result = await session.execute(select(User).where(User.tg_id == tg_id))
            user = result.scalar_one_or_none()
            if user:
                user.username = username
                user.first_name = first_name
                logger.info("User updated: tg_id=%s username=%s", tg_id, username)
            else:
                user = User(
                    tg_id=tg_id,
                    username=username,
                    first_name=first_name,
                )
                session.add(user)
                logger.info("User created: tg_id=%s username=%s", tg_id, username)
            await session.commit()

    async def create_order(
        self,
        tg_id: int,
        username: str | None,
        first_name: str | None,
        plan_code: str,
        receipt_email: str | None = None,
    ) -> Order:
        plan = PLANS[plan_code]

        async with self.session_maker() as session:
            order = Order(
                tg_id=tg_id,
                username=username,
                first_name=first_name,
                plan_code=plan.code,
                product_name=plan.product_name,
                months=plan.months,
                amount=plan.amount,
                receipt_email=receipt_email,
                status="pending",
                server_key=plan.server_key,
            )
            session.add(order)
            await session.commit()
            await session.refresh(order)

            logger.info(
                "Order created: order_id=%s tg_id=%s plan=%s amount=%s receipt_email=%s",
                order.id,
                tg_id,
                plan_code,
                plan.amount,
                receipt_email,
            )

            return order

    async def attach_payment_to_order(self, order_id: int, payment_id: str, payment_url: str) -> None:
        async with self.session_maker() as session:
            result = await session.execute(select(Order).where(Order.id == order_id))
            order = result.scalar_one()
            order.yookassa_payment_id = payment_id
            order.payment_url = payment_url
            await session.commit()

            logger.info(
                "Payment attached to order: order_id=%s payment_id=%s payment_url=%s",
                order_id,
                payment_id,
                payment_url,
            )

    async def create_payment_for_order(self, order_id: int) -> str:
        async with self.session_maker() as session:
            result = await session.execute(select(Order).where(Order.id == order_id))
            order = result.scalar_one()

            payment_id, pay_url = self.yookassa.create_payment(order)
            order.yookassa_payment_id = payment_id
            order.payment_url = pay_url
            await session.commit()

            logger.info(
                "Payment saved to DB: order_id=%s payment_id=%s pay_url=%s",
                order.id,
                payment_id,
                pay_url,
            )

            return pay_url

    async def process_success_payment(self, payment_id: str) -> Order | None:
        logger.info("process_success_payment start: payment_id=%s", payment_id)

        payment = self.yookassa.get_payment(payment_id)
        payment_status = getattr(payment, "status", None)

        if payment_status != "succeeded":
            logger.warning(
                "Payment status is not succeeded: payment_id=%s status=%s",
                payment_id,
                payment_status,
            )
            return None

        async with self.session_maker() as session:
            result = await session.execute(
                select(Order).where(Order.yookassa_payment_id == payment_id)
            )
            order = result.scalar_one_or_none()

            if not order:
                logger.warning("Order not found by payment_id=%s", payment_id)
                return None

            logger.info(
                "Order found by payment_id: order_id=%s status=%s tg_id=%s plan=%s",
                order.id,
                order.status,
                order.tg_id,
                order.plan_code,
            )

            if order.status == "paid" and order.sub_url:
                logger.info(
                    "Order already paid and has sub_url: order_id=%s sub_url=%s",
                    order.id,
                    order.sub_url,
                )
                return order

            plan = PLANS[order.plan_code]
            xui_service = self.xui_services[plan.server_key]

            logger.info(
                "Starting 3x-ui provisioning: order_id=%s payment_id=%s server_key=%s",
                order.id,
                payment_id,
                plan.server_key,
            )

            provision = await xui_service.create_client(order.tg_id, plan)

            logger.info(
                "3x-ui provisioning result: order_id=%s provision=%s",
                order.id,
                provision,
            )

            order.status = "paid"
            order.paid_at = datetime.utcnow()
            order.xui_email = provision["xui_email"]
            order.xui_client_uuid = provision["xui_client_uuid"]
            order.xui_sub_id = provision["xui_sub_id"]
            order.sub_url = provision["sub_url"]
            order.expires_at = provision["expires_at"]

            await session.commit()
            await session.refresh(order)

            logger.info(
                "Order marked as paid: order_id=%s sub_url=%s expires_at=%s",
                order.id,
                order.sub_url,
                order.expires_at,
            )

            return order

    async def get_cabinet_text(self, tg_id: int) -> str:
        async with self.session_maker() as session:
            result = await session.execute(
                select(Order)
                .where(Order.tg_id == tg_id, Order.status == "paid")
                .order_by(desc(Order.created_at))
            )
            orders = result.scalars().all()

        active_orders = [
            order for order in orders
            if order.expires_at and order.expires_at > datetime.utcnow()
        ]

        if not active_orders:
            logger.info("Cabinet requested: tg_id=%s no active subscriptions", tg_id)
            return (
                "👤 <b>Личный кабинет</b>\n\n"
                "У вас пока нет активных подписок."
            )

        lines = ["👤 <b>Личный кабинет</b>\n"]
        for idx, order in enumerate(active_orders, start=1):
            expires_str = order.expires_at.strftime("%d.%m.%Y %H:%M")
            lines.append(
                f"{idx}. <b>{order.product_name}</b>\n"
                f"   Срок: {order.months} мес.\n"
                f"   Действует до: {expires_str}\n"
                f"   sub: <code>{order.sub_url}</code>\n"
            )

        logger.info("Cabinet requested: tg_id=%s active_orders=%s", tg_id, len(active_orders))
        return "\n".join(lines)

    async def send_success_message(self, order: Order) -> None:
        expires_str = order.expires_at.strftime("%d.%m.%Y %H:%M") if order.expires_at else "-"
        text = (
            "✅ Оплата прошла успешно.\n\n"
            f"Ваш продукт: <b>{order.product_name}</b>\n"
            f"Срок: <b>{order.months} мес.</b>\n"
            f"Доступ действует до: <b>{expires_str}</b>\n\n"
            "🔗 Ваша sub-ссылка:\n"
            f"<code>{order.sub_url}</code>\n\n"
            "Сохраните её. Она также доступна в личном кабинете."
        )

        logger.info("Sending success message: order_id=%s tg_id=%s", order.id, order.tg_id)
        await self.bot.send_message(
            order.tg_id,
            text,
            reply_markup=success_payment_kb(),
        )
        logger.info("Success message sent: order_id=%s tg_id=%s", order.id, order.tg_id)

    async def get_order_by_payment_id(self, payment_id: str) -> Order | None:
        async with self.session_maker() as session:
            result = await session.execute(
                select(Order).where(Order.yookassa_payment_id == payment_id)
            )
            order = result.scalar_one_or_none()

            logger.info(
                "get_order_by_payment_id: payment_id=%s found=%s",
                payment_id,
                bool(order),
            )

            return order