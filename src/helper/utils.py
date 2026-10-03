"""Generic helpers shared by UI pages and services."""
from collections.abc import Mapping
from typing import Any, Iterable, List, Optional, Sequence

import pandas as pd
from sqlmodel import SQLModel


def has_value(value: Any) -> bool:
    """False for None, empty / whitespace-only strings and empty collections."""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


# Backwards-compatible name used by the existing pages.
check_null = has_value


def get_or_default(dictionary: Mapping, key: str, default: Any = "") -> Any:
    """Value for `key`, or `default` when missing / blank. Works for dicts and st.session_state."""
    value = dictionary.get(key, default)
    return value if has_value(value) else default


def get_index_or_default(options: Sequence, search_for: Any, default: int = 0) -> int:
    """Position of `search_for` in `options` (for st.selectbox index), else `default`."""
    if not has_value(list(options)) or search_for is None:
        return default
    try:
        return list(options).index(search_for)
    except ValueError:
        return default


def model_dump_with_prefix_alias(dumped_model: dict, prefix_alias: str) -> dict:
    return {f"{prefix_alias}_{key}": value for key, value in dumped_model.items()}


def _row_to_record(row: Any) -> dict:
    if isinstance(row, SQLModel):
        return row.model_dump()
    # Multi-entity / column selects come back as Row tuples.
    record: dict = {}
    mapping = getattr(row, "_mapping", None)
    items = mapping.items() if mapping is not None else enumerate(row)
    for key, value in items:
        if isinstance(value, SQLModel):
            prefix = type(value).__tablename__
            record.update(model_dump_with_prefix_alias(value.model_dump(), str(prefix)))
        else:
            record[str(getattr(key, "key", key))] = value
    return record


def sqlmodel_to_df(objects: Iterable[Any], columns: Optional[List[str]] = None) -> pd.DataFrame:
    """Converts SQLModel objects (or rows of several models / columns) to a DataFrame."""
    records = [_row_to_record(row) for row in objects]
    if not records:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame.from_records(records, columns=columns)
