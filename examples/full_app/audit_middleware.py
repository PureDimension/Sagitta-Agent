"""Audit and permission capabilities for the full_app demo.

Demonstrates pydantic-ai Capabilities API integration:
- AuditCapability: tracks tool usage stats (call count, duration, breakdown)
- PermissionCapability: blocks access to sensitive paths via ModelRetry
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import ModelRetry
from pydantic_ai.capabilities import AbstractCapability

from pydantic_deep.deps import DeepAgentDeps

logger = logging.getLogger(__name__)


@dataclass
class ToolUsageStats:
    """Accumulated tool usage statistics for a session."""

    call_count: int = 0
    total_duration_ms: float = 0
    last_tool: str = ""
    tools_used: dict[str, int] = field(default_factory=lambda: defaultdict(int))


@dataclass
class AuditCapability(AbstractCapability[DeepAgentDeps]):
    """Capability that tracks tool usage for frontend display.

    Accumulates stats globally (since the agent is shared/stateless).
    The WebSocket handler reads these stats after each tool call.
    """

    stats: ToolUsageStats = field(default_factory=ToolUsageStats)
    _tool_start_times: dict[str, float] = field(default_factory=dict, repr=False)

    def get_stats(self) -> ToolUsageStats:
        """Get current accumulated stats."""
        return self.stats

    def reset_stats(self) -> None:
        """Reset stats (e.g., on session reset)."""
        self.stats = ToolUsageStats()
        self._tool_start_times.clear()

    async def before_tool_execute(
        self,
        ctx: Any,
        *,
        call: Any,
        tool_def: Any,
        args: Any,
    ) -> None:
        """Record tool call start time."""
        self._tool_start_times[tool_def.name] = time.monotonic()

    async def after_tool_execute(
        self,
        ctx: Any,
        *,
        call: Any,
        tool_def: Any,
        args: Any,
        result: Any,
    ) -> Any:
        """Record tool completion and accumulate stats."""
        tool_name = tool_def.name
        self.stats.call_count += 1
        self.stats.last_tool = tool_name
        self.stats.tools_used[tool_name] += 1

        start = self._tool_start_times.pop(tool_name, None)
        if start is not None:
            duration = (time.monotonic() - start) * 1000
            self.stats.total_duration_ms += duration

        return result


# Patterns for sensitive paths that should be blocked
BLOCKED_PATH_PATTERNS = [
    r"/etc/passwd",
    r"/etc/shadow",
    r"\.env$",
    r"\.env\.",
    r"/root/",
    r"\.ssh/",  # matches ~/.ssh/, /home/user/.ssh/, etc.
    r"/proc/",
    r"/sys/",
    r"id_rsa",  # SSH private keys anywhere
    r"id_ed25519",  # SSH private keys (ed25519)
]

# File-related tools whose path arguments should be checked
FILE_TOOLS = {"read_file", "write_file", "edit_file", "glob", "grep"}


@dataclass
class PermissionCapability(AbstractCapability[DeepAgentDeps]):
    """Capability that blocks access to sensitive paths.

    Checks file paths in tool arguments against blocked patterns.
    Raises ModelRetry for blocked paths so the agent retries with a different approach.
    """

    async def before_tool_execute(
        self,
        ctx: Any,
        *,
        call: Any,
        tool_def: Any,
        args: Any,
    ) -> None:
        """Check file paths against blocked patterns."""
        tool_name = tool_def.name
        logger.debug(f"PermissionCapability.before_tool_execute: {tool_name}({args})")

        if tool_name not in FILE_TOOLS:
            return

        # Extract path from args (different tools use different arg names)
        tool_args = args if isinstance(args, dict) else {}
        path = tool_args.get("path", "") or tool_args.get("pattern", "")
        logger.debug(f"PermissionCapability: checking path '{path}' for tool '{tool_name}'")

        for pattern in BLOCKED_PATH_PATTERNS:
            if re.search(pattern, str(path)):
                logger.warning(
                    f"PermissionCapability BLOCKED: {tool_name}(path={path}) "
                    f"matches pattern '{pattern}'"
                )
                raise ModelRetry(
                    f"Access denied: path matches blocked pattern '{pattern}'. "
                    f"Try a different path."
                )


# Backward-compat aliases for app.py import
AuditMiddleware = AuditCapability
PermissionMiddleware = PermissionCapability
