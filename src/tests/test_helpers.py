from datetime import date

import pytest

from helper.money import amount_in_words_inr, format_inr, paise_to_rupees, rupees_to_paise
from helper.school_calendar import (
    academic_year_bounds,
    academic_year_label,
    academic_year_start_for,
    fee_months,
    next_class,
)
from helper.utils import get_index_or_default, get_or_default, has_value, sqlmodel_to_df
from statics import CLASSES, ONE_OFF_FEE_TYPES, RECURRING_FEE_TYPES, FeeType


@pytest.mark.parametrize(
    "on_date, expected",
    [(date(2026, 6, 1), 2026), (date(2026, 5, 31), 2025), (date(2027, 3, 15), 2026), (date(2026, 12, 31), 2026)],
)
def test_academic_year_start_for(on_date, expected):
    assert academic_year_start_for(on_date) == expected


def test_academic_year_label_and_bounds():
    assert academic_year_label(2026) == "2026-27"
    assert academic_year_label(2099) == "2099-00"
    assert academic_year_bounds(2026) == (date(2026, 6, 1), date(2027, 5, 31))
    assert academic_year_bounds(2027)[1] == date(2028, 5, 31)


def test_fee_months_run_june_to_may():
    months = fee_months(2026)
    assert len(months) == 12
    assert months[0] == date(2026, 6, 1)
    assert months[6] == date(2026, 12, 1) and months[7] == date(2027, 1, 1)
    assert months[-1] == date(2027, 5, 1)


def test_class_progression():
    assert CLASSES[:2] == ["LKG", "UKG"]
    assert next_class("LKG") == "UKG"
    assert next_class("UKG") == "1"
    assert next_class("10") is None
    with pytest.raises(ValueError):
        next_class("11")


def test_fee_type_groups():
    assert set(RECURRING_FEE_TYPES) == {FeeType.TUITION, FeeType.VAN}
    assert FeeType.BOOK in ONE_OFF_FEE_TYPES and FeeType.TUITION not in ONE_OFF_FEE_TYPES
    assert FeeType.TUITION.label == "Tuition Fee"
    assert FeeType.TUITION == "TUITION"


def test_money_conversion_is_exact():
    assert rupees_to_paise("2500") == 250000
    assert rupees_to_paise(0.1 + 0.2) == 30
    assert rupees_to_paise("10.005") == 1001
    assert str(paise_to_rupees(250050)) == "2500.50"


def test_format_inr_uses_indian_grouping():
    assert format_inr(0) == "\u20b90.00"
    assert format_inr(250000) == "\u20b92,500.00"
    assert format_inr(12345678900) == "\u20b912,34,56,789.00"
    assert format_inr(-150, with_symbol=False) == "-1.50"


def test_amount_in_words():
    assert amount_in_words_inr(3000000) == "Thirty Thousand Rupees Only"
    assert amount_in_words_inr(12500000) == "One Lakh, Twenty-Five Thousand Rupees Only"
    assert amount_in_words_inr(250050) == "Two Thousand, Five Hundred Rupees and Fifty Paise Only"
    with pytest.raises(ValueError):
        amount_in_words_inr(-1)


def test_has_value_and_get_or_default():
    assert not has_value(None) and not has_value("  ") and not has_value([])
    assert has_value(0) and has_value(False) and has_value("x")
    data = {"a": "", "b": "value", "c": 0}
    assert get_or_default(data, "a", "fallback") == "fallback"
    assert get_or_default(data, "b") == "value"
    assert get_or_default(data, "c", 5) == 0
    assert get_or_default(data, "missing", None) is None


def test_get_index_or_default():
    options = ["CASH", "UPI", "CARD"]
    assert get_index_or_default(options, "UPI") == 1
    assert get_index_or_default(options, "CHEQUE", default=0) == 0
    assert get_index_or_default(options, None) == 0
    assert get_index_or_default([], "UPI", default=2) == 2


def test_sqlmodel_to_df_empty_keeps_columns():
    frame = sqlmodel_to_df([], columns=["id", "name"])
    assert list(frame.columns) == ["id", "name"] and frame.empty
