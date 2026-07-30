"""
Ground symbolic object and target references in the current world state.

This module filters world objects by attributes and relations, detects
unique, ambiguous, missing, and invalid references, and optionally uses
the Stage 3 model checker to validate unresolved object references.
"""

from dataclasses import dataclass, field
import re
from typing import Any, Dict, List, Optional, Tuple

from ..world import World
from ..stage3 import ModelChecker




# ----------------------------------------
# Reference grounding
# ----------------------------------------

@dataclass
class ResolutionResult:
    """Stores the result of resolving one object reference."""

    object_id: Optional[str] = None
    candidate_ids: List[str] = field(default_factory=list)

    # Possible values: NO_MATCH, UNIQUE_MATCH, AMBIGUOUS, INVALID_ID
    resolution: str = "NO_MATCH"

    model_correction: bool = False
    message: str = ""



@dataclass
class TargetResolutionResult:
    """Stores the result of resolving a placement target."""

    location: Optional[str] = None
    next_to_id: Optional[str] = None
    candidate_ids: List[str] = field(default_factory=list)
    # Possible values: NO_MATCH, UNIQUE_MATCH, AMBIGUOUS, INVALID_ID
    resolution: str = "NO_MATCH"

    messages: List[str] = field(default_factory=list)



def apply_filter_constraints(
    world: World,
    candidate_ids: List[str],
    filters: Dict[str, Any]
) -> List[str]:
    """Return candidate IDs whose objects satisfy all filter constraints."""

    clean_filters = strip_ref_metadata(filters)
    matches = []

    for object_id in candidate_ids:
        obj = world.get_object_by_id(object_id)
        if obj is None:
            continue

        is_match = True

        for attribute_name, requested_value in clean_filters.items():
            if requested_value is None:
                continue

            # Apply lower-bound constraints to consumable tools
            if attribute_name == "min_fullness":
                if not hasattr(obj, "fullness_percent"):
                    is_match = False
                    break
                if obj.fullness_percent < requested_value:
                    is_match = False
                    break
                continue

            # Apply upper-bound constraints to repair-tool damage
            if attribute_name == "max_damage":
                if not hasattr(obj, "damage_status"):
                    is_match = False
                    break
                if obj.damage_status > requested_value:
                    is_match = False
                    break
                continue

            # All remaining filters require an exact attribute match
            if not hasattr(obj, attribute_name):
                is_match = False
                break
            actual_value = getattr(obj, attribute_name)
            if actual_value != requested_value:
                is_match = False
                break

        if is_match:
            matches.append(object_id)

    return matches



