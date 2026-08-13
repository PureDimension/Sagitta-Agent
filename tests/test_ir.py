from __future__ import annotations

import json
from importlib import resources
import unittest

from sagitta.ir import ValidationError, validate_planning_response


def ready_response() -> dict:
    return {
        "status": "ready",
        "summary": "A linear plan.",
        "questions": [],
        "workflow": {
            "title": "Example",
            "goal": "Do the work.",
            "project_summary": "A Python project.",
            "assumptions": ["Use existing tests."],
            "entry_phase": "explore",
            "phases": [
                {
                    "type": "phase",
                    "id": "explore",
                    "title": "Explore",
                    "kind": "explore",
                    "objective": "Read the project.",
                    "outputs": ["A project inventory."],
                    "expected_facts": ["The relevant project constraints are identified."],
                    "timeout_seconds": 60,
                    "on": {"done": "implement"},
                },
                {
                    "type": "phase",
                    "id": "implement",
                    "title": "Implement",
                    "kind": "implement",
                    "objective": "Make the change.",
                    "outputs": ["The requested source change."],
                    "expected_facts": ["The requested behavior is implemented."],
                    "timeout_seconds": 120,
                    "on": {"done": "$complete"},
                },
            ],
        },
    }


class PlanIRTests(unittest.TestCase):
    def test_rejects_a_phase_without_completion_contract(self) -> None:
        response = ready_response()
        del response["workflow"]["phases"][0]["expected_facts"]
        with self.assertRaisesRegex(ValidationError, "phase fields"):
            validate_planning_response(response)

    def test_local_validator_rejects_an_empty_outcome_map(self) -> None:
        response = ready_response()
        response["workflow"]["phases"][0]["on"] = {}
        with self.assertRaisesRegex(ValidationError, "on must be a non-empty object"):
            validate_planning_response(response)

    def test_transport_schema_leaves_node_semantics_to_the_local_validator(self) -> None:
        schema = json.loads(
            resources.files("sagitta.schemas").joinpath("planning_response.json").read_text(encoding="utf-8")
        )
        self.assertEqual(
            schema,
            {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "additionalProperties": False,
                "required": ["planning_response_json"],
                "properties": {"planning_response_json": {"type": "string"}},
            },
        )

    def test_accepts_a_complete_single_chain(self) -> None:
        self.assertEqual(validate_planning_response(ready_response())["status"], "ready")

    def test_accepts_a_cycle(self) -> None:
        response = ready_response()
        response["workflow"]["phases"][1]["on"] = {"done": "explore", "needs_fix": "$complete"}
        self.assertEqual(validate_planning_response(response)["status"], "ready")

    def test_rejects_an_unreachable_phase(self) -> None:
        response = ready_response()
        response["workflow"]["phases"].append(
            {
                "type": "phase",
                "id": "review",
                "title": "Review",
                "kind": "review",
                "objective": "Review the change.",
                "outputs": ["A review record."],
                "expected_facts": ["The review result is recorded."],
                "timeout_seconds": 60,
                "on": {"done": "$complete"},
            }
        )
        with self.assertRaisesRegex(ValidationError, "unreachable"):
            validate_planning_response(response)

    def test_accepts_focused_planning_questions(self) -> None:
        response = {
            "status": "needs_input",
            "summary": "A material product choice is unresolved.",
            "workflow": None,
            "questions": [
                {
                    "id": "auth-mode",
                    "question": "Use sessions or tokens?",
                    "reason": "The answer changes the implementation boundary.",
                }
            ],
        }
        self.assertEqual(validate_planning_response(response)["status"], "needs_input")

    def test_accepts_hierarchical_conditional_navigation(self) -> None:
        response = ready_response()
        response["workflow"]["entry_phase"] = "major"
        response["workflow"]["phases"] = [
            {
                "type": "scope",
                "id": "major",
                "entry_phase": "minor",
                "phases": [
                    {
                        "type": "scope",
                        "id": "minor",
                        "entry_phase": "try_minor",
                        "phases": [
                            {
                                "type": "phase",
                                "id": "try_minor",
                                "title": "Try minor direction",
                                "kind": "implement",
                                "objective": "Validate a minor direction.",
                                "outputs": ["A minor-direction result."],
                                "expected_facts": ["The direction has evidence for validity or invalidity."],
                                "timeout_seconds": 60,
                                "on": {
                                    "done": "$complete",
                                    "invalid": [
                                        {
                                            "when": "($major.minor < 3 and $workflow.minor < 8) or $try_minor.retry == 0",
                                            "target": "minor",
                                        },
                                        {"target": "$complete"},
                                    ],
                                },
                            }
                        ],
                    }
                ],
            }
        ]
        self.assertEqual(validate_planning_response(response)["status"], "ready")

    def test_rejects_unsafe_or_unknown_condition_syntax(self) -> None:
        response = ready_response()
        response["workflow"]["phases"][0]["on"] = {
            "done": [
                {"when": "$explore.retry + 1 < 3", "target": "implement"},
                {"target": "$complete"},
            ]
        }
        with self.assertRaisesRegex(ValidationError, "unsupported syntax"):
            validate_planning_response(response)
