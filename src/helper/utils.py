from typing import Any, Optional

def check_null(value: Any):
    if isinstance(value, str):
        if value=="" or value is None:
            return False
    return True

def get_or_default(dictionary, key, default=""):
    value_retrieved = dictionary.get(key, default=default)
    if not check_null(value_retrieved):
        return default
    return value_retrieved