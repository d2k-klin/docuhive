"""JSON for statement snapshots: amounts as strings, dates as ISO dates."""

import json
from datetime import date
from decimal import Decimal


def dumps(value: object) -> str:
    def default(v: object) -> object:
        if isinstance(v, Decimal):
            return str(v)
        if isinstance(v, date):
            return v.isoformat()
        raise TypeError(type(v).__name__)

    return json.dumps(value, default=default)
