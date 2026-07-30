"""Public grounding and reference-resolution interface."""

from .resolver import (
    ResolutionResult,
    TargetResolutionResult,
    choose_unique_match,
    format_symbolic_ref_lines,
    resolve_generic_object,
    resolve_object_candidates,
    resolve_role_object,
    resolve_target_relation,
)

__all__ = [
    "ResolutionResult",
    "TargetResolutionResult",
    "choose_unique_match",
    "format_symbolic_ref_lines",
    "resolve_generic_object",
    "resolve_object_candidates",
    "resolve_role_object",
    "resolve_target_relation",
]
