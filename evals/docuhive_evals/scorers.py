"""Per-field metrics (CL-03 §3.3). Pure functions over (expected, predicted) pairs."""

from statistics import median

from docuhive.agents.validators import norm_name, similarity

FIELDS = ("category", "document_type", "correspondent", "document_date", "language")


def accuracy(pairs: list[tuple[object, object]]) -> float | None:
    return sum(e == p for e, p in pairs) / len(pairs) if pairs else None


def parent(cat: str | None) -> str | None:
    return cat.split("/")[0] if cat else None


def correspondent_match(expected: str | None, predicted: str | None, fuzzy: bool) -> bool:
    if not expected or not predicted:
        return expected == predicted
    if norm_name(expected) == norm_name(predicted):
        return True
    return fuzzy and similarity(expected, predicted) >= 0.75


def tag_prf(pairs: list[tuple[list[str], list[str]]]) -> dict[str, float]:
    tp = sum(len(set(e) & set(p)) for e, p in pairs)
    fp = sum(len(set(p) - set(e)) for e, p in pairs)
    fn = sum(len(set(e) - set(p)) for e, p in pairs)
    prec = tp / (tp + fp) if tp + fp else 1.0
    rec = tp / (tp + fn) if tp + fn else 1.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    return {"precision": round(prec, 3), "recall": round(rec, 3), "f1": round(f1, 3)}


def fact_equal(expected: dict | str, predicted: dict | None) -> bool:
    """Money: same amount and currency; others: same canonical string (strings normalised)."""
    if predicted is None:
        return False
    if isinstance(expected, dict):
        return str(expected.get("value")) == str(predicted.get("value")) and (
            expected.get("currency") or None
        ) == (predicted.get("currency") or None)
    return norm_name(str(expected)) == norm_name(str(predicted.get("value")))


def percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    return s[min(len(s) - 1, int(round(q * (len(s) - 1))))]


def calibration(items: list[tuple[bool, float, float]]) -> dict[str, float | None]:
    """items: (correct, confidence, threshold). The gate metric: accuracy of the fields that
    auto-apply would write (confidence >= threshold) and the share of such fields."""
    above = [c for c, conf, thr in items if conf >= thr]
    return {
        "precision_above_threshold": round(sum(above) / len(above), 3) if above else None,
        "share_above_threshold": round(len(above) / len(items), 3) if items else None,
    }


def latency(values: list[float]) -> dict[str, float | None]:
    return {"p50": median(values) if values else None, "p95": percentile(values, 0.95)}
