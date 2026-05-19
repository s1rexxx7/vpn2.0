from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from app.keyboards import (
    back_to_main_kb,
    buy_menu_kb,
    bypass_plans_kb,
    cabinet_kb,
    finland_plans_kb,
    main_menu_kb,
    payment_kb,
    receipt_choice_kb,
    skip_email_kb,
)
from app.services import PLANS, SubscriptionService, is_valid_email
from app.states import PurchaseState
from app.texts import (
    ASK_EMAIL_TEXT,
    BUY_MENU_TEXT,
    BYPASS_TEXT,
    FINLAND_TEXT,
    PAYMENT_CREATED_TEXT,
    RECEIPT_ASK_TEXT,
    START_TEXT,
)

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"

MAIN_MENU_PHOTO = ASSETS_DIR / "main_menu.png"
PRODUCTS_PHOTO = ASSETS_DIR / "products.png"
ORDER_PHOTO = ASSETS_DIR / "order.png"
CABINET_PHOTO = ASSETS_DIR / "cabinet.png"


async def send_photo_screen(
    target: Message,
    photo_path: Path,
    caption: str,
    reply_markup,
):
    await target.answer_photo(
        photo=FSInputFile(photo_path),
        caption=caption,
        reply_markup=reply_markup,
    )


async def replace_with_photo(
    callback: CallbackQuery,
    photo_path: Path,
    caption: str,
    reply_markup,
):
    try:
        await callback.message.delete()
    except Exception:
        pass

    await callback.message.answer_photo(
        photo=FSInputFile(photo_path),
        caption=caption,
        reply_markup=reply_markup,
    )
    await callback.answer()


