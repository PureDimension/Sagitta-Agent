from __future__ import annotations

import json
from importlib import resources
import unittest

from sagitta.ir import ValidationError, validate_planning_response, validate_workflow


def workflow() -> dict:
    return {
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
    }


class PlanIRTests(unittest.TestCase):
    def test_rejects_a_phase_without_completion_contract(self) -> None:
        response = workflow()
        del response["phases"][0]["expected_facts"]
        with self.assertRaisesRegex(ValidationError, "phase fields"):
            validate_workflow(response)

    def test_local_validator_rejects_an_empty_outcome_map(self) -> None:
        response = workflow()
        response["phases"][0]["on"] = {}
        with self.assertRaisesRegex(ValidationError, "on must be a non-empty object"):
            validate_workflow(response)

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
        self.assertEqual(validate_workflow(workflow())["title"], "Example")

    def test_accepts_a_ready_status_without_a_duplicate_workflow(self) -> None:
        response = {"status": "ready", "summary": "The plan package is ready.", "questions": []}
        self.assertEqual(validate_planning_response(response)["status"], "ready")

    def test_accepts_a_cycle(self) -> None:
        response = workflow()
        response["phases"][1]["on"] = {"done": "explore", "needs_fix": "$complete"}
        self.assertEqual(validate_workflow(response)["title"], "Example")

    def test_rejects_an_unreachable_phase(self) -> None:
        response = workflow()
        response["phases"].append(
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
            validate_workflow(response)

    def test_accepts_focused_planning_questions(self) -> None:
        response = {
            "status": "needs_input",
            "summary": "A material product choice is unresolved.",
            "questions": [
                {
                    "id": "auth-mode",
                    "question": "Use sessions or tokens?",
                    "reason": "The answer changes the implementation boundary.",
                }
            ],
        }
        self.assertEqual(validate_planning_response(response)["status"], "needs_input")

    def test_accepts_phase_navigation_with_anchor_counter_windows(self) -> None:
        response = workflow()
        response["entry_phase"] = "explore_major"
        response["phases"] = [
            {
                "type": "phase",
                "id": "explore_major",
                "title": "Explore a major direction",
                "kind": "explore",
                "objective": "Choose a major direction.",
                "outputs": ["A selected major direction."],
                "expected_facts": ["The active major direction is recorded."],
                "timeout_seconds": 60,
                "on": {"direction_selected": "try_minor"},
            },
            {
                "type": "phase",
                "id": "try_minor",
                "title": "Try a minor direction",
                "kind": "implement",
                "objective": "Validate a minor direction.",
                "outputs": ["A minor-direction result."],
                "expected_facts": ["The direction has evidence for validity or invalidity."],
                "timeout_seconds": 60,
                "on": {
                    "done": "$complete",
                    "invalid": [
                        {
                            "when": "($try_minor.entercount.after.explore_major < 3 and $try_minor.retrycount.after.explore_major < 2 and $try_minor.entercount < 8)",
                            "target": "try_minor",
                        },
                        {"target": "$complete"},
                    ],
                },
            }
        ]
        self.assertEqual(validate_workflow(response)["title"], "Example")

    def test_rejects_scope_nodes_and_old_counter_notation(self) -> None:
        response = workflow()
        response["phases"][0] = {"type": "scope", "id": "legacy", "entry_phase": "implement", "phases": []}
        with self.assertRaisesRegex(ValidationError, "must be phase"):
            validate_workflow(response)

        response = workflow()
        response["phases"][0]["on"] = {
            "done": [
                {"when": "$workflow.implement < 2", "target": "implement"},
                {"target": "$complete"},
            ]
        }
        with self.assertRaisesRegex(ValidationError, "unknown phase: workflow"):
            validate_workflow(response)

    def test_rejects_a_windowed_retry_counter_for_another_phase(self) -> None:
        response = workflow()
        response["phases"][0]["on"] = {
            "done": [
                {"when": "$implement.retrycount.after.explore < 2", "target": "implement"},
                {"target": "$complete"},
            ]
        }
        with self.assertRaisesRegex(ValidationError, "only reference the current phase explore"):
            validate_workflow(response)

    def test_rejects_unsafe_or_unknown_condition_syntax(self) -> None:
        response = workflow()
        response["phases"][0]["on"] = {
            "done": [
                {"when": "$explore.retrycount + 1 < 3", "target": "implement"},
                {"target": "$complete"},
            ]
        }
        with self.assertRaisesRegex(ValidationError, "unsupported syntax"):
            validate_workflow(response)
