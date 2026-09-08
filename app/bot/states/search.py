from aiogram.fsm.state import State, StatesGroup


class SearchWizard(StatesGroup):
    query = State()
    confirm_query = State()
    custom_price = State()
    condition = State()
    region = State()
    inspection = State()
    seller_rating = State()
    seller_sales = State()
    deal = State()
    notification = State()
    notification_limit = State()
    frequency = State()
    confirm = State()
    edit_price = State()
