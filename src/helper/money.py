"""
Money helpers.

All amounts are stored as integer paise (Rs 1 = 100 paise) so that sums and
balance comparisons are exact. Convert only at the UI / report boundary.
"""
from decimal import ROUND_HALF_UP, Decimal
from typing import Union

from num2words import num2words

Number = Union[int, float, str, Decimal]


def rupees_to_paise(amount: Number) -> int:
    """Rs 2500.505 -> 250051 (rounded half-up to the nearest paisa)."""
    paise = (Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return int(paise)


def paise_to_rupees(paise: int) -> Decimal:
    """250050 -> Decimal('2500.50')."""
    return (Decimal(paise) / 100).quantize(Decimal("0.01"))


def _indian_grouping(whole: int) -> str:
    """1234567 -> '12,34,567' (lakh / crore grouping)."""
    digits = str(whole)
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join(groups) + "," + tail


def format_inr(paise: int, with_symbol: bool = True) -> str:
    """250050 -> '\u20b92,500.50' (Indian digit grouping)."""
    sign = "-" if paise < 0 else ""
    whole, fraction = divmod(abs(paise), 100)
    text = f"{sign}{_indian_grouping(whole)}.{fraction:02d}"
    return f"\u20b9{text}" if with_symbol else text


def amount_in_words_inr(paise: int) -> str:
    """250050 -> 'Two Thousand, Five Hundred Rupees and Fifty Paise Only'."""
    if paise < 0:
        raise ValueError("Amount in words is only defined for non-negative amounts")
    rupees, remainder = divmod(paise, 100)
    words = f"{num2words(rupees, lang='en_IN')} rupees"
    if remainder:
        words += f" and {num2words(remainder, lang='en_IN')} paise"
    return words.title().replace(" And ", " and ") + " Only"
