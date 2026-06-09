"""FSM-состояния бота."""
from aiogram.fsm.state import StatesGroup, State


class AdminStates(StatesGroup):
    adding_slots = State()             # ждём список разовых слотов
    broadcasting = State()             # ждём текст рассылки
    writing_hw = State()               # ждём текст/файл ДЗ (student_id в data)
    adding_payment = State()           # ждём кол-во уроков для начисления (student_id в data)
    template_pick_day = State()        # выбор дня недели для общего шаблона
    template_pick_time = State()       # ввод времени для общего шаблона
    student_sched_pick_day = State()   # выбор дня для личного расписания ученика
    student_sched_pick_time = State()  # ввод времени для личного расписания ученика


class StudentStates(StatesGroup):
    submitting_hw = State()         # ждём ответ на ДЗ (hw_id в data)
    rescheduling = State()          # выбор нового слота для переноса (old_slot_id в data)
