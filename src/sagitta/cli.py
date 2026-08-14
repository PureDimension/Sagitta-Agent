"""Command-line entry points for planning and Goal export."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .codex import CodexError, CodexPlanner
from .config import ConfigStore, PlanningRunStore, StorageError
from .goal import GoalCompilationError, GoalService
from .planning import PlanningError, PlanningService, record_for_display


def _home_from_args(args: argparse.Namespace) -> Path | None:
    return Path(args.home).expanduser() if args.home else None


def _service(args: argparse.Namespace) -> PlanningService:
    home = _home_from_args(args)
    return PlanningService(ConfigStore(home), PlanningRunStore(home), CodexPlanner())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Sagitta Plan Package/IR and manual Goal export MVP")
    parser.add_argument("--home", help="override the local Sagitta state directory")
    subcommands = parser.add_subparsers(dest="command", required=True)

    init = subcommands.add_parser("init", help="configure the planning workspace")
    init.add_argument("--workspace", required=True, help="existing directory Codex may inspect")

    plan = subcommands.add_parser(
        "plan",
        help="ask Codex to inspect, write, and pre-launch-review a Plan Package and IR",
    )
    plan.add_argument("intent", help="natural-language development request")

    answer = subcommands.add_parser("answer", help="answer one Codex planning question and resume planning")
    answer.add_argument("run_id")
    answer.add_argument("question_id")
    answer.add_argument("answer")

    show = subcommands.add_parser("show", help="show a persisted planning run")
    show.add_argument("run_id")

    goal = subcommands.add_parser("goal", help="export a reviewed Plan IR as a paste-ready Codex Goal")
    goal.add_argument("run_id")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    home = _home_from_args(args)
    try:
        if args.command == "init":
            config = ConfigStore(home).save_workspace(Path(args.workspace))
            print(record_for_display(config))
            return 0
        if args.command == "plan":
            print(record_for_display(_service(args).plan(args.intent)))
            return 0
        if args.command == "answer":
            print(record_for_display(_service(args).answer(args.run_id, args.question_id, args.answer)))
            return 0
        if args.command == "show":
            print(record_for_display(PlanningRunStore(home).load(args.run_id)))
            return 0
        if args.command == "goal":
            path, goal = GoalService(PlanningRunStore(home)).export(args.run_id)
            print(f"Saved paste-ready Codex Goal to: {path}\n")
            print(goal)
            return 0
    except (StorageError, PlanningError, CodexError, GoalCompilationError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    raise AssertionError(f"unhandled command: {args.command}")
