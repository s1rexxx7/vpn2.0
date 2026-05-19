import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4
from html import escape
import httpx
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import async_sessionmaker
from yookassa import Configuration, Payment

from pathlib import Path
from aiogram.types import FSInputFile

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
THANKS_PHOTO = ASSETS_DIR / "thanks.png"

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
    "finland_1m": Plan(
        code="finland_1m",
        product_name="VPN Финляндия",
        months=1,
        amount=Decimal("149.00"),
        server_key="finland",
    ),
    "finland_3m": Plan(
        code="finland_3m",
        product_name="VPN Финляндия",
        months=3,
        amount=Decimal("349.00"),
        server_key="finland",
    ),
    "finland_6m": Plan(
        code="finland_6m",
        product_name="VPN Финляндия",
        months=6,
        amount=Decimal("600.00"),
        server_key="finland",
    ),
    "finland_12m": Plan(
        code="finland_12m",
        product_name="VPN Финляндия",
        months=12,
        amount=Decimal("1000.00"),
        server_key="finland",
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

        response = Payment.create(payload, str(uuid4()))

        logger.info(
            "YooKassa payment created: order_id=%s payment_id=%s status=%s paid=%s receipt_registration=%s",
            order.id,
            response.id,
            getattr(response, "status", None),
            getattr(response, "paid", None),
            getattr(response, "receipt_registration", None),
        )

        payment_id = response.id
        pay_url = response.confirmation.confirmation_url
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
        if plan.server_key == "finland":
            email = f"🇫🇮 Финляндия_{sub_id}"
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
            "finland": XUIService(settings.finland_server),
            "bypass": XUIService(settings.bypass_server),
        }

        self._payment_locks: dict[str, asyncio.Lock] = {}
        logger.info("SubscriptionService initialized")
        logger.info("SubscriptionService initialized")

    def is_admin(self, tg_id: int) -> bool:
        return tg_id in self.settings.ADMIN_IDS


    def _get_payment_lock(self, payment_id: str) -> asyncio.Lock:
        lock = self._payment_locks.get(payment_id)
        if lock is None:
            lock = asyncio.Lock()
            self._payment_locks[payment_id] = lock
        return lock

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
            order.status = "payment_created"
            order.last_error = None

            await session.commit()
            return pay_url
        
    async def get_order_by_payment_id(self, payment_id: str) -> Order | None:
        async with self.session_maker() as session:
            result = await session.execute(
                select(Order).where(Order.yookassa_payment_id == payment_id)
            )
            return result.scalar_one_or_none()


    async def get_order_by_id(self, order_id: int) -> Order | None:
        async with self.session_maker() as session:
            result = await session.execute(select(Order).where(Order.id == order_id))
            return result.scalar_one_or_none()


    async def mark_order_warning_sent(self, payment_id: str, error_text: str) -> None:
        async with self.session_maker() as session:
            result = await session.execute(
                select(Order).where(Order.yookassa_payment_id == payment_id)
            )
            order = result.scalar_one_or_none()
            if not order:
                return

            order.status = "provision_error"
            order.last_error = error_text[:4000]
            order.last_warning_sent_at = datetime.utcnow()
            await session.commit()

    async def process_success_payment(self, payment_id: str) -> Order | None:
        logger.info("process_success_payment start: payment_id=%s", payment_id)

        payment = self.yookassa.get_payment(payment_id)
        payment_status = getattr(payment, "status", None)
        logger.info(
            "Payment status check: payment_id=%s status=%s paid=%s receipt_registration=%s",
            payment_id,
            getattr(payment, "status", None),
            getattr(payment, "paid", None),
            getattr(payment, "receipt_registration", None),
        )

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
        
    async def handle_successful_payment_webhook(self, payment_id: str) -> None:
        try:
            order = await self.process_success_payment(payment_id)
            if order and order.sub_url:
                await self.send_success_message(order)
        except Exception:
            logger.exception("Unhandled background payment processing error: %s", payment_id)

    async def send_provision_warning(self, payment_id: str) -> None:
        order = await self.get_order_by_payment_id(payment_id)
        if not order:
            return

        text = (
            "⚠️ Оплата получена, но выдать доступ автоматически пока не удалось.\n\n"
            "Мы уже сохранили заказ и попробуем обработать его повторно.\n"
            "Через минуту можно нажать кнопку «Проверить оплату» в сообщении со ссылкой на оплату.\n\n"
            "Если проблема не исчезнет — напишите в поддержку и пришлите ID оплаты:\n"
            f"<code>{payment_id}</code>"
        )

        try:
            await self.bot.send_message(chat_id=order.tg_id, text=text)
        except Exception:
            logger.exception("Failed to send warning message to tg_id=%s", order.tg_id)

    async def check_and_describe_order_payment(self, tg_id: int, order_id: int) -> str:
        order = await self.get_order_by_id(order_id)
        if not order or order.tg_id != tg_id:
            return "Заказ не найден."

        if order.status == "paid" and order.sub_url:
            return "Оплата уже подтверждена, доступ выдан."

        if not order.yookassa_payment_id:
            return "У заказа пока нет ID оплаты. Попробуйте создать оплату заново."

        try:
            payment = self.yookassa.get_payment(order.yookassa_payment_id)
        except Exception:
            logger.exception("Manual payment check failed: order_id=%s", order_id)
            return "Не удалось проверить оплату прямо сейчас. Попробуйте чуть позже."

        payment_status = getattr(payment, "status", None)

        if payment_status == "succeeded":
            processed_order = await self.process_success_payment(order.yookassa_payment_id)
            if processed_order and processed_order.sub_url:
                await self.send_success_message(processed_order)
                return "Оплата подтверждена. Доступ выдан."
            return "Оплата есть, но доступ ещё выдаётся. Подождите немного и откройте кабинет."

        if payment_status in {"pending", "waiting_for_capture"}:
            return "Оплата ещё не подтверждена. Если вы уже оплатили — подождите 30–60 секунд и проверьте снова."

        if payment_status == "canceled":
            return "Платёж отменён или не завершён."

        return f"Текущий статус платежа: {payment_status or 'неизвестно'}"
    
    async def broadcast_message(
        self,
        text: str,
        initiated_by: int,
        parse_mode: str | None = "HTML",
    ) -> dict[str, int]:
        async with self.session_maker() as session:
            result = await session.execute(select(User.tg_id).order_by(User.id))
            tg_ids = list(result.scalars().all())

        sent = 0
        failed = 0

        for tg_id in tg_ids:
            try:
                await self.bot.send_message(
                    chat_id=tg_id,
                    text=text,
                    parse_mode=parse_mode,
                )
                sent += 1
            except Exception:
                failed += 1
                logger.exception(
                    "Broadcast send failed: initiated_by=%s target_tg_id=%s",
                    initiated_by,
                    tg_id,
                )
            await asyncio.sleep(0.03)

        return {
            "total": len(tg_ids),
            "sent": sent,
            "failed": failed,
        }

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
        lines.append(
            "📲 Как подключиться:\n"
            "1. Установите клиент V2RayTun, Happ или другой совместимый клиент.\n"
            "2. Откройте приложение и нажмите на «+».\n"
            "3. Вставьте купленную ссылку.\n"
            "4. Пользуйтесь!"
        )

        return "\n".join(lines)

    async def send_success_message(self, order: Order) -> None:
        expires_str = order.expires_at.strftime("%d.%m.%Y %H:%M") if order.expires_at else "-"

        text = (
            "✅ Спасибо за покупку!\n\n"
            f"Ваш продукт: <b>{order.product_name}</b>\n"
            f"Срок: <b>{order.months} мес.</b>\n"
            f"Доступ действует до: <b>{expires_str}</b>\n\n"
            "Ваша sub-ссылка:\n"
            f"<code>{order.sub_url}</code>\n\n"
            "\n\n📲 Как подключиться:\n"
            "1. Установите клиент V2RayTun, Happ или другой совместимый клиент.\n"
            "2. Откройте приложение и нажмите на «+».\n"
            "3. Вставьте купленную ссылку.\n"
            "4. Пользуйтесь!"   
        )

        logger.info("Sending success message with photo: order_id=%s tg_id=%s", order.id, order.tg_id)

        await self.bot.send_photo(
            chat_id=order.tg_id,
            photo=FSInputFile(THANKS_PHOTO),
            caption=text,
            reply_markup=success_payment_kb(),
        )

        logger.info("Success photo message sent: order_id=%s tg_id=%s", order.id, order.tg_id)

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