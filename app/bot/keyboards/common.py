from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def rows(*rows: tuple[tuple[str, str], ...]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data=data) for text, data in row]
            for row in rows
        ]
    )


def main_menu() -> InlineKeyboardMarkup:
    return rows(
        (("🔎 Создать поиск", "s:new"),),
        (("🔥 Новые находки", "i:new"), ("📋 Мои поиски", "s:list")),
        (("⭐ Избранное", "fav:list"), ("⚙️ Настройки", "set:main")),
        (("ℹ️ Помощь", "help"),),
    )


def query_confirmation() -> InlineKeyboardMarkup:
    return rows(
        (("✅ Да, продолжить", "s:q:ok"),),
        (("✏️ Изменить название", "s:q:edit"),),
        (("❌ Отмена", "cancel"),),
    )


def price_keyboard() -> InlineKeyboardMarkup:
    values = (2000, 3000, 4000, 4500, 5000, 6000, 7500, 10000)
    pairs = [
        tuple((f"¥{v:,}".replace(",", " "), f"s:p:{v}") for v in values[i : i + 2])
        for i in range(0, 8, 2)
    ]
    return rows(*pairs, (("✏️ Своя цена", "s:p:custom"),), (("⬅️ Назад", "s:q:edit"),))


def multi_keyboard(
    prefix: str, options: list[tuple[str, str]], selected: set[str], done: str
) -> InlineKeyboardMarkup:
    option_rows = tuple(
        ((("☑" if key in selected else "☐") + " " + label, f"{prefix}:{key}"),)
        for key, label in options
    )
    return rows(*option_rows, (("✅ Готово", done),), (("❌ Отмена", "cancel"),))


def search_card(task_id: str, paused: bool) -> InlineKeyboardMarkup:
    return rows(
        (("⚙️ Настроить", f"s:e:{task_id}"), ("🔥 Найденные", f"s:f:{task_id}")),
        (
            (("▶️ Возобновить" if paused else "⏸ Пауза"), f"s:t:{task_id}"),
            ("🗑 Удалить", f"s:d:{task_id}"),
        ),
        (("⬅️ Назад", "menu"),),
    )
