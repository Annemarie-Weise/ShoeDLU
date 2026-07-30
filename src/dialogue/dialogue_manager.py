"""Coordinate command interpretation and execution in the shoe-rack world.

This module parses commands, optionally validates them with Stage 3,
resolves symbolic references, dispatches intents to action handlers,
and returns structured interpretation and execution results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from ..world import World
from ..domain_rules_and_constants import (
    CLEANING_TOOLS,
    IMPREGNATION_TOOLS,
    REPAIR_TOOLS
)
from ..parsers import BaseParser, ParseError, RuleBasedParser
from ..grounding import *
from ..stage3 import ModelChecker

# ----------------------------------------
# Dialogue formatting
# ----------------------------------------

def collect_parse_warnings(value: Any) -> List[Dict[str, Any]]:
    """Collect all parser warnings from a nested parse result."""

    warnings = []

    if isinstance(value, dict):
        own_warnings = value.get("warnings")
        if isinstance(own_warnings, list):
            warnings.extend(own_warnings)

        for key, child in value.items():
            if key != "warnings":
                warnings.extend(collect_parse_warnings(child))

    elif isinstance(value, list):
        for child in value:
            warnings.extend(collect_parse_warnings(child))

    return warnings



def format_parse_warnings(warnings: List[Dict[str, Any]]) -> str:
    """Format parser warnings as a readable text block."""
    
    if not warnings:
        return ""
        
    lines = ["Parser warnings:"]
    for warning in warnings:
        message = warning.get("message", str(warning))
        lines.append(f"- {message}")
    return "\n".join(lines)



def format_dialogue_output(result: dialogue.InterpretationResult) -> str:
    """Format an InterpretationResult as readable dialogue output."""
    
    system_parts = []
    if result.intent_message:
        system_parts.append(result.intent_message)
    if result.system_messages:
        system_parts.extend(result.system_messages)
    output_parts = []
    if system_parts:
        output_parts.append(
            "_" * 20 + "SYSTEM MESSAGES" + "_" * 20 + "\n\n"
            + "\n\n".join(system_parts)
        )
    if result.action_result:
        output_parts.append(
            "_" * 20 + "ACTION RESULT" + "_" * 20 + "\n\n"
            + result.action_result
        )
    return "\n\n".join(output_parts)
    


# ----------------------------------------
# Intent handlers
# ----------------------------------------

@dataclass
class HandlerResult:
    """Store the grounding and execution result of an intent handler."""

    messages: List[str] = field(default_factory=list)
    action_result: Optional[str] = None
    object_id: Optional[str] = None
    tool_id: Optional[str] = None
    next_to_id: Optional[str] = None
    location: Optional[str] = None
    tool_type: Optional[str] = None
    created_object_id: Optional[str] = None
    status: str = "NO_ACTION"
    success: Optional[bool] = None
    object_resolution: Optional[str] = None
    tool_resolution: Optional[str] = None
    target_resolution: Optional[str] = None
    object_candidate_ids: List[str] = field(default_factory=list)
    tool_candidate_ids: List[str] = field(default_factory=list)
    target_candidate_ids: List[str] = field(default_factory=list)
    model_corrected_object: bool = False
    model_corrected_tool: bool = False

    

def handle_pick_up(
    world: World,
    utterance: str,
    parsed: Dict[str, Any],
    checker: Optional[ModelChecker] = None,
) -> HandlerResult:
    """Resolve the requested object and execute the pick-up action."""

    resolution = resolve_generic_object(
        world=world,
        utterance=utterance,
        object_ref=parsed["object_ref"],
        model_checker=checker,
        description="main object",
        reference_role="object that should be picked up"
    )

    if resolution.object_id is None:
        return HandlerResult(
            messages=[resolution.message],
            object_resolution=resolution.resolution,
            object_candidate_ids=resolution.candidate_ids
        )

    success, action_result = world.pick_up(resolution.object_id)
    return HandlerResult(
        messages=[resolution.message],
        action_result=action_result,
        object_id=resolution.object_id,
        status="EXECUTED",
        success=success,
        object_resolution=resolution.resolution,
        object_candidate_ids=resolution.candidate_ids,
        model_corrected_object=resolution.model_correction
    )



def handle_put_down(
    world: World,
    utterance: str,
    parsed: Dict[str, Any],
    checker: Optional[ModelChecker] = None,
) -> HandlerResult:
    """Resolve the held object and target, then execute the put-down action.
    The checker parameter is kept for a consistent handler interface.
    """

    messages = []
    object_ref = parsed["object_ref"]
    object_id = None
    object_resolution = None
    object_candidate_ids = []

    matches = resolve_object_candidates(world, object_ref)
    object_candidate_ids = list(matches)

    if len(matches) == 1:
        object_id = matches[0]
        object_resolution = "UNIQUE_MATCH"
        messages.append(f"Resolved requested object to {object_id}.")
    # Prefer the matching held object when the description is ambiguous
    elif len(matches) > 1:
        held_ids = [world.holding] if world.holding is not None else []
        held_matches = resolve_object_candidates(
            world=world,
            object_ref=object_ref,
            candidate_ids=held_ids
        )
        if held_matches:
            object_id = held_matches[0]
            object_resolution = "UNIQUE_MATCH"
            object_candidate_ids = list(held_matches)
            messages.append(f"Resolved requested held object to {object_id}.")
        else:
            ref_text = "\n".join(format_symbolic_ref_lines(object_ref))
            messages.append(
                "Several requested objects match this description, "
                "but none of them is currently held.\n"
                f"I looked for this held object:\n{ref_text}"
            )
            return HandlerResult(
                messages=messages,
                object_resolution="AMBIGUOUS",
                object_candidate_ids=object_candidate_ids
            )
    elif not (
        object_ref["object_class"] is None
        and not object_ref["filters"]
        and not object_ref["relation_refs"]
    ):
        resolution = choose_unique_match(
            world=world,
            matches=[],
            symbolic_ref=object_ref,
            description="put-down object"
        )
        messages.append(resolution.message)
        return HandlerResult(
            messages=messages,
            object_resolution=resolution.resolution,
            object_candidate_ids=resolution.candidate_ids
        )

    # If no object was described, use the currently held object
    if object_id is None:
        object_id = world.holding
        if object_id is not None:
            object_resolution = "UNIQUE_MATCH"
            object_candidate_ids = [object_id]
    if object_id is None:
        messages.append("There is no object currently being held.")
        return HandlerResult(
            messages=messages,
            object_resolution=object_resolution,
            object_candidate_ids=object_candidate_ids
        )

    if not parsed["target_relation_refs"]:
        messages.append(
            "I understood that you want to put something down, but not where."
        )
        return HandlerResult(
            messages=messages,
            object_id=object_id,
            object_resolution=object_resolution,
            object_candidate_ids=object_candidate_ids
        )

    # Resolve the requested placement target or spatial relation
    target_relation_ref = parsed["target_relation_refs"][0]
    target_resolution = resolve_target_relation(
        world=world,
        utterance=utterance,
        target_relation_ref=target_relation_ref
    )
    location = target_resolution.location
    next_to_id = target_resolution.next_to_id
    messages.extend(target_resolution.messages)

    if location is None and next_to_id is None:
        return HandlerResult(
            messages=messages,
            object_id=object_id,
            object_resolution=object_resolution,
            target_resolution=target_resolution.resolution,
            object_candidate_ids=object_candidate_ids,
            target_candidate_ids=target_resolution.candidate_ids
        )

    success, action_result = world.put_down(
        object_id=object_id,
        new_location=location,
        next_to_id=next_to_id
    )
    return HandlerResult(
        messages=messages,
        action_result=action_result,
        object_id=object_id,
        location=location,
        next_to_id=next_to_id,
        status="EXECUTED",
        success=success,
        object_resolution=object_resolution,
        target_resolution=target_resolution.resolution,
        object_candidate_ids=object_candidate_ids,
        target_candidate_ids=target_resolution.candidate_ids
    )



def handle_move(
    world: World,
    utterance: str,
    parsed: Dict[str, Any],
    checker: Optional[ModelChecker] = None,
) -> HandlerResult:
    """Resolve the object and target, then execute the move action."""

    messages = []
    resolution = resolve_generic_object(
        world=world,
        utterance=utterance,
        object_ref=parsed["object_ref"],
        model_checker=checker,
        description="main object",
        reference_role="object that should be moved"
    )
    messages.append(resolution.message)

    if resolution.object_id is None:
        return HandlerResult(
            messages=messages,
            object_resolution=resolution.resolution,
            object_candidate_ids=resolution.candidate_ids,
            model_corrected_object=resolution.model_correction
        )

    object_id = resolution.object_id
    if not parsed["target_relation_refs"]:
        messages.append("I understood that you want to move something, but not where.")
        return HandlerResult(
            messages=messages,
            object_id=object_id,
            object_resolution=resolution.resolution,
            object_candidate_ids=resolution.candidate_ids,
            model_corrected_object=resolution.model_correction
        )

    # Resolve the requested destination or next-to relation
    target_relation_ref = parsed["target_relation_refs"][0]
    target_resolution = resolve_target_relation(
        world=world,
        utterance=utterance,
        target_relation_ref=target_relation_ref
    )
    location = target_resolution.location
    next_to_id = target_resolution.next_to_id
    messages.extend(target_resolution.messages)

    if location is None and next_to_id is None:
        return HandlerResult(
            messages=messages,
            object_id=object_id,
            object_resolution=resolution.resolution,
            target_resolution=target_resolution.resolution,
            object_candidate_ids=resolution.candidate_ids,
            target_candidate_ids=target_resolution.candidate_ids,
            model_corrected_object=resolution.model_correction
        )

    success, action_result = world.move_object(
        object_id=object_id,
        new_location=location,
        next_to_id=next_to_id
    )
    return HandlerResult(
        messages=messages,
        action_result=action_result,
        object_id=object_id,
        location=location,
        next_to_id=next_to_id,
        status="EXECUTED",
        success=success,
        object_resolution=resolution.resolution,
        target_resolution=target_resolution.resolution,
        object_candidate_ids=resolution.candidate_ids,
        target_candidate_ids=target_resolution.candidate_ids,
        model_corrected_object=resolution.model_correction
    )



def handle_dry(
    world: World,
    utterance: str,
    parsed: Dict[str, Any],
    checker: Optional[ModelChecker] = None,
) -> HandlerResult:
    """Resolve the requested shoe and execute the drying action."""

    resolution = resolve_role_object(
        world=world,
        utterance=utterance,
        object_class="shoe",
        symbolic_ref=parsed["shoe_ref"],
        model_checker=checker,
        reference_role="shoe that should be dried"
    )
    if resolution.object_id is None:
        return HandlerResult(
            messages=[resolution.message],
            object_resolution=resolution.resolution,
            object_candidate_ids=resolution.candidate_ids,
            model_corrected_object=resolution.model_correction
        )

    success, action_result = world.dry_shoe(resolution.object_id)
    return HandlerResult(
        messages=[resolution.message],
        action_result=action_result,
        object_id=resolution.object_id,
        status="EXECUTED",
        success=success,
        object_resolution=resolution.resolution,
        object_candidate_ids=resolution.candidate_ids,
        model_corrected_object=resolution.model_correction
    )



def get_repair_target(parsed: Dict[str, Any]) -> str:
    """Return which part of the shoe should be repaired."""

    sole_ref = parsed["sole_ref"]
    material_ref = parsed["material_ref"]
    sole_part = sole_ref.get("value") if sole_ref else None
    material_part = material_ref.get("value") if material_ref else None

    if sole_part is not None and material_part is not None:
        return "both"
    if sole_part is not None:
        return "sole"
    if material_part is not None:
        return "material"
    return "both"



def handle_shoe_tool_action(
    world: World,
    utterance: str,
    parsed: Dict[str, Any],
    checker: Optional[ModelChecker] = None,
    intent: str = "CLEAN",
) -> HandlerResult:
    """Resolve the shoe and required tool, then execute the requested action."""

    messages = []
    shoe_resolution = resolve_role_object(
        world=world,
        utterance=utterance,
        object_class="shoe",
        symbolic_ref=parsed["shoe_ref"],
        model_checker=checker,
        reference_role=f"shoe used for the {intent.lower()} action"
    )
    messages.append(shoe_resolution.message)

    # Select the required tool class and parsed reference for the intent
    match intent:
        case "CLEAN":
            tool_class = "cleaning_utensil"
            tool_ref_name = "utensil_ref"
        case "IMPREGNATE":
            tool_class = "impregnation_utensil"
            tool_ref_name = "utensil_ref"
        case "REPAIR":
            tool_class = "repair_tool"
            tool_ref_name = "tool_ref"
        case _:
            raise ValueError(f"Unsupported shoe-tool intent: {intent}")

    tool_resolution = resolve_role_object(
        world=world,
        utterance=utterance,
        object_class=tool_class,
        symbolic_ref=parsed[tool_ref_name],
        model_checker=checker,
        reference_role=f"{tool_class} used for the {intent.lower()} action"
    )
    messages.append(tool_resolution.message)

    shoe_id = shoe_resolution.object_id
    tool_id = tool_resolution.object_id
    if shoe_id is None or tool_id is None:
        return HandlerResult(
            messages=messages,
            object_id=shoe_id,
            tool_id=tool_id,
            object_resolution=shoe_resolution.resolution,
            tool_resolution=tool_resolution.resolution,
            object_candidate_ids=shoe_resolution.candidate_ids,
            tool_candidate_ids=tool_resolution.candidate_ids,
            model_corrected_object=shoe_resolution.model_correction,
            model_corrected_tool=tool_resolution.model_correction
        )

    # Dispatch the resolved shoe and tool to the corresponding world action
    match intent:
        case "CLEAN":
            success, action_result = world.clean_shoe(shoe_id, tool_id)
        case "IMPREGNATE":
            success, action_result = world.impregnate_shoe(shoe_id, tool_id)
        case "REPAIR":
            repair_target = get_repair_target(parsed)
            success, action_result = world.repair_shoe(
                shoe_id,
                tool_id,
                repair_target
            )
            
    return HandlerResult(
        messages=messages,
        action_result=action_result,
        object_id=shoe_id,
        tool_id=tool_id,
        status="EXECUTED",
        success=success,
        object_resolution=shoe_resolution.resolution,
        tool_resolution=tool_resolution.resolution,
        object_candidate_ids=shoe_resolution.candidate_ids,
        tool_candidate_ids=tool_resolution.candidate_ids,
        model_corrected_object=shoe_resolution.model_correction,
        model_corrected_tool=tool_resolution.model_correction
    )



def handle_go_on_walk(
    world: World,
    utterance: str,
    parsed: Dict[str, Any],
    checker: Optional[ModelChecker] = None,
) -> HandlerResult:
    """Resolve the requested shoe and execute the walk action."""

    resolution = resolve_role_object(
        world=world,
        utterance=utterance,
        object_class="shoe",
        symbolic_ref=parsed["shoe_ref"],
        model_checker=checker,
        reference_role="shoe used to go on a walk"
    )
    if resolution.object_id is None:
        return HandlerResult(
            messages=[resolution.message],
            object_resolution=resolution.resolution,
            object_candidate_ids=resolution.candidate_ids,
            model_corrected_object=resolution.model_correction
        )

    # Use default walk parameters when optional details were not parsed
    walk_ref = parsed["walk_ref"]
    success, action_result = world.go_on_a_walk(
        shoe_id=resolution.object_id,
        length=walk_ref.get("walk_length", "short"),
        place=walk_ref.get("place", "park"),
        weather=walk_ref.get("weather", "sunny")
    )
    return HandlerResult(
        messages=[resolution.message],
        action_result=action_result,
        object_id=resolution.object_id,
        status="EXECUTED",
        success=success,
        object_resolution=resolution.resolution,
        object_candidate_ids=resolution.candidate_ids,
        model_corrected_object=resolution.model_correction
    )



def handle_get_new_tool(
    world: World,
    parsed: Dict[str, Any],
) -> HandlerResult:
    """Determine the requested tool type and create it in the world."""

    messages = []
    cleaning_ref = parsed["tool_cleaning_ref"]
    impregnation_ref = parsed["tool_impregnation_ref"]
    repair_ref = parsed["tool_repair_ref"]
    tool_type = ""
    tool_class = ""
    valid_types = CLEANING_TOOLS | IMPREGNATION_TOOLS | REPAIR_TOOLS

    # Identify the requested tool class and its valid tool types
    if cleaning_ref:
        tool_class = "cleaning"
        tool_type = cleaning_ref.get("utensil_type")
        valid_types = CLEANING_TOOLS
    elif impregnation_ref:
        tool_class = "impregnation"
        tool_type = impregnation_ref.get("utensil_type")
        valid_types = IMPREGNATION_TOOLS
    elif repair_ref:
        tool_class = "repair"
        tool_type = repair_ref.get("tool_type")
        valid_types = REPAIR_TOOLS

    # Ask for a specific type if the parser found no usable tool type
    if not tool_type:
        valid_text = ", ".join(valid_types)
        if tool_class:
            messages.append(
                f"I understood that you want a new {tool_class} tool, "
                f"but not which type.\nValid types: {valid_text}"
            )
        else:
            messages.append(
                f"I understood that you want a new tool, "
                f"but not which type.\nValid types: {valid_text}"
            )
        return HandlerResult(messages=messages)

    success, action_result, created_object_id = (
        world.get_new_tool_from_infinite_toolbox(
            tool_class,
            tool_type
        )
    )
    return HandlerResult(
        messages=messages,
        action_result=action_result,
        tool_type=tool_type,
        created_object_id=created_object_id,
        status="EXECUTED",
        success=success
    )



# ----------------------------------------
# Main dialogue entry point
# ----------------------------------------

@dataclass
class InterpretationResult:
    """Store the complete result of interpreting and executing a command."""

    intent: Optional[str] = None
    original_intent: Optional[str] = None
    parsed: Optional[Dict[str, Any]] = None
    intent_message: str = ""
    system_messages: List[str] = field(default_factory=list)
    action_result: Optional[str] = None
    object_id: Optional[str] = None
    tool_id: Optional[str] = None
    next_to_id: Optional[str] = None
    location: Optional[str] = None
    tool_type: Optional[str] = None
    created_object_id: Optional[str] = None
    status: str = "NO_ACTION"
    success: Optional[bool] = None
    object_resolution: Optional[str] = None
    tool_resolution: Optional[str] = None
    target_resolution: Optional[str] = None
    object_candidate_ids: List[str] = field(default_factory=list)
    tool_candidate_ids: List[str] = field(default_factory=list)
    target_candidate_ids: List[str] = field(default_factory=list)
    model_corrected_intent: bool = False
    model_corrected_object: bool = False
    model_corrected_tool: bool = False
    
    

def interpret_and_act(
    world: World,
    utterance: str,
    parser: Optional[BaseParser] = None,
    intent_display: bool = True,
    model_checker: Optional[ModelChecker] = None
) -> InterpretationResult:
    """Parse, ground, and execute one user command.

    Optionally validate the parsed intent with Stage 3 and return the
    complete interpretation, resolution, and execution result.
    """

    if parser is None:
        parser = RuleBasedParser()

    system_messages = []
    intent_message = ""
    model_corrected_intent = False

    # Parse the command and optionally validate or correct its intent
    try:
        parsed = parser.parse_command(utterance)
        intent = parsed["intent"]
        original_intent = intent

        if intent_display:
            intent_message = f"I interpreted your command as: {intent}"

        if model_checker is not None:
            parsed, check_message = model_checker.check_parser_intent(
                utterance,
                parsed,
                parser
            )
            intent = parsed["intent"]
            model_corrected_intent = intent != original_intent

            if check_message:
                if intent_message:
                    intent_message += "\n"
                intent_message += check_message

    except ParseError as error:
        return InterpretationResult(
            system_messages=[f"I could not parse the command:\n{error}"],
            status="NO_ACTION"
        )

    # Collect warnings stored anywhere in the nested parse result
    # only the SlotTaggerParser can issue such warnings
    parse_warnings = format_parse_warnings(
        collect_parse_warnings(parsed)
    )
    if parse_warnings:
        system_messages.append(parse_warnings)

    # Dispatch the parsed intent to its corresponding action handler
    match intent:
        case "PICK_UP":
            handler_result = handle_pick_up(
                world, utterance, parsed, model_checker
            )
        case "PUT_DOWN":
            handler_result = handle_put_down(
                world, utterance, parsed, model_checker
            )
        case "MOVE":
            handler_result = handle_move(
                world, utterance, parsed, model_checker
            )
        case "DRY":
            handler_result = handle_dry(
                world, utterance, parsed, model_checker
            )
        case "CLEAN" | "IMPREGNATE" | "REPAIR":
            handler_result = handle_shoe_tool_action(
                world, utterance, parsed, model_checker, intent
            )
        case "GO_ON_WALK":
            handler_result = handle_go_on_walk(
                world, utterance, parsed, model_checker
            )
        case "GET_NEW_TOOL":
            handler_result = handle_get_new_tool(world, parsed)
        case _:
            return InterpretationResult(
                intent=intent,
                parsed=parsed,
                intent_message=intent_message,
                system_messages=system_messages,
                status="NO_ACTION"
            )

    system_messages.extend(handler_result.messages)

    # Combine parser, grounding, and execution information into one result
    return InterpretationResult(
        intent=intent,
        original_intent=original_intent,
        parsed=parsed,
        intent_message=intent_message,
        system_messages=system_messages,
        action_result=handler_result.action_result,
        object_id=handler_result.object_id,
        tool_id=handler_result.tool_id,
        next_to_id=handler_result.next_to_id,
        location=handler_result.location,
        tool_type=handler_result.tool_type,
        created_object_id=handler_result.created_object_id,
        status=handler_result.status,
        success=handler_result.success,
        object_resolution=handler_result.object_resolution,
        tool_resolution=handler_result.tool_resolution,
        target_resolution=handler_result.target_resolution,
        object_candidate_ids=handler_result.object_candidate_ids,
        tool_candidate_ids=handler_result.tool_candidate_ids,
        target_candidate_ids=handler_result.target_candidate_ids,
        model_corrected_intent=model_corrected_intent,
        model_corrected_object=handler_result.model_corrected_object,
        model_corrected_tool=handler_result.model_corrected_tool
    )
