from aiogram.fsm.state import State, StatesGroup


class RegistrationStates(StatesGroup):
    """FSM states for technician registration."""
    waiting_full_name = State()
    waiting_shop_name = State()
    waiting_shop_location = State()
    waiting_contact = State()


class ListingStates(StatesGroup):
    """FSM states for creating a part listing."""
    waiting_category = State()
    waiting_brand = State()
    waiting_model = State()
    waiting_part_name = State()
    waiting_condition = State()
    waiting_price = State()
    waiting_photos = State()
    waiting_confirmation = State()


class SearchStates(StatesGroup):
    """FSM states for searching parts."""
    waiting_category = State()
    waiting_brand = State()
    waiting_model = State()


class PaymentStates(StatesGroup):
    """FSM states for payment flow."""
    waiting_payment_method = State()
    waiting_receipt = State()


class WebLoginStates(StatesGroup):
    """FSM states for web login linking."""
    waiting_code = State()