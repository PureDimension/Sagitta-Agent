"""Validation for Sagitta planning responses and hierarchical workflow IR."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterator


class ValidationError(ValueError):
    """Raised when Codex returns a response outside Sagitta's IR contract."""


PHASE_KINDS = {"explore", "design", "implement", "test", "review"}
WORKFLOW_FIELDS = {
    "title",
    "goal",
    "project_summary",
    "assumptions",
    "entry_phase",
    "phases",
}
PHASE_FIELDS = {
    "type",
    "id",
    "title",
    "kind",
    "objective",
    "outputs",
    "expected_facts",
    "timeout_seconds",
    "on",
}
SCOPE_FIELDS = {"type", "id", "entry_phase", "phases"}
ROUTE_FIELDS = {"target"}
CONDITIONAL_ROUTE_FIELDS = {"when", "target"}
CONDITION_TOKEN = re.compile(
    r"\s*("
    r"\$[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)?"
    r"|\d+"
    r"|<=|>=|==|!=|<|>"
    r"|\(|\)"
    r"|and\b|or\b"
    r")"
)
VARIABLE = re.compile(r"\$([A-Za-z_][A-Za-z0-9_]*)(?:\.([A-Za-z_][A-Za-z0-9_]*))?$")


@dataclass(frozen=True)
class Node:
    """One validated workflow node and its hierarchical location."""

    node: dict[str, Any]
    parent: str

    @property
    def id(self) -> str:
        return self.node["id"]

    @property
    def type(self) -> str:
        return self.node["type"]


def _nonempty_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{name} must be a non-empty string")
    return value


def _nonempty_string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValidationError(f"{name} must be a non-empty array of non-empty strings")
    if any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValidationError(f"{name} must be a non-empty array of non-empty strings")
    return value


def validate_planning_response(response: Any) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise ValidationError("planning response must be an object")

    status = response.get("status")
    _nonempty_string(response.get("summary"), "summary")
    if set(response) != {"status", "summary", "questions"}:
        raise ValidationError("planning response must contain status, summary, and questions")

    if status == "needs_input":
        questions = response.get("questions")
        if not isinstance(questions, list) or not questions:
            raise ValidationError("needs_input requires at least one question")
        ids: set[str] = set()
        for index, question in enumerate(questions):
            if not isinstance(question, dict) or set(question) != {"id", "question", "reason"}:
                raise ValidationError(f"questions[{index}] must contain id, question, and reason")
            question_id = _nonempty_string(question.get("id"), f"questions[{index}].id")
            if question_id in ids:
                raise ValidationError(f"duplicate question id: {question_id}")
            ids.add(question_id)
            _nonempty_string(question.get("question"), f"questions[{index}].question")
            _nonempty_string(question.get("reason"), f"questions[{index}].reason")
        return response

    if status == "ready":
        if response.get("questions") != []:
            raise ValidationError("ready requires questions to be an empty array")
        return response

    raise ValidationError("planning response status must be needs_input or ready")


def validate_workflow(workflow: Any) -> dict[str, Any]:
    if not isinstance(workflow, dict):
        raise ValidationError("workflow must be an object")
    if set(workflow) != WORKFLOW_FIELDS:
        missing = sorted(WORKFLOW_FIELDS - set(workflow))
        extra = sorted(set(workflow) - WORKFLOW_FIELDS)
        raise ValidationError(f"workflow fields do not match v2; missing={missing}, extra={extra}")

    for field in ("title", "goal", "project_summary", "entry_phase"):
        _nonempty_string(workflow.get(field), field)
    assumptions = workflow.get("assumptions")
    if not isinstance(assumptions, list) or any(not isinstance(item, str) or not item.strip() for item in assumptions):
        raise ValidationError("assumptions must be an array of non-empty strings")

    nodes = list(_collect_nodes(workflow.get("phases"), parent="$workflow", location="phases"))
    by_id = {node.id: node for node in nodes}
    _validate_entry(workflow["entry_phase"], "$workflow", by_id, "workflow.entry_phase")
    for node in nodes:
        if node.type == "scope":
            _validate_entry(node.node["entry_phase"], node.id, by_id, f"scope {node.id}.entry_phase")

    for node in nodes:
        if node.type == "phase":
            _validate_on(node, by_id)

    _validate_reachability(workflow["entry_phase"], by_id)
    return workflow


