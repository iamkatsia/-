"""FSM-состояния бота."""
from aiogram.fsm.state import StatesGroup, State


class AdminStates(StatesGroup):
    adding_slots = State()       # ждём список слотов
    broadcasting = State()       # ждём текст рассылки
    writing_hw = State()         # ждём текст/файл ДЗ (student_id в data)
    adding_payment = State()     # ждём кол-во уроков для начисления (student_id в data)


class StudentStates(StatesGroup):
    submitting_hw = State()      # ждём ответ на ДЗ (hw_id в data)
