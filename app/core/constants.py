from enum import StrEnum


class SearchStatus(StrEnum):
    ACTIVE = "active"
    ACTIVE_WITH_ERRORS = "active_with_errors"
    PAUSED = "paused"
    ERROR = "error"
    DISABLED = "disabled"


class NotificationMode(StrEnum):
    DEALS = "deals"
    ALL = "all"
    SUPER = "super"


class InspectionFilter(StrEnum):
    ANY = "any"
    WITH_INSPECTION = "with_inspection"
    MANDATORY_INSPECTION = "mandatory_inspection"
    WITHOUT_INSPECTION = "without_inspection"


class Condition(StrEnum):
    NEW = "new"
    LIKE_NEW = "99new"
    VERY_GOOD = "95new"
    GOOD = "90new"
    DEFECTS = "defects"


CONDITION_LABELS = {
    Condition.NEW: "全新 — новое",
    Condition.LIKE_NEW: "99新 — практически новое",
    Condition.VERY_GOOD: "95新 — очень хорошее",
    Condition.GOOD: "9成新 — хорошее",
    Condition.DEFECTS: "Есть дефекты",
}
