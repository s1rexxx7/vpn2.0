from aiogram.fsm.state import State, StatesGroup


class PurchaseState(StatesGroup):
    waiting_receipt_email = State()