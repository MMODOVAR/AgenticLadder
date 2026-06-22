"""Shared helpers for connectors (stdlib only)."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Iterable


def load_records(path: str) -> list[dict[str, Any]]:
    """Load a list of records from a JSON array file or a JSONL file."""
    with open(path, "r", encoding="utf-8") as fh:
        text = fh.read().strip()
    if not text:
        return []
    if text[0] == "[":
        data = json.loads(text)
        return list(data)
    # JSON Lines
    records: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def parse_ts(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.utcfromtimestamp(float(value))
        except (OverflowError, OSError, ValueError):
            return None
    if isinstance(value, str):
        v = value.strip().replace("Z", "+00:00")
        for parser in (datetime.fromisoformat,):
            try:
                return parser(v)
            except ValueError:
                pass
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%m/%d/%Y"):
            try:
                return datetime.strptime(value.strip(), fmt)
            except ValueError:
                continue
    return None


def dig(record: dict[str, Any], dotted: str | None, default: Any = None) -> Any:
    """Fetch a possibly-nested value using ``a.b.c`` dotted paths."""
    if not dotted:
        return default
    cur: Any = record
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return default
    return cur


def as_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "yes", "y", "1"):
            return True
        if v in ("false", "no", "n", "0"):
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return None


def first_str(*values: Any) -> str | None:
    for v in values:
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def listify(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(x) for x in value]
    return [str(value)]
