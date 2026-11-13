"""Built-in rules from rules.json plus user-created rules persisted as JSON."""

import json
import re
from pathlib import Path
from uuid import uuid4

from pydantic import BaseModel, Field, TypeAdapter

from .correlation import load_rules
from .models import Kind, Rule, Severity


class RuleDraft(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    severity: Severity
    sequence: list[Kind] = Field(min_length=2, max_length=8)
    window_seconds: int = Field(gt=0, le=3600)
    restricted_only: bool = False
    after_hours_only: bool = False


class RuleBook:
    """Mutable rule list shared by the correlation engine, the live session, and the API."""

    def __init__(self, builtin: Path | None, custom_path: Path):
        self.builtin = load_rules(builtin)
        self.custom_path = custom_path
        self.custom: list[Rule] = []
        self.rules: list[Rule] = list(self.builtin)

    def load(self) -> None:
        if self.custom_path.is_file():
            self.custom = TypeAdapter(list[Rule]).validate_json(self.custom_path.read_bytes())
        self._refresh()

    def _refresh(self) -> None:
        self.rules[:] = [*self.builtin, *self.custom]

    def _persist(self) -> None:
        self.custom_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [rule.model_dump(mode="json") for rule in self.custom]
        self.custom_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def add(self, draft: RuleDraft) -> Rule:
        slug = re.sub(r"[^a-z0-9]+", "-", draft.title.lower()).strip("-") or "rule"
        rule = Rule(
            id=f"{slug}-{uuid4().hex[:6]}",
            description=draft.description or self.describe(draft),
            custom=True,
            **draft.model_dump(exclude={"description"}),
        )
        self.custom.append(rule)
        self._persist()
        self._refresh()
        return rule

    def remove(self, rule_id: str) -> bool:
        remaining = [rule for rule in self.custom if rule.id != rule_id]
        if len(remaining) == len(self.custom):
            return False
        self.custom = remaining
        self._persist()
        self._refresh()
        return True

    @staticmethod
    def describe(draft: RuleDraft) -> str:
        names = [kind.value.replace("_", " ") for kind in draft.sequence]
        where = "the same restricted zone" if draft.restricted_only else "the same zone"
        when = " after staffed hours" if draft.after_hours_only else ""
        return f"{', then '.join(names)} within {draft.window_seconds} seconds in {where}{when}."