def get_router(service: SubscriptionService) -> Router:
    router = Router()

    @router.message(CommandStart())
    async def start_handler(message: Message, state: FSMContext):
        await state.clear()
        await service.ensure_user(
            tg_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )
        await send_photo_screen(
            target=message,
            photo_path=MAIN_MENU_PHOTO,
            caption=START_TEXT,
            reply_markup=main_menu_kb(),
        )

    @router.callback_query(F.data == "menu:main")
    async def menu_main(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await replace_with_photo(
            callback=callback,
            photo_path=MAIN_MENU_PHOTO,
            caption=START_TEXT,
            reply_markup=main_menu_kb(),
        )

    @router.callback_query(F.data == "menu:buy")
    async def menu_buy(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        await replace_with_photo(
            callback=callback,
            photo_path=PRODUCTS_PHOTO,
            caption=BUY_MENU_TEXT,
            reply_markup=buy_menu_kb(),
        )

    @router.callback_query(F.data == "product:finland")
    async def product_finland(callback: CallbackQuery):
        await replace_with_photo(
            callback=callback,
            photo_path=PRODUCTS_PHOTO,
            caption=FINLAND_TEXT,
            reply_markup=finland_plans_kb(),
        )

    @router.callback_query(F.data == "product:bypass")
    async def product_bypass(callback: CallbackQuery):
        await replace_with_photo(
            callback=callback,
            photo_path=PRODUCTS_PHOTO,
            caption=BYPASS_TEXT,
            reply_markup=bypass_plans_kb(),
        )

    @router.callback_query(F.data.startswith("plan:"))
    async def choose_plan(callback: CallbackQuery, state: FSMContext):
        plan_code = callback.data.split(":", 1)[1]
        if plan_code not in PLANS:
            await callback.answer("Неизвестный тариф", show_alert=True)
            return

        await state.update_data(plan_code=plan_code)
        await replace_with_photo(
            callback=callback,
            photo_path=ORDER_PHOTO,
            caption=RECEIPT_ASK_TEXT,
            reply_markup=receipt_choice_kb(),
        )

    @router.callback_query(F.data == "receipt:yes")
    async def receipt_yes(callback: CallbackQuery, state: FSMContext):
        await state.set_state(PurchaseState.waiting_receipt_email)
        await replace_with_photo(
            callback=callback,
            photo_path=ORDER_PHOTO,
            caption=ASK_EMAIL_TEXT,
            reply_markup=skip_email_kb(),
        )

    @router.callback_query(F.data == "receipt:no")
    async def receipt_no(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        plan_code = data.get("plan_code")
        if not plan_code:
            await callback.answer("Сначала выберите тариф", show_alert=True)
            return

        await start_payment_flow_from_callback(
            callback=callback,
            state=state,
            service=service,
            plan_code=plan_code,
            receipt_email=None,
        )

    @router.callback_query(F.data == "receipt:skip_email")
    async def receipt_skip_email(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        plan_code = data.get("plan_code")
        if not plan_code:
            await callback.answer("Сначала выберите тариф", show_alert=True)
            return

        await start_payment_flow_from_callback(
            callback=callback,
            state=state,
            service=service,
            plan_code=plan_code,
            receipt_email=None,
        )

    @router.message(PurchaseState.waiting_receipt_email)
    async def receipt_email_handler(message: Message, state: FSMContext):
        email = (message.text or "").strip()
        if not is_valid_email(email):
            await message.answer(
                "Некорректный email.\n"
                "Отправьте корректный адрес или нажмите «Пропустить».",
                reply_markup=skip_email_kb(),
            )
            return

        data = await state.get_data()
        plan_code = data.get("plan_code")
        if not plan_code:
            await state.clear()
            await message.answer(
                "Тариф не найден.\nНачните заново.",
                reply_markup=back_to_main_kb(),
            )
            return

        await start_payment_flow_from_message(
            message=message,
            state=state,
            service=service,
            plan_code=plan_code,
            receipt_email=email,
        )

    @router.callback_query(F.data.startswith("payment:check:"))
    async def payment_check(callback: CallbackQuery):
        try:
            order_id = int(callback.data.split(":")[-1])
        except Exception:
            await callback.answer("Некорректный заказ", show_alert=True)
            return

        status_text = await service.check_and_describe_order_payment(
            tg_id=callback.from_user.id,
            order_id=order_id,
        )
        await callback.answer(status_text, show_alert=True)

    @router.callback_query(F.data == "menu:cabinet")
    async def menu_cabinet(callback: CallbackQuery, state: FSMContext):
        await state.clear()
        text = await service.get_cabinet_text(callback.from_user.id)
        await replace_with_photo(
            callback=callback,
            photo_path=CABINET_PHOTO,
            caption=text,
            reply_markup=cabinet_kb(),
        )

    @router.message(Command("say"))
    async def admin_say_handler(message: Message, command: CommandObject):
        if not service.is_admin(message.from_user.id):
            await message.answer("Эта команда доступна только администратору.")
            return

        text = (command.args or "").strip()
        if not text:
            await message.answer("Использование: /say ваш текст для рассылки")
            return

        stats = await service.broadcast_message(
            text=text,
            initiated_by=message.from_user.id,
            parse_mode=None,
        )
        await message.answer(
            "📣 Рассылка завершена.\n\n"
            f"Отправлено: {stats['sent']}\n"
            f"Ошибок: {stats['failed']}\n"
            f"Всего пользователей: {stats['total']}"
        )


    @router.message(Command("say_html"))
    async def admin_say_html_handler(message: Message, command: CommandObject):
        if not service.is_admin(message.from_user.id):
            await message.answer("Эта команда доступна только администратору.")
            return

        text = (command.args or "").strip()
        if not text:
            await message.answer(
                "Использование:\n"
                "/say_html <b>Важная новость</b>\n"
                "Доступны HTML-теги Telegram: "
                "<b>, <i>, <u>, <s>, <code>, <pre>, <a href='...'>"
            )
            return

        stats = await service.broadcast_message(
            text=text,
            initiated_by=message.from_user.id,
            parse_mode="HTML",
        )
        await message.answer(
            "📣 HTML-рассылка завершена.\n\n"
            f"Отправлено: {stats['sent']}\n"
            f"Ошибок: {stats['failed']}\n"
            f"Всего пользователей: {stats['total']}"
        )

    return router

async def start_payment_flow_from_callback(
    callback: CallbackQuery,
    state: FSMContext,
    service: SubscriptionService,
    plan_code: str,
    receipt_email: str | None,
):
    try:
        order = await service.create_order(
            tg_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
            plan_code=plan_code,
            receipt_email=receipt_email,
        )
        pay_url = await service.create_payment_for_order(order.id)
    except Exception:
        await state.clear()
        await callback.message.answer(
            "⚠️ Не удалось создать оплату прямо сейчас.\n"
            "Попробуйте ещё раз чуть позже.\n\n"
            "Если деньги уже списались или ошибка повторяется — напишите в поддержку.",
            reply_markup=back_to_main_kb(),
        )
        return

    await state.clear()
    await replace_with_photo(
        callback=callback,
        photo_path=ORDER_PHOTO,
        caption=PAYMENT_CREATED_TEXT,
        reply_markup=payment_kb(pay_url, order.id),
    )


async def start_payment_flow_from_message(
    message: Message,
    state: FSMContext,
    service: SubscriptionService,
    plan_code: str,
    receipt_email: str | None,
):
    try:
        order = await service.create_order(
            tg_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
            plan_code=plan_code,
            receipt_email=receipt_email,
        )
        pay_url = await service.create_payment_for_order(order.id)
    except Exception:
        await state.clear()
        await message.answer(
            "⚠️ Не удалось создать оплату прямо сейчас.\n"
            "Попробуйте ещё раз чуть позже.\n\n"
            "Если деньги уже списались или ошибка повторяется — напишите в поддержку.",
            reply_markup=back_to_main_kb(),
        )
        return

    await state.clear()
    await send_photo_screen(
        target=message,
        photo_path=ORDER_PHOTO,
        caption=PAYMENT_CREATED_TEXT,
        reply_markup=payment_kb(pay_url, order.id),
    )