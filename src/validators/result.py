"""Shared validation contract for config/manifest validators.

Mirrors checker-npm's ``{ valid, errors, warnings, info }`` shape so every
validator reports findings the same way. ``ValidationError`` subclasses the
project's ``ImportCheckerError`` so a finding that escapes as an exception is
still caught by ``main()``'s top-level handler, while carrying a
machine-readable ``code`` and an optional 1-based ``line`` number.

Findings are normally *returned* in ``ValidationResult.errors`` /
``ValidationResult.warnings`` -- raising is reserved for failures that abort a
single file's validation (e.g. an unreadable file).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

# Import the project's base exception. Flat layout (tests put ``src/`` on
# sys.path) exposes it as ``checker``; the installed wheel as ``src.checker``.
try:  # pragma: no cover - import shim
    from checker import ImportCheckerError
except ImportError:  # pragma: no cover - import shim
    from ..checker import ImportCheckerError


class ValidationError(ImportCheckerError):
    """A single validation finding.

    Subclass of :class:`ImportCheckerError` so escaped instances are still
    caught by ``main()``; carries a machine-readable ``code`` and an optional
    1-based ``line``.
    """

    def __init__(self, message: str, code: str, line: Optional[int] = None) -> None:
        super().__init__(message)
        self.code = code
        self.line = line

    def __repr__(self) -> str:
        loc = f" line {self.line}" if self.line is not None else ""
        return f"ValidationError[{self.code}]{loc}: {self.args[0]}"


@dataclass
class ValidationWarning:
    """A non-fatal finding. Carries the same code/line metadata as an error."""

    code: str
    message: str
    line: Optional[int] = None


@dataclass
class ValidationResult:
    """Uniform result of validating one config artifact."""

    valid: bool = True
    errors: List[ValidationError] = field(default_factory=list)
    warnings: List[ValidationWarning] = field(default_factory=list)
    info: Dict[str, Any] = field(default_factory=dict)

    def add_error(self, message: str, code: str, line: Optional[int] = None) -> None:
        """Record an error finding and mark the result invalid."""
        self.errors.append(ValidationError(message, code, line))
        self.valid = False

    def add_warning(self, message: str, code: str, line: Optional[int] = None) -> None:
        """Record a warning finding (does not affect ``valid``)."""
        self.warnings.append(ValidationWarning(code, message, line))
