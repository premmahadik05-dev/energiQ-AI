"""Data quality score.

Score = 100 x completeness x (1 - invalid_fraction) x regularity, where

* completeness      = valid readings / expected readings over the time span
* invalid_fraction  = (duplicates + non-numeric + negative + unparseable
                       timestamps) / raw data rows
* regularity        = 1 - (steps that differ from the dominant step) / steps

Grades: >= 90 excellent, >= 75 good, >= 50 fair, otherwise poor. The score is a
transparent screening number, not a guarantee that a dataset will forecast well.
"""
from __future__ import annotations


def quality_score(
    *,
    raw_rows: int,
    valid_values: int,
    expected_slots: int,
    duplicates: int,
    non_numeric: int,
    negative: int,
    unparseable_timestamps: int,
    irregular_steps: int,
    steps: int,
) -> dict:
    completeness = min(1.0, valid_values / expected_slots) if expected_slots > 0 else 0.0
    invalid_fraction = (
        min(1.0, (duplicates + non_numeric + negative + unparseable_timestamps) / raw_rows)
        if raw_rows > 0
        else 1.0
    )
    regularity = max(0.0, 1.0 - irregular_steps / steps) if steps > 0 else 0.0
    score = round(100.0 * completeness * (1.0 - invalid_fraction) * regularity, 2)
    if score >= 90:
        grade = "excellent"
    elif score >= 75:
        grade = "good"
    elif score >= 50:
        grade = "fair"
    else:
        grade = "poor"
    return {
        "score": score,
        "grade": grade,
        "completeness": round(completeness, 6),
        "invalid_fraction": round(invalid_fraction, 6),
        "regularity": round(regularity, 6),
    }
