from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🚀 Подключить VPN", callback_data="menu:buy"),
        InlineKeyboardButton(text="👤 Личный кабинет", callback_data="menu:cabinet"),
    )
    return builder.as_markup()


def back_to_main_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main"))
    return builder.as_markup()


def buy_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🇩🇪 VPN Германия", callback_data="product:germany")
    )
    builder.row(
        InlineKeyboardButton(text="🚀 Обход глушилок", callback_data="product:bypass")
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main")
    )
    return builder.as_markup()


def germany_plans_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 149р на месяц", callback_data="plan:germany_1m"))
    builder.row(InlineKeyboardButton(text="💳 349р на 3 месяца", callback_data="plan:germany_3m"))
    builder.row(InlineKeyboardButton(text="💳 600р на 6 месяцев", callback_data="plan:germany_6m"))
    builder.row(InlineKeyboardButton(text="💳 1000р на год", callback_data="plan:germany_12m"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:buy"))
    return builder.as_markup()


def bypass_plans_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 299р на месяц", callback_data="plan:bypass_1m"))
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:buy"))
    return builder.as_markup()


def receipt_choice_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="Да", callback_data="receipt:yes"),
        InlineKeyboardButton(text="Нет", callback_data="receipt:no"),
    )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:buy"))
    return builder.as_markup()


def skip_email_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="➡️ Пропустить", callback_data="receipt:skip_email"))
    builder.row(InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main"))
    return builder.as_markup()


def payment_kb(pay_url: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="💳 Оплатить", url=pay_url))
    builder.row(InlineKeyboardButton(text="👤 Личный кабинет", callback_data="menu:cabinet"))
    builder.row(InlineKeyboardButton(text="⬅️ В меню", callback_data="menu:main"))
    return builder.as_markup()


def cabinet_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🔄 Обновить", callback_data="menu:cabinet")
    )
    builder.row(
        InlineKeyboardButton(text="🛒 Купить ещё", callback_data="menu:buy")
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu:main")
    )
    return builder.as_markup()

def success_payment_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu:main"))
    return builder.as_markup()