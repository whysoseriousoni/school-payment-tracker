from typing import Any, Optional

def check_null(value: Any):
    if isinstance(value, list):
        if len(value)==0 or value is None:
            return False
    if isinstance(value, str):
        if value=="" or value is None:
            return False
    return True

def get_or_default(dictionary, key, default=""):
    value_retrieved = dictionary.get(key, default=default)
    if not check_null(value_retrieved):
        return default
    return value_retrieved

def get_index_or_default(options: list, search_for, default=0):
    if check_null(options):
        return default
    try:
        return options.index(value=search_for)
    except IndexError:
        return default