def _collect_nodes(value: Any, parent: str, location: str) -> Iterator[Node]:
    if not isinstance(value, list) or not value:
        raise ValidationError(f"{location} must be a non-empty array")
    seen_here: set[str] = set()
    for index, raw in enumerate(value):
        node_location = f"{location}[{index}]"
        if not isinstance(raw, dict):
            raise ValidationError(f"{node_location} must be an object")
        node_type = raw.get("type")
        if node_type == "phase":
            if set(raw) != PHASE_FIELDS:
                raise ValidationError(f"{node_location} phase fields must be exactly {sorted(PHASE_FIELDS)}")
            _nonempty_string(raw.get("id"), f"{node_location}.id")
            _nonempty_string(raw.get("title"), f"{node_location}.title")
            _nonempty_string(raw.get("objective"), f"{node_location}.objective")
            _nonempty_string_list(raw.get("outputs"), f"{node_location}.outputs")
            _nonempty_string_list(raw.get("expected_facts"), f"{node_location}.expected_facts")
            if raw.get("kind") not in PHASE_KINDS:
                raise ValidationError(f"{node_location}.kind must be one of {sorted(PHASE_KINDS)}")
            timeout = raw.get("timeout_seconds")
            if isinstance(timeout, bool) or not isinstance(timeout, int) or timeout <= 0:
                raise ValidationError(f"{node_location}.timeout_seconds must be a positive integer")
            if not isinstance(raw.get("on"), dict) or not raw["on"]:
                raise ValidationError(f"{node_location}.on must be a non-empty object")
        elif node_type == "scope":
            if set(raw) != SCOPE_FIELDS:
                raise ValidationError(f"{node_location} scope fields must be exactly {sorted(SCOPE_FIELDS)}")
            _nonempty_string(raw.get("id"), f"{node_location}.id")
            _nonempty_string(raw.get("entry_phase"), f"{node_location}.entry_phase")
        else:
            raise ValidationError(f"{node_location}.type must be phase or scope")

        node_id = raw["id"]
        if node_id in seen_here:
            raise ValidationError(f"duplicate node id among {parent} children: {node_id}")
        seen_here.add(node_id)
        yield Node(raw, parent)
        if node_type == "scope":
            yield from _collect_nodes(raw["phases"], parent=node_id, location=f"{node_location}.phases")

    all_ids = [node["id"] for node in _flatten_for_duplicates(value)]
    if len(all_ids) != len(set(all_ids)):
        duplicates = sorted({node_id for node_id in all_ids if all_ids.count(node_id) > 1})
        raise ValidationError(f"node ids must be globally unique: {duplicates}")


