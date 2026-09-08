from uuid import UUID

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards.common import multi_keyboard, price_keyboard, query_confirmation, rows
from app.bot.states import SearchWizard
from app.collectors.goofish.normalizer import Normalizer
from app.core.constants import InspectionFilter, NotificationMode
from app.db.models import User
from app.db.repositories import SearchRepository
from app.services.search_service import SearchDraft, SearchService, parse_price

router = Router(name="search")
CONDITIONS = [
    ("new", "全新 — новое"),
    ("99new", "99新 — практически новое"),
    ("95new", "95新 — очень хорошее"),
    ("90new", "9成新 — хорошее"),
    ("defects", "Есть дефекты"),
]
LOCATIONS = [
    ("any", "🌎 Любой"),
    ("Shanghai", "🇨🇳 Shanghai"),
    ("Beijing", "🇨🇳 Beijing"),
    ("Guangzhou", "🇨🇳 Guangzhou"),
    ("Shenzhen", "🇨🇳 Shenzhen"),
    ("Hangzhou", "🇨🇳 Hangzhou"),
]


def draft_is_complete(data: dict[str, object]) -> bool:
    return bool(data.get("query") and data.get("max_price"))


async def restart_expired_wizard(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "⚠️ Сессия создания поиска устарела после перезапуска бота.\n\n"
        "Начните создание поиска заново.",
        reply_markup=rows(
            (("🔎 Создать поиск", "s:new"),),
            (("⬅️ К меню", "menu"),),
        ),
    )
    await callback.answer("Сессия устарела")


