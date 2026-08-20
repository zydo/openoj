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
        assembly: dict[str, dict[str, str]] | None = None,
    ) -> PreparedProgram:
        """Write/compile source and return the command used for each testcase.

        ``assembly`` carries the judge-assembled library sources that make
        one complete program with the submission: ``{"common": {filename:
        content}, "provided": {filename: content}}`` from the problem
        set's common/ library and the problem's provided/ directory. It
        is None/empty for jobs that predate the assembly model (the
        built-in fallback types then apply).
        """
        ...

    def encode_case(self, invocation: dict[str, Any], case_input: Any) -> bytes:
        """Encode one language-neutral testcase for the executor harness."""
        ...
