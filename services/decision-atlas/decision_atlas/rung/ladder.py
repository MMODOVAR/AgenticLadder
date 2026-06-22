"""The AgenticLadder autonomy ladder.

Six rungs describe how much of a decision an agent may own, from fully manual
(rung 0) to fully autonomous (rung 5). Decision Atlas recommends a *target*
rung for every discovered decision; the rest of the AgenticLadder platform helps
you climb toward it safely.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Rung:
    level: int
    name: str
    summary: str
    human_role: str


LADDER: tuple[Rung, ...] = (
    Rung(0, "Manual",
         "A human performs the decision end to end. No automation.",
         "Human decides and acts."),
    Rung(1, "Assisted",
         "The system surfaces data, context, and insight; the human decides.",
         "Human decides; agent informs."),
    Rung(2, "Recommended",
         "The agent proposes a specific action; a human approves before it runs.",
         "Human approves each action."),
    Rung(3, "Supervised",
         "The agent executes automatically; humans review after the fact and can "
         "roll back. Exceptions escalate.",
         "Human reviews after the fact."),
    Rung(4, "Conditional Autonomy",
         "The agent acts within explicit guardrails; only low-confidence or "
         "edge cases escalate to a human.",
         "Human handles only escalations."),
    Rung(5, "Full Autonomy",
         "The agent owns the decision, including edge cases. Humans monitor "
         "aggregate outcomes and KPIs only.",
         "Human monitors KPIs only."),
)

MAX_RUNG = LADDER[-1].level


def rung_name(level: int) -> str:
    level = max(0, min(MAX_RUNG, int(level)))
    return LADDER[level].name


def get_rung(level: int) -> Rung:
    level = max(0, min(MAX_RUNG, int(level)))
    return LADDER[level]
