from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class ExecutorError(RuntimeError):
    """A language plugin could not prepare a submitted program."""


@dataclass(frozen=True)
class PreparedProgram:
    """Immutable command and environment produced by a language plugin."""

    command: tuple[str, ...]
    environment: dict[str, str]


class LanguageExecutor(Protocol):
    """Boundary implemented by each installed compiler/interpreter plugin.

    A plugin can compile once in ``prepare`` and return the per-testcase
    command. The worker owns sandboxing, resource limits, testcase isolation,
    and the JSON result protocol.
    """

    language: str
    address_space_overhead_mb: int
    max_processes: int

    def calibrate(self) -> tuple[float, float]:
        """Return a benchmark duration and clamped deadline scale."""
        ...

    def prepare(
        self,
        job_root: Path,
        scratch: Path,
        code: str,
        invocation: dict[str, Any],
        limits: dict[str, Any],
    ) -> PreparedProgram:
        """Write/compile source and return the command used for each testcase."""
        ...

    def encode_case(self, invocation: dict[str, Any], case_input: Any) -> bytes:
        """Encode one language-neutral testcase for the executor harness."""
        ...
