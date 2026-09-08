from uuid import UUID

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.common import main_menu, rows, search_card
from app.core.constants import SearchStatus
from app.db.models import (
    Alert,
    Favorite,
    HiddenItem,
    Item,
    PriceHistory,
    SearchTask,
    User,
    UserSettings,
)
from app.db.repositories import SearchRepository
from app.services.deal_score import inspection_explanation

router = Router(name="main")


async def menu_text(db: AsyncSession, user: User) -> str:
    active = await db.scalar(
        select(func.count())
        .select_from(SearchTask)
        .where(
            SearchTask.user_id == user.id,
            SearchTask.enabled.is_(True),
            SearchTask.deleted_at.is_(None),
        )
    )
    favorites = await db.scalar(
        select(func.count()).select_from(Favorite).where(Favorite.user_id == user.id)
    )
    return (
        "🔥 GOFISH FINDER\nОтслеживай выгодные объявления\nна Goofish и получай их прямо в Telegram.\n\n"
        f"🔎 Активных поисков: {active or 0}\n🔥 Новых находок: 0\n⭐ Избранных: {favorites or 0}\n\nВыберите действие:"
    )


@router.message(CommandStart())
async def start(message: Message, db: AsyncSession, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await message.answer(await menu_text(db, db_user), reply_markup=main_menu())


@router.callback_query(F.data == "menu")
async def menu(callback: CallbackQuery, db: AsyncSession, db_user: User, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(await menu_text(db, db_user), reply_markup=main_menu())
    await callback.answer()


@router.callback_query(F.data == "help")
async def help_screen(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "ℹ️ ПОМОЩЬ\n\nСоздайте поиск, выберите фильтры, и бот будет присылать новые подходящие объявления. "
        "Оценка выгоды и риска носит справочный характер.",
        reply_markup=rows((("⬅️ Назад", "menu"),)),
    )
    await callback.answer()


@router.callback_query(F.data == "s:list")
async def list_searches(callback: CallbackQuery, db: AsyncSession, db_user: User) -> None:
    tasks = await SearchRepository(db).list_owned(db_user.id)
    if not tasks:
        await callback.message.edit_text(
            "📋 МОИ ПОИСКИ\n\nПока нет сохранённых поисков.",
            reply_markup=rows((("🔎 Создать поиск", "s:new"),), (("⬅️ Назад", "menu"),)),
        )
    else:
        task = tasks[0]
        state = "⏸" if task.status == SearchStatus.PAUSED else "🟢"
        await callback.message.edit_text(
            f"📋 МОИ ПОИСКИ\n\n{state} {task.query}\nдо ¥{task.max_price:,.0f}",
            reply_markup=search_card(str(task.id), task.status == SearchStatus.PAUSED),
        )
    await callback.answer()


def _callback_uuid(data: str) -> UUID:
    try:
        return UUID(data.rsplit(":", 1)[1])
    except (ValueError, IndexError) as exc:
        raise ValueError("Некорректное действие") from exc


@router.callback_query(F.data.startswith("s:t:"))
async def toggle_search(callback: CallbackQuery, db: AsyncSession, db_user: User) -> None:
    task_id = _callback_uuid(callback.data)
    repo = SearchRepository(db)
    task = await repo.get_owned(task_id, db_user.id)
    if not task:
        await callback.answer("Поиск не найден", show_alert=True)
        return
    paused = task.status != SearchStatus.PAUSED
    await (repo.pause(task) if paused else repo.resume(task))
    await callback.answer("Поиск приостановлен" if paused else "Поиск возобновлён")
    await callback.message.edit_reply_markup(reply_markup=search_card(str(task.id), paused))


@router.callback_query(F.data.startswith("s:d:"))
async def delete_confirm(callback: CallbackQuery, db: AsyncSession, db_user: User) -> None:
    task = await SearchRepository(db).get_owned(_callback_uuid(callback.data), db_user.id)
    if not task:
        await callback.answer("Поиск не найден", show_alert=True)
        return
    await callback.message.edit_text(
        f"🗑 Удалить поиск «{task.query}»?",
        reply_markup=rows((("🗑 Да, удалить", f"s:dx:{task.id}"),), (("❌ Отмена", "s:list"),)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("s:dx:"))
async def delete_search(callback: CallbackQuery, db: AsyncSession, db_user: User) -> None:
    repo = SearchRepository(db)
    task = await repo.get_owned(_callback_uuid(callback.data), db_user.id)
    if not task:
        await callback.answer("Поиск не найден", show_alert=True)
        return
    await repo.soft_delete(task)
    await callback.message.edit_text(
        "✅ Поиск удалён. Исторические данные сохранены.",
        reply_markup=rows((("⬅️ К меню", "menu"),)),
    )
    await callback.answer()


@router.callback_query(F.data == "set:main")
async def settings(callback: CallbackQuery, db: AsyncSession, db_user: User) -> None:
    value = await db.get(UserSettings, db_user.id)
    quiet = "🟢" if value and value.quiet_hours_enabled else "🔴"
    await callback.message.edit_text(
        f"⚙️ НАСТРОЙКИ\n\n💱 Валюта: 🇨🇳 CNY\n🔔 Уведомления: 🟢\n🌙 Тихие часы: {quiet}\n🌅 Дайджест: 🔴\n🔥 Минимальный Score: 70\n🌐 Язык: 🇷🇺 Русский",
        reply_markup=rows((("🌙 Тихие часы", "set:quiet"),), (("⬅️ Назад", "menu"),)),
    )
    await callback.answer()


@router.callback_query(F.data == "set:quiet")
async def toggle_quiet(callback: CallbackQuery, db: AsyncSession, db_user: User) -> None:
    value = await db.get(UserSettings, db_user.id)
    if not value:
        value = UserSettings(user_id=db_user.id)
        db.add(value)
    value.quiet_hours_enabled = not value.quiet_hours_enabled
    await callback.answer(
        "Тихие часы включены" if value.quiet_hours_enabled else "Тихие часы выключены"
    )
    await callback.message.edit_text(
        f"🌙 ТИХИЕ ЧАСЫ\n\n{'🟢 Включены' if value.quiet_hours_enabled else '🔴 Выключены'}\n"
        f"{value.quiet_from:%H:%M} — {value.quiet_to:%H:%M}",
        reply_markup=rows((("🔁 Включить/выключить", "set:quiet"),), (("⬅️ Назад", "set:main"),)),
    )


@router.callback_query(F.data.in_({"i:new", "fav:list"}))
async def item_list(callback: CallbackQuery, db: AsyncSession, db_user: User) -> None:
    if callback.data == "i:new":
        item = await db.scalar(
            select(Item)
            .join(Alert)
            .where(Alert.user_id == db_user.id, Alert.status == "pending")
            .order_by(Alert.created_at.desc())
        )
        title = "🔥 НОВЫЕ НАХОДКИ"
    else:
        item = await db.scalar(
            select(Item)
            .join(Favorite)
            .where(Favorite.user_id == db_user.id)
            .order_by(Favorite.created_at.desc())
        )
        title = "⭐ ИЗБРАННОЕ"
    if not item:
        await callback.message.edit_text(
            f"{title}\n\nПока здесь пусто.", reply_markup=rows((("⬅️ Назад", "menu"),))
        )
    else:
        await callback.message.edit_text(
            f"{title}\n\n📱 {item.title}\n💰 ¥{item.price:,.0f}",
            reply_markup=rows((("📊 Подробнее", f"i:v:{item.id}"),), (("⬅️ Назад", "menu"),)),
        )
    await callback.answer()


async def _user_item(db: AsyncSession, user_id: UUID, item_id: UUID) -> Item | None:
    return await db.scalar(
        select(Item)
        .join(Alert, Alert.item_id == Item.id)
        .where(Item.id == item_id, Alert.user_id == user_id)
    )


@router.callback_query(F.data.startswith("i:v:"))
async def item_details(callback: CallbackQuery, db: AsyncSession, db_user: User) -> None:
    item = await _user_item(db, db_user.id, _callback_uuid(callback.data))
    if not item:
        await callback.answer("Объявление недоступно", show_alert=True)
        return
    text = (
        f"📊 АНАЛИЗ\n\nЦена: ¥{item.price:,.0f}\n🔥 Deal Score: {item.deal_score}/100\n"
        f"🛡 Risk Score: {item.risk_score}/100\n📦 Состояние: {item.condition or 'не указано'}\n"
        f"📍 {item.location or 'не указано'}"
    )
    if item.inspection_service_available:
        status = "ОБЯЗАТЕЛЬНО" if item.inspection_service_mandatory else "Есть"
        text += f"\n🛡 验货宝 (проверка товара): {status}"
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Открыть", url=item.url)],
            [
                InlineKeyboardButton(text="⭐ Сохранить", callback_data=f"i:s:{item.id}"),
                InlineKeyboardButton(text="📉 История цены", callback_data=f"i:ph:{item.id}"),
            ],
            [InlineKeyboardButton(text="🤔 Почему это выгодно?", callback_data=f"i:why:{item.id}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="i:new")],
        ]
    )
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("i:why:"))
async def why_deal(callback: CallbackQuery, db: AsyncSession, db_user: User) -> None:
    item = await _user_item(db, db_user.id, _callback_uuid(callback.data))
    if not item:
        await callback.answer("Объявление недоступно", show_alert=True)
        return
    explanation = inspection_explanation(
        {
            "inspection_service_available": item.inspection_service_available,
            "inspection_service_mandatory": item.inspection_service_mandatory,
        }
    )
    text = f"🤔 ПОЧЕМУ ЭТО ВЫГОДНО?\n\n🔥 Deal Score: {item.deal_score}/100"
    if explanation:
        text += f"\n\n{explanation}"
    await callback.message.edit_text(text, reply_markup=rows((("⬅️ Назад", f"i:v:{item.id}"),)))
    await callback.answer()


@router.callback_query(F.data.startswith("i:s:"))
async def favorite_item(callback: CallbackQuery, db: AsyncSession, db_user: User) -> None:
    item_id = _callback_uuid(callback.data)
    if not await _user_item(db, db_user.id, item_id):
        await callback.answer("Объявление недоступно", show_alert=True)
        return
    if not await db.get(Favorite, (db_user.id, item_id)):
        db.add(Favorite(user_id=db_user.id, item_id=item_id))
    await callback.answer("Сохранено в избранное")


@router.callback_query(F.data.startswith("i:h:"))
async def hide_item(callback: CallbackQuery, db: AsyncSession, db_user: User) -> None:
    item_id = _callback_uuid(callback.data)
    if not await _user_item(db, db_user.id, item_id):
        await callback.answer("Объявление недоступно", show_alert=True)
        return
    if not await db.get(HiddenItem, (db_user.id, item_id)):
        db.add(HiddenItem(user_id=db_user.id, item_id=item_id))
    await callback.message.edit_text(
        "🚫 Объявление скрыто.", reply_markup=rows((("⬅️ К находкам", "i:new"),))
    )
    await callback.answer()


@router.callback_query(F.data.startswith("i:ph:"))
async def price_history(callback: CallbackQuery, db: AsyncSession, db_user: User) -> None:
    item_id = _callback_uuid(callback.data)
    if not await _user_item(db, db_user.id, item_id):
        await callback.answer("Объявление недоступно", show_alert=True)
        return
    history = list(
        await db.scalars(
            select(PriceHistory)
            .where(PriceHistory.item_id == item_id)
            .order_by(PriceHistory.recorded_at.desc())
            .limit(20)
        )
    )
    lines = [f"¥{row.price:,.0f} — {row.recorded_at:%d.%m %H:%M}" for row in history]
    await callback.message.edit_text(
        "📉 ИСТОРИЯ ЦЕНЫ\n\n" + ("\n".join(lines) or "Нет данных"),
        reply_markup=rows((("⬅️ Назад", f"i:v:{item_id}"),)),
    )
    await callback.answer()
