"""Adaptive, dataset-aware suggested questions for uploaded CSVs."""

from backend.services.adaptive_questions.engine import (
    generate_followup_questions,
    generate_suggested_questions,
)

__all__ = ["generate_suggested_questions", "generate_followup_questions"]
