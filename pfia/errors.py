"""Exception hierarchy for the PFIA register toolchain."""


class PFIAError(Exception):
    """Base class for all register toolchain errors."""


class RegisterLoadError(PFIAError):
    """Raised when a register file is structurally invalid or a reference dangles."""


class PredicateError(PFIAError):
    """Raised when a predicate expression cannot be evaluated."""


class ExtractionError(PFIAError):
    """Raised when an extractor returns a payload that does not match its control."""
