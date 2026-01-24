from typing import Any, Optional

import pandas as pd
from sqlmodel import SQLModel

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

def sqlmodel_to_df(objects: list[SQLModel]) -> pd.DataFrame:
    """Converts a list of SQLModel objects into a Pandas DataFrame."""
    if not objects:
        return pd.DataFrame()
        
    records = [obj.dict() for obj in objects]
    # Optional: ensure column order is retained based on the schema
    columns = list(objects[0].model_fields.keys()) 
    df = pd.DataFrame.from_records(records, columns=columns)
    return df