def strip_ref_metadata(symbolic_ref: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Remove parser-only fields from a symbolic reference.

    This keeps only constraints that can be used for object matching.
    """

    if not symbolic_ref:
        return {}
    return {
        key: value
        for key, value in symbolic_ref.items()
        if key != "warnings" and key != "generic_class"
    }



def find_existing_object_ids_in_text(
    world: World,
    text: str,
    report_invalid_schema_id: bool = False,
) -> Tuple[List[str], Optional[str]]:
    """Find existing world object IDs mentioned in text.

    Optionally report an ID-like expression that follows the expected
    naming scheme but does not exist in the world.
    """

    normalized_text = text.lower()
    all_object_ids = world.get_all_object_ids()
    found = []
    for object_id in all_object_ids:
        pattern = rf"\b{re.escape(object_id.lower())}\b"
        match = re.search(pattern, normalized_text)
        if match:
            found.append((match.start(), object_id))

    # Preserve the order in which object IDs appear in the text
    found.sort(key=lambda pair: pair[0])
    existing_ids = [object_id for _, object_id in found]

    invalid_message = None

    # Check for a well-formed but unknown ID only when no existing ID was found
    if report_invalid_schema_id and not existing_ids:
        id_like_pattern = r"\b[a-zA-Z]+(?:_[a-zA-Z]+)*_\d+\b"
        id_like_match = re.search(id_like_pattern, normalized_text)
        if id_like_match:
            invalid_id = id_like_match.group(0)
            invalid_message = f"Object ID '{invalid_id}' does not exist."

    return existing_ids, invalid_message



def format_filters(filters: Optional[Dict[str, Any]], indent: int = 0) -> List[str]:
    """Format object filters as readable bullet lines."""

    if not filters:
        return []
    prefix = " " * indent
    lines = []

    for attribute_name, value in filters.items():
        if value is None or attribute_name == "warnings":
            continue
        readable_attribute = attribute_name.replace("_", " ")
        lines.append(f"{prefix}- {readable_attribute}: {value}")

    return lines



def format_symbolic_ref_lines(
    symbolic_ref: Optional[Dict[str, Any]],
    indent: int = 0,
) -> List[str]:
    """Format a symbolic object reference as indented bullet lines."""

    if not symbolic_ref:
        return []

    prefix = " " * indent
    lines = []
    object_class = symbolic_ref.get("object_class")
    object_phrase = symbolic_ref.get("object_phrase")
    filters = symbolic_ref.get("filters", {})
    relation_refs = symbolic_ref.get("relation_refs", [])

    if object_class is not None:
        lines.append(f"{prefix}- object class: {object_class}")
    lines.extend(format_filters(filters, indent))

    if relation_refs:
        lines.append(f"{prefix}- relations:")
        for relation_ref in relation_refs:
            lines.extend(
                format_relation_ref(relation_ref, indent + 2)
            )

    return lines



def format_relation_ref(
    relation_ref: Dict[str, Any],
    indent: int = 0,
) -> List[str]:
    """Format one relation reference as indented bullet lines."""

    prefix = " " * indent
    relation_type = relation_ref["relation_type"]

    if relation_type in {"on", "inside"}:
        target_location = relation_ref["target_location"]
        readable_relation = relation_type.replace("_", " ")
        return [
            f"{prefix}- relation: {readable_relation} {target_location}"
        ]

    if relation_type == "next_to":
        lines = [f"{prefix}- relation: next to"]
        target_ref = relation_ref["target_ref"]
        if target_ref is not None:
            lines.append(f"{prefix}  - target:")
            lines.extend(format_symbolic_ref_lines(target_ref, indent + 4))
        else:
            target_phrase = relation_ref.get("target_phrase", "")
            lines.append(f"{prefix}  - target phrase: {target_phrase}")
        return lines

    # Preserve unsupported relation types in the diagnostic output
    return [f"{prefix}- relation: {relation_type}"]



def choose_unique_match(
    world: World,
    matches: List[str],
    symbolic_ref: Optional[Dict[str, Any]],
    description: str = "object",
) -> ResolutionResult:
    """Return a no-match, ambiguous, or unique resolution result.

    The result includes the candidate IDs and a human-readable diagnostic message.
    """

    if not matches:
        lines = format_symbolic_ref_lines(symbolic_ref)
        if lines:
            ref_text = "\n".join(lines)
            message = (
                f"I could not find the requested {description}.\n"
                f"I looked for this {description}:\n"
                f"{ref_text}"
            )
        else:
            message = f"I could not find the {description}."
        return ResolutionResult(
            object_id=None,
            candidate_ids=[],
            resolution="NO_MATCH",
            message=message
        )

    if len(matches) > 1:
        candidate_text = "\n".join(
            world.describe_object_by_id(object_id)
            for object_id in matches
        )
        return ResolutionResult(
            object_id=None,
            candidate_ids=list(matches),
            resolution="AMBIGUOUS",
            message=(
                f"Which {description} did you mean exactly?\n"
                f"Are you looking for one of these?:\n"
                f"{candidate_text}"
            )
        )

    return ResolutionResult(
        object_id=matches[0],
        candidate_ids=list(matches),
        resolution="UNIQUE_MATCH",
        message=f"Resolved '{description}' to {matches[0]}."
    )



def resolve_object_candidates(
    world: World,
    object_ref: Dict[str, Any],
    candidate_ids: Optional[List[str]] = None
) -> List[str]:
    """Recursively resolve an object reference to all matching candidate object IDs.

    This works even if object_class is None, as long as relation_refs can
    narrow down the candidates.
    """

    object_class = object_ref["object_class"]
    filters = object_ref["filters"]
    relation_refs = object_ref["relation_refs"]

    if candidate_ids is None:
        candidate_ids = world.get_all_object_ids(object_class)

    # Apply class/filter constraints
    candidates = apply_filter_constraints(world, candidate_ids, filters)

    # Stop early when no candidate satisfies the current constraints
    if not candidates:
        return []

    # Apply each relation constraint
    for relation_ref in relation_refs:
        relation_type = relation_ref["relation_type"]
        match relation_type:
            case "on" | "inside":
                target_location = relation_ref["target_location"]
                candidates = [
                    object_id
                    for object_id in candidates
                    if world.check_location_relation(
                        relation_type,
                        object_id,
                        target_location
                    )
                ]
            case "next_to":
                target_ref = relation_ref["target_ref"]
                if target_ref is None:
                    target_phrase = relation_ref["target_phrase"]
                    target_ids, _ = find_existing_object_ids_in_text(world, target_phrase)

                    # Ignore an unresolved raw target phrase because it cannot narrow the candidates
                    if not target_ids:
                        continue
                else:
                    target_ids = resolve_object_candidates(
                        world=world,
                        object_ref=target_ref,
                        candidate_ids=None
                    )

                    # A parsed next-to target with no matches makes the whole relation unsatisfiable
                    if not target_ids:
                        return []

                candidates = [
                    object_id
                    for object_id in candidates
                    if any(
                        world.check_next_to_relation(object_id, target_id)
                        for target_id in target_ids
                    )
                ]

        # Stop early when no candidate satisfies the accumulated relations
        if not candidates:
            return []

    return candidates



def resolve_target_relation(
    world: World,
    utterance: str,
    target_relation_ref: Dict[str, Any],
) -> TargetResolutionResult:
    """Resolve a placement relation to a location or next-to target object."""

    relation_type = target_relation_ref["relation_type"]

    match relation_type:
        case "on" | "inside":
            location = target_relation_ref["target_location"]
            if location is None:
                return TargetResolutionResult(
                    resolution="NO_MATCH",
                    messages=[
                        "I understood the target relation, "
                        "but not the target location."
                    ]
                )
            return TargetResolutionResult(
                location=location,
                resolution="UNIQUE_MATCH"
            )

        case "next_to":
            target_ref = target_relation_ref["target_ref"]

            # Fall back to a direct object ID when no structured target was parsed
            if target_ref is None:
                mentioned_ids, invalid_id_message = find_existing_object_ids_in_text(
                    world,
                    target_relation_ref["target_phrase"],
                    report_invalid_schema_id=True
                )
                if mentioned_ids:
                    next_to_id = mentioned_ids[0]
                    return TargetResolutionResult(
                        next_to_id=next_to_id,
                        candidate_ids=mentioned_ids,
                        resolution="UNIQUE_MATCH",
                        messages=[
                            f"Resolved next-to target object as direct ID: {next_to_id}."
                        ]
                    )
                if invalid_id_message is not None:
                    return TargetResolutionResult(
                        resolution="INVALID_ID",
                        messages=[
                            "I couldn't find the requested next-to target object. "
                            + invalid_id_message
                        ]
                    )
                return TargetResolutionResult(
                    resolution="NO_MATCH",
                    messages=["I could not resolve the next-to target object."]
                )

            # Resolve a descriptive next-to target using the general object resolver
            object_resolution = resolve_generic_object(
                world=world,
                object_ref=target_ref,
                utterance=utterance,
                description="next-to target object"
            )
            return TargetResolutionResult(
                next_to_id=object_resolution.object_id,
                candidate_ids=object_resolution.candidate_ids,
                resolution=object_resolution.resolution,
                messages=[object_resolution.message]
            )

        case _:
            return TargetResolutionResult(
                resolution="NO_MATCH",
                messages=[
                    f"Unsupported target relation: {relation_type}."
                ]
            )



def resolve_role_object(
    world: World,
    object_class: str,
    symbolic_ref: Dict[str, Any],
    model_checker: Optional[ModelChecker] = None,
    utterance: Optional[str] = None,
    reference_role: Optional[str] = None
) -> ResolutionResult:
    """Resolve an object reference within the expected object class.

    Optionally use the Stage 3 model checker when symbolic resolution
    does not produce a unique match.
    """

    prefix_message = ""
    readable_class = object_class.replace("_", " ")

    # Accept a direct ID only if it belongs to the expected object class
    mentioned_ids, invalid_id_message = find_existing_object_ids_in_text(
        world,
        symbolic_ref["object_phrase"],
        report_invalid_schema_id=True
    )
    for object_id in mentioned_ids:
        actual_class = world.get_object_category(object_id)
        if actual_class == object_class:
            return ResolutionResult(
                object_id=object_id,
                candidate_ids=[object_id],
                resolution="UNIQUE_MATCH",
                message=(
                    f"Resolved direct {readable_class} ID: "
                    f"{object_id}."
                )
            )
        prefix_message += (
            f"ID '{object_id}' exists, but it is a "
            f"{actual_class.replace('_', ' ')}, not a {readable_class}.\n"
        )

    # Restrict descriptive resolution to the expected object class
    symbolic_ref["object_class"] = object_class

    matches = resolve_object_candidates(
        world=world,
        object_ref=symbolic_ref
    )
    result = choose_unique_match(
        world=world,
        matches=matches,
        symbolic_ref=symbolic_ref,
        description=readable_class
    )

    # Combine invalid-ID and wrong-class diagnostics with the resolution message
    message_parts = []
    if invalid_id_message is not None:
        message_parts.append(invalid_id_message)
    if prefix_message:
        message_parts.append(prefix_message.rstrip())
    message_parts.append(result.message)

    result.message = "\n".join(message_parts)

    # Ask Stage 3 to validate unresolved or ambiguous references
    if model_checker is not None and result.object_id is None:
        checked_id, checked_message = model_checker.check_resolved_object(
            world=world,
            command=utterance,
            object_class=object_class,
            symbolic_ref=symbolic_ref,
            candidate_ids=result.candidate_ids,
            resolver_message=result.message,
            reference_role=(
                reference_role or f"requested {readable_class}"
            )
        )
        if checked_id is not None:
            result.object_id = checked_id
            result.resolution = "UNIQUE_MATCH"
            result.candidate_ids = [checked_id]
            result.model_correction = True
        result.message = checked_message

    return result



def resolve_generic_object(
    world: World,
    object_ref: Dict[str, Any],
    model_checker: Optional[ModelChecker] = None,
    utterance: Optional[str] = None,
    reference_role: Optional[str] = None,
    description: str = "object"
) -> ResolutionResult:
    """Resolve an object reference when its object class may be unknown.

    Use direct IDs, attribute and relation constraints, and optionally the
    Stage 3 model checker when symbolic resolution is not unique.
    """

    # Prefer an existing object ID mentioned directly in the object phrase
    mentioned_ids, invalid_id_message = find_existing_object_ids_in_text(
        world,
        object_ref["object_phrase"],
        report_invalid_schema_id=True
    )
    if mentioned_ids:
        object_id = mentioned_ids[0]
        return ResolutionResult(
            object_id=object_id,
            candidate_ids=[object_id],
            resolution="UNIQUE_MATCH",
            message=f"Resolved direct object ID: {object_id}."
        )

    # Resolve descriptive references recursively, even without an object class
    matches = resolve_object_candidates(
        world=world,
        object_ref=object_ref
    )

    description = (description if object_ref["object_class"] is None else object_ref["object_class"])
    result = choose_unique_match(
        world=world,
        matches=matches,
        symbolic_ref=object_ref,
        description=description
    )

    # Preserve an unknown direct ID as an INVALID_ID result
    if invalid_id_message is not None:
        result.message = (invalid_id_message + "\n" + result.message)
        if result.object_id is None:
            result.resolution = "INVALID_ID"

    # Ask Stage 3 to validate unresolved or ambiguous references
    if model_checker is not None and result.object_id is None:
        checked_id, checked_message = (
            model_checker.check_resolved_object(
                world=world,
                command=utterance,
                object_class=object_ref["object_class"],
                symbolic_ref=object_ref,
                candidate_ids=result.candidate_ids,
                resolver_message=result.message,
                reference_role=reference_role
            )
        )
        if checked_id is not None:
            result.object_id = checked_id
            result.resolution = "UNIQUE_MATCH"
            result.candidate_ids = [checked_id]
            result.model_correction = True
        result.message = checked_message

    return result



