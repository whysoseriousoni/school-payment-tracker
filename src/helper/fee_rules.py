"""
Overdue rule for flexible (instalment) payment.

The admin sets milestones per term, e.g. 50% by 31 Oct and 100% by 31 Mar.
On a given date, the expected share of each annual fee is the highest milestone
percentage already reached. At the end of the term the whole fee is expected
(balances never carry over). One-off fees are expected as soon as they are added.
"""
from datetime import date
from typing import Iterable, Tuple

Milestone = Tuple[date, int]  # (due date, cumulative percent)


def expected_percent(milestones: Iterable[Milestone], as_of: date, term_end: date) -> int:
    if as_of >= term_end:
        return 100
    reached = [percent for due_date, percent in milestones if due_date <= as_of]
    return max(reached, default=0)


def expected_amount(amount_due_paise: int, percent: int) -> int:
    """Rounded up to the next paisa so a partial rupee is never treated as paid."""
    return -(-amount_due_paise * percent // 100)


def overdue_amount(amount_due_paise: int, amount_paid_paise: int, percent: int) -> int:
    return max(0, expected_amount(amount_due_paise, percent) - amount_paid_paise)


def next_milestone(milestones: Iterable[Milestone], as_of: date):
    """The first milestone after `as_of`, or None."""
    upcoming = sorted((m for m in milestones if m[0] > as_of), key=lambda m: m[0])
    return upcoming[0] if upcoming else None