@router.callback_query(F.data == "s:new")
async def begin(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(SearchWizard.query)
    await callback.message.edit_text(
        "🔎 СОЗДАНИЕ ПОИСКА\n\nВведите название товара, который хотите отслеживать.\nНапример:\niPhone 16 Pro 128GB",
        reply_markup=rows((("❌ Отмена", "cancel"),)),
    )
    await callback.answer()


@router.message(SearchWizard.query)
async def query(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not text or len(text) > 255:
        await message.answer("Введите название длиной до 255 символов.")
        return
    parsed = Normalizer().normalize_query(text)
    await state.update_data(
        query=text, brand=parsed.brand, model=parsed.model, storage=parsed.storage_gb
    )
    await state.set_state(SearchWizard.confirm_query)
    known = [f"📱 {parsed.brand or ''} {parsed.model or text}".strip()]
    if parsed.storage_gb:
        known.append(f"💾 {parsed.storage_gb} GB")
    if not parsed.model:
        known.append("ℹ️ Модель не распознана уверенно — сохраню исходный запрос.")
    await message.answer(
        "🤖 Я правильно понял?\n\n" + "\n".join(known), reply_markup=query_confirmation()
    )


@router.callback_query(F.data == "s:q:edit")
async def edit_query(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SearchWizard.query)
    await callback.message.edit_text(
        "Введите новое название товара:", reply_markup=rows((("❌ Отмена", "cancel"),))
    )
    await callback.answer()


@router.callback_query(SearchWizard.confirm_query, F.data == "s:q:ok")
async def choose_price(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        "💰 МАКСИМАЛЬНАЯ ЦЕНА\n\nВыберите максимальную цену:", reply_markup=price_keyboard()
    )
    await callback.answer()


async def show_conditions(target: Message, state: FSMContext) -> None:
    data = await state.get_data()
    selected = set(data.get("conditions", []))
    await state.set_state(SearchWizard.condition)
    await target.edit_text(
        "📦 СОСТОЯНИЕ\n\nВыберите подходящие варианты:",
        reply_markup=multi_keyboard("s:c", CONDITIONS, selected, "s:c:done"),
    )


@router.callback_query(F.data.regexp(r"^s:p:\d+$"))
async def price_preset(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(max_price=callback.data.rsplit(":", 1)[1])
    await show_conditions(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "s:p:custom")
async def custom_price(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(SearchWizard.custom_price)
    await callback.message.edit_text("Введите максимальную цену в CNY числом:")
    await callback.answer()


@router.message(SearchWizard.custom_price)
async def custom_price_value(message: Message, state: FSMContext) -> None:
    try:
        price = parse_price(message.text or "")
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.update_data(max_price=str(price))
    await state.set_state(SearchWizard.condition)
    await message.answer(
        "📦 СОСТОЯНИЕ\n\nВыберите подходящие варианты:",
        reply_markup=multi_keyboard("s:c", CONDITIONS, set(), "s:c:done"),
    )


@router.callback_query(SearchWizard.condition, F.data.startswith("s:c:"))
async def condition(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.rsplit(":", 1)[1]
    if value == "done":
        data = await state.get_data()
        await state.set_state(SearchWizard.region)
        await callback.message.edit_text(
            "📍 РЕГИОН\n\nВыберите один или несколько:",
            reply_markup=multi_keyboard(
                "s:r", LOCATIONS, set(data.get("locations", [])), "s:r:done"
            ),
        )
    else:
        data = await state.get_data()
        selected = set(data.get("conditions", []))
        selected.symmetric_difference_update({value})
        await state.update_data(conditions=list(selected))
        await callback.message.edit_reply_markup(
            reply_markup=multi_keyboard("s:c", CONDITIONS, selected, "s:c:done")
        )
    await callback.answer()


@router.callback_query(SearchWizard.region, F.data.startswith("s:r:"))
async def region(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.rsplit(":", 1)[1]
    if value != "done":
        data = await state.get_data()
        selected = set(data.get("locations", []))
        selected = {"any"} if value == "any" else ({x for x in selected if x != "any"} ^ {value})
        await state.update_data(locations=list(selected))
        await callback.message.edit_reply_markup(
            reply_markup=multi_keyboard("s:r", LOCATIONS, selected, "s:r:done")
        )
        await callback.answer()
        return
    await state.set_state(SearchWizard.inspection)
    await callback.message.edit_text(
        "🛡 验货宝 (сервис проверки товара)\n\nВыберите требование к сервису проверки:",
        reply_markup=rows(
            (("☑ Неважно (показывать любые)", "s:in:a"),),
            (("☑ Только с 验货宝 (с проверкой)", "s:in:w"),),
            (("☑ Только через 验货宝 (проверка обязательна)", "s:in:m"),),
            (("☑ Без 验货宝 (без сервиса проверки)", "s:in:n"),),
            (("❌ Отмена", "cancel"),),
        ),
    )
    await callback.answer()


@router.callback_query(SearchWizard.inspection, F.data.startswith("s:in:"))
async def inspection_filter(callback: CallbackQuery, state: FSMContext) -> None:
    code = callback.data.rsplit(":", 1)[1]
    value = {
        "a": InspectionFilter.ANY,
        "w": InspectionFilter.WITH_INSPECTION,
        "m": InspectionFilter.MANDATORY_INSPECTION,
        "n": InspectionFilter.WITHOUT_INSPECTION,
    }.get(code)
    if value is None:
        await callback.answer("Некорректный фильтр", show_alert=True)
        return
    await state.update_data(inspection_filter=value.value)
    await state.set_state(SearchWizard.seller_rating)
    await callback.message.edit_text(
        "👤 ФИЛЬТР ПРОДАВЦА\n\nМинимальный рейтинг:",
        reply_markup=rows(
            (("Неважно", "s:sr:0"),),
            (("⭐ 90%+", "s:sr:90"), ("⭐ 95%+", "s:sr:95")),
            (("⭐ 98%+", "s:sr:98"),),
            (("❌ Отмена", "cancel"),),
        ),
    )
    await callback.answer()


@router.callback_query(SearchWizard.seller_rating, F.data.startswith("s:sr:"))
async def seller_rating(callback: CallbackQuery, state: FSMContext) -> None:
    value = int(callback.data.rsplit(":", 1)[1])
    await state.update_data(seller_rating=value or None)
    await state.set_state(SearchWizard.seller_sales)
    await callback.message.edit_text(
        "📦 МИНИМУМ ПРОДАЖ",
        reply_markup=rows(
            (("Неважно", "s:ss:0"),),
            (("10+", "s:ss:10"), ("50+", "s:ss:50")),
            (("100+", "s:ss:100"), ("500+", "s:ss:500")),
            (("❌ Отмена", "cancel"),),
        ),
    )
    await callback.answer()


@router.callback_query(SearchWizard.seller_sales, F.data.startswith("s:ss:"))
async def seller_sales(callback: CallbackQuery, state: FSMContext) -> None:
    value = int(callback.data.rsplit(":", 1)[1])
    await state.update_data(seller_sales=value or None)
    await state.set_state(SearchWizard.deal)
    await callback.message.edit_text(
        "🔥 НАСКОЛЬКО ВЫГОДНЫЕ ОБЪЯВЛЕНИЯ ПОКАЗЫВАТЬ?",
        reply_markup=rows(
            (("💰 Любые подходящие", "s:dl:0"),),
            (("📉 Ниже рынка на 10%+", "s:dl:10"),),
            (("🔥 Ниже рынка на 20%+", "s:dl:20"),),
            (("🚨 Ниже рынка на 30%+", "s:dl:30"),),
            (("🤖 Только AI-рекомендации", "s:dl:ai"),),
            (("❌ Отмена", "cancel"),),
        ),
    )
    await callback.answer()


@router.callback_query(SearchWizard.deal, F.data.startswith("s:dl:"))
async def deal_filter(callback: CallbackQuery, state: FSMContext) -> None:
    value = callback.data.rsplit(":", 1)[1]
    await state.update_data(
        deal_below=None if value in {"0", "ai"} else int(value),
        ai_only=value == "ai",
        min_deal_score=80 if value == "ai" else 0,
    )
    await state.set_state(SearchWizard.notification)
    await callback.message.edit_text(
        "🔔 КАКИЕ УВЕДОМЛЕНИЯ ПОЛУЧАТЬ?",
        reply_markup=rows(
            (("🔥 Только выгодные", "s:n:deals"),),
            (("🆕 Все подходящие", "s:n:all"),),
            (("🚨 Только суперцены", "s:n:super"),),
            (("❌ Отмена", "cancel"),),
        ),
    )
    await callback.answer()


@router.callback_query(SearchWizard.notification, F.data.startswith("s:n:"))
async def notification_mode(callback: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(notification_mode=callback.data.rsplit(":", 1)[1])
    await state.set_state(SearchWizard.notification_limit)
    await callback.message.edit_text(
        "🔔 ЛИМИТ УВЕДОМЛЕНИЙ",
        reply_markup=rows(
            (("5 в час", "s:nl:5"), ("10 в час", "s:nl:10")),
            (("20 в час", "s:nl:20"), ("Без ограничений", "s:nl:0")),
            (("❌ Отмена", "cancel"),),
        ),
    )
    await callback.answer()


@router.callback_query(SearchWizard.notification_limit, F.data.startswith("s:nl:"))
async def notification_limit(callback: CallbackQuery, state: FSMContext) -> None:
    value = int(callback.data.rsplit(":", 1)[1])
    await state.update_data(notification_limit=value or None)
    await state.set_state(SearchWizard.frequency)
    await callback.message.edit_text(
        "⚡ ЧАСТОТА МОНИТОРИНГА",
        reply_markup=rows(
            (("🚀 Быстро — 5 мин.", "s:fr:300"),),
            (("🟢 Стандарт — 15 мин.", "s:fr:900"),),
            (("🔵 Экономично — 60 мин.", "s:fr:3600"),),
            (("❌ Отмена", "cancel"),),
        ),
    )
    await callback.answer()


@router.callback_query(SearchWizard.frequency, F.data.startswith("s:fr:"))
async def frequency(callback: CallbackQuery, state: FSMContext) -> None:
    interval = int(callback.data.rsplit(":", 1)[1])
    await state.update_data(polling_interval=interval)
    data = await state.get_data()
    if not draft_is_complete(data):
        await restart_expired_wizard(callback, state)
        return
    await state.set_state(SearchWizard.confirm)
    locations = (
        "Любой регион"
        if not data.get("locations") or "any" in data.get("locations", [])
        else ", ".join(data["locations"])
    )
    deal = (
        "AI-рекомендации"
        if data.get("ai_only")
        else (f"−{data['deal_below']}% от рынка" if data.get("deal_below") else "Любые подходящие")
    )
    rating = f"{data['seller_rating']}%+" if data.get("seller_rating") else "неважно"
    inspection_label = {
        InspectionFilter.ANY.value: "Неважно (показывать любые)",
        InspectionFilter.WITH_INSPECTION.value: "Только с 验货宝 (с проверкой)",
        InspectionFilter.MANDATORY_INSPECTION.value: "Только через 验货宝 (проверка обязательна)",
        InspectionFilter.WITHOUT_INSPECTION.value: "Без 验货宝 (без сервиса проверки)",
    }[data.get("inspection_filter", InspectionFilter.ANY.value)]
    text = (
        f"🎯 ВАШ ПОИСК\n\n📱 {data['query']}\n💰 до ¥{data['max_price']}\n"
        f"📦 {', '.join(data.get('conditions', [])) or 'Любое'}\n📍 {locations}\n🔥 {deal}\n"
        f"🛡 验货宝 (проверка товара): {inspection_label}\n⭐ Продавец {rating}\n"
        f"🔔 {data['notification_mode']}\n⚡ {interval // 60} мин.\n\nВсё правильно?"
    )
    await callback.message.edit_text(
        text,
        reply_markup=rows(
            (("🚀 ЗАПУСТИТЬ", "s:run"),),
            (("✏️ ИЗМЕНИТЬ", "s:q:edit"),),
            (("❌ ОТМЕНИТЬ", "cancel"),),
        ),
    )
    await callback.answer()


@router.callback_query(SearchWizard.confirm, F.data == "s:run")
async def save(callback: CallbackQuery, state: FSMContext, db: AsyncSession, db_user: User) -> None:
    data = await state.get_data()
    if not draft_is_complete(data):
        await restart_expired_wizard(callback, state)
        return
    draft = SearchDraft(
        query=data["query"],
        max_price=parse_price(str(data["max_price"])),
        conditions=data.get("conditions", []),
        locations=data.get("locations", []),
        seller_min_rating=data.get("seller_rating"),
        seller_min_sales=data.get("seller_sales"),
        inspection_filter=InspectionFilter(
            data.get("inspection_filter", InspectionFilter.ANY.value)
        ),
        min_deal_score=data.get("min_deal_score", 0),
        deal_percent_below=data.get("deal_below"),
        ai_only=data.get("ai_only", False),
        notification_mode=NotificationMode(data.get("notification_mode", "deals")),
        notification_limit_hour=data.get("notification_limit"),
        polling_interval=data.get("polling_interval", 900),
    )
    task = await SearchService(db).create(db_user, draft)
    await state.clear()
    await callback.message.edit_text(
        f"✅ Поиск «{task.query}» запущен.\nПланировщик поставит первое обновление в очередь в течение минуты.",
        reply_markup=rows((("📋 Мои поиски", "s:list"),), (("⬅️ К меню", "menu"),)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("s:e:"))
async def edit_search(callback: CallbackQuery, db: AsyncSession, db_user: User) -> None:
    task_id = callback.data.rsplit(":", 1)[1]
    try:
        task = await SearchRepository(db).get_owned(UUID(task_id), db_user.id)
    except ValueError:
        task = None
    if not task:
        await callback.answer("Поиск не найден", show_alert=True)
        return
    await callback.message.edit_text(
        f"⚙️ НАСТРОЙКА ПОИСКА\n\n📱 {task.query}\n💰 до ¥{task.max_price:,.0f}\n"
        f"🛡 验货宝 (проверка товара): {inspection_filter_label(task.inspection_filter)}",
        reply_markup=rows(
            (("💰 Изменить цену", f"s:ep:{task.id}"),),
            (("🛡 验货宝 (проверка товара)", f"s:ei:{task.id}"),),
            (("⬅️ Назад", "s:list"),),
        ),
    )
    await callback.answer()


def inspection_filter_label(value: InspectionFilter) -> str:
    return {
        InspectionFilter.ANY: "Неважно (показывать любые)",
        InspectionFilter.WITH_INSPECTION: "Только с 验货宝 (с проверкой)",
        InspectionFilter.MANDATORY_INSPECTION: "Только через 验货宝 (проверка обязательна)",
        InspectionFilter.WITHOUT_INSPECTION: "Без 验货宝 (без сервиса проверки)",
    }[value]


@router.callback_query(F.data.startswith("s:ei:"))
async def edit_inspection_filter(callback: CallbackQuery, db: AsyncSession, db_user: User) -> None:
    task_id = callback.data.rsplit(":", 1)[1]
    try:
        task = await SearchRepository(db).get_owned(UUID(task_id), db_user.id)
    except ValueError:
        task = None
    if not task:
        await callback.answer("Поиск не найден", show_alert=True)
        return
    await callback.message.edit_text(
        "🛡 验货宝 (сервис проверки товара)\n\nВыберите новый фильтр:",
        reply_markup=rows(
            (("Неважно (показывать любые)", f"s:eix:a:{task.id}"),),
            (("Только с 验货宝 (с проверкой)", f"s:eix:w:{task.id}"),),
            (("Только через 验货宝 (обязательная проверка)", f"s:eix:m:{task.id}"),),
            (("Без 验货宝 (без сервиса проверки)", f"s:eix:n:{task.id}"),),
            (("⬅️ Назад", f"s:e:{task.id}"),),
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("s:eix:"))
async def save_inspection_filter(callback: CallbackQuery, db: AsyncSession, db_user: User) -> None:
    parts = callback.data.split(":")
    if len(parts) != 4:
        await callback.answer("Некорректное действие", show_alert=True)
        return
    value = {
        "a": InspectionFilter.ANY,
        "w": InspectionFilter.WITH_INSPECTION,
        "m": InspectionFilter.MANDATORY_INSPECTION,
        "n": InspectionFilter.WITHOUT_INSPECTION,
    }.get(parts[2])
    try:
        task = await SearchRepository(db).get_owned(UUID(parts[3]), db_user.id)
    except ValueError:
        task = None
    if not task or value is None:
        await callback.answer("Поиск не найден", show_alert=True)
        return
    task.inspection_filter = value
    await callback.message.edit_text(
        f"✅ 🛡 验货宝 (проверка товара): {inspection_filter_label(value)}",
        reply_markup=rows((("⬅️ К поиску", f"s:e:{task.id}"),)),
    )
    await callback.answer("Фильтр сохранён")


@router.callback_query(F.data.startswith("s:ep:"))
async def edit_price(
    callback: CallbackQuery, state: FSMContext, db: AsyncSession, db_user: User
) -> None:
    task_id = callback.data.rsplit(":", 1)[1]
    try:
        task = await SearchRepository(db).get_owned(UUID(task_id), db_user.id)
    except ValueError:
        task = None
    if not task:
        await callback.answer("Поиск не найден", show_alert=True)
        return
    await state.update_data(edit_task_id=task_id)
    await state.set_state(SearchWizard.edit_price)
    await callback.message.edit_text(
        "Введите новую максимальную цену в CNY:", reply_markup=rows((("❌ Отмена", "s:list"),))
    )
    await callback.answer()


@router.message(SearchWizard.edit_price)
async def save_edited_price(
    message: Message, state: FSMContext, db: AsyncSession, db_user: User
) -> None:
    try:
        price = parse_price(message.text or "")
    except ValueError as exc:
        await message.answer(str(exc))
        return
    data = await state.get_data()
    try:
        task = await SearchRepository(db).get_owned(UUID(data["edit_task_id"]), db_user.id)
    except (ValueError, KeyError):
        task = None
    if not task:
        await state.clear()
        await message.answer("Поиск не найден.")
        return
    task.max_price = price
    await state.clear()
    await message.answer(
        f"✅ Максимальная цена изменена на ¥{price:,.0f}.",
        reply_markup=rows((("📋 Мои поиски", "s:list"),)),
    )


@router.callback_query(F.data == "cancel")
async def cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text(
        "Создание поиска отменено.", reply_markup=rows((("⬅️ К меню", "menu"),))
    )
    await callback.answer()