def _flatten_for_duplicates(value: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    for node in value:
        yield node
        if node.get("type") == "scope" and isinstance(node.get("phases"), list):
            yield from _flatten_for_duplicates(node["phases"])


def _validate_entry(entry: str, parent: str, by_id: dict[str, Node], name: str) -> None:
    node = by_id.get(entry)
    if node is None:
        raise ValidationError(f"{name} points to an unknown node: {entry}")
    if node.parent != parent:
        raise ValidationError(f"{name} must point to a direct child of {parent}")


def _validate_on(node: Node, by_id: dict[str, Node]) -> None:
    for outcome, route in node.node["on"].items():
        _nonempty_string(outcome, f"phase {node.id}.on outcome")
        if isinstance(route, str):
            _validate_target(route, by_id, f"phase {node.id}.on.{outcome}")
            continue
        if not isinstance(route, list) or not route:
            raise ValidationError(f"phase {node.id}.on.{outcome} must be a target string or non-empty route array")
        default_seen = False
        for index, item in enumerate(route):
            location = f"phase {node.id}.on.{outcome}[{index}]"
            if not isinstance(item, dict):
                raise ValidationError(f"{location} must be an object")
            keys = set(item)
            if keys == ROUTE_FIELDS:
                if index != len(route) - 1:
                    raise ValidationError(f"{location} is a default route and must be last")
                default_seen = True
            elif keys == CONDITIONAL_ROUTE_FIELDS:
                if default_seen:
                    raise ValidationError(f"{location} cannot follow a default route")
                _validate_condition(item["when"], node, by_id, location)
            else:
                raise ValidationError(f"{location} fields must be target or when plus target")
            _validate_target(item.get("target"), by_id, location)
        if not default_seen:
            raise ValidationError(f"phase {node.id}.on.{outcome} route array requires a final default target")


def _validate_target(target: Any, by_id: dict[str, Node], location: str) -> None:
    _nonempty_string(target, f"{location}.target")
    if target != "$complete" and target not in by_id:
        raise ValidationError(f"{location} points to an unknown target: {target}")


def _validate_condition(value: Any, phase: Node, by_id: dict[str, Node], location: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{location}.when must be a non-empty condition string")
    tokens = _tokenize_condition(value, location)
    parser = _ConditionParser(tokens, location)
    variables = parser.parse()
    for variable in variables:
        _validate_variable(variable, phase, by_id, location)


def _tokenize_condition(value: str, location: str) -> list[str]:
    tokens: list[str] = []
    position = 0
    value = value.strip()
    while position < len(value):
        match = CONDITION_TOKEN.match(value, position)
        if match is None:
            raise ValidationError(f"{location}.when has unsupported syntax near: {value[position:]!r}")
        tokens.append(match.group(1))
        position = match.end()
    return tokens


class _ConditionParser:
    """Parses a deliberately small comparison/boolean expression language."""

    def __init__(self, tokens: list[str], location: str) -> None:
        self.tokens = tokens
        self.location = location
        self.index = 0
        self.variables: list[str] = []

    def parse(self) -> list[str]:
        self._parse_or()
        if self.index != len(self.tokens):
            raise ValidationError(f"{self.location}.when has an unexpected token: {self.tokens[self.index]!r}")
        return self.variables

    def _parse_or(self) -> None:
        self._parse_and()
        while self._take("or"):
            self._parse_and()

    def _parse_and(self) -> None:
        self._parse_term()
        while self._take("and"):
            self._parse_term()

    def _parse_term(self) -> None:
        if self._take("("):
            self._parse_or()
            self._expect(")")
            return
        variable = self._next()
        if not variable.startswith("$"):
            raise ValidationError(f"{self.location}.when expects a counter reference")
        self.variables.append(variable)
        operator = self._next()
        if operator not in {"<", "<=", ">", ">=", "==", "!="}:
            raise ValidationError(f"{self.location}.when expects an integer comparison operator")
        number = self._next()
        if not number.isdigit():
            raise ValidationError(f"{self.location}.when expects a non-negative integer")

    def _take(self, token: str) -> bool:
        if self.index < len(self.tokens) and self.tokens[self.index] == token:
            self.index += 1
            return True
        return False

    def _expect(self, token: str) -> None:
        if not self._take(token):
            raise ValidationError(f"{self.location}.when expects {token!r}")

    def _next(self) -> str:
        if self.index >= len(self.tokens):
            raise ValidationError(f"{self.location}.when ends unexpectedly")
        token = self.tokens[self.index]
        self.index += 1
        return token


def _validate_variable(variable: str, phase: Node, by_id: dict[str, Node], location: str) -> None:
    match = VARIABLE.fullmatch(variable)
    if match is None:
        raise ValidationError(f"{location}.when has an invalid counter reference: {variable}")
    scope_or_phase, child_or_metric = match.groups()
    if child_or_metric is None:
        raise ValidationError(f"{location}.when counter references require a dotted name")
    if scope_or_phase == phase.id:
        if child_or_metric != "retry":
            raise ValidationError(f"{location}.when only supports ${phase.id}.retry for the current phase")
        return
    if scope_or_phase == "workflow":
        if child_or_metric not in by_id:
            raise ValidationError(f"{location}.when references an unknown workflow node: {child_or_metric}")
        return
    scope = by_id.get(scope_or_phase)
    if scope is None or scope.type != "scope":
        raise ValidationError(f"{location}.when references an unknown scope: {scope_or_phase}")
    if scope.id not in _ancestor_scopes(phase, by_id):
        raise ValidationError(f"{location}.when scope {scope.id} is not active for phase {phase.id}")
    child = by_id.get(child_or_metric)
    if child is None or child.parent != scope.id:
        raise ValidationError(f"{location}.when {scope.id}.{child_or_metric} must name a direct child node")


def _ancestor_scopes(node: Node, by_id: dict[str, Node]) -> set[str]:
    ancestors: set[str] = set()
    parent = node.parent
    while parent != "$workflow":
        ancestors.add(parent)
        parent = by_id[parent].parent
    return ancestors


def _validate_reachability(entry: str, by_id: dict[str, Node]) -> None:
    pending = [entry]
    reached: set[str] = set()
    complete_reached = False
    while pending:
        current = pending.pop()
        if current in reached:
            continue
        reached.add(current)
        node = by_id[current]
        if node.type == "scope":
            pending.append(node.node["entry_phase"])
            continue
        for route in node.node["on"].values():
            targets = [route] if isinstance(route, str) else [item["target"] for item in route]
            for target in targets:
                if target == "$complete":
                    complete_reached = True
                else:
                    pending.append(target)
    if set(by_id) != reached:
        missing = sorted(set(by_id) - reached)
        raise ValidationError(f"v2 workflow has nodes unreachable from entry_phase: {missing}")
    if not complete_reached:
        raise ValidationError("v2 workflow has no path to $complete")
