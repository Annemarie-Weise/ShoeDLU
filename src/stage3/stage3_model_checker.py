"""Hugging Face model checks for shoe-world parsing and object resolution."""

import copy
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

from huggingface_hub import InferenceClient

from .stage3_prompts import (
    AMBIGUOUS_OBJECT_RESOLUTION_PROMPT,
    GENERIC_OBJECT_RESOLUTION_PROMPT,
    INTENT_CLASSIFICATION_PROMPT,
    NO_MATCH_RESOLUTION_PROMPT
)
from ..parsers.base_parser import ParseError, BaseParser
from ..parsers.rule_based_parser import RuleBasedParser
from ..world import World
from ..domain_rules_and_constants import VALID_INTENTS


class ModelChecker:
    """Validate parser and resolver outputs with a constrained Hugging Face model.

    The checker independently reviews predicted intents and unresolved or
    ambiguous object references. Model responses are parsed as JSON and accepted
    only when they contain valid values, permitted object IDs, and confidence
    above the configured threshold.

    Invalid, low-confidence, or failed model responses preserve the original
    symbolic result. Detailed API errors and model reasoning are displayed only
    in verbose mode.
    """
    

    def __init__(
        self,
        model_name: str = "Qwen/Qwen3-4B-Instruct-2507",
        hf_token: Optional[str] = None,
        confidence_threshold: float = 0.75,
        verbose: bool = False
    ):
        """Initialize the Stage 3 model checker and Hugging Face client."""
        
        self.model_name = model_name

        # Prefer an explicitly provided token, otherwise use the environment variable
        self.hf_token = hf_token or os.environ.get("HF_TOKEN")
        self.confidence_threshold = confidence_threshold
        self.verbose = verbose
        if self.hf_token is None:
            raise ValueError(
                "No Hugging Face token found. Set HF_TOKEN as an environment variable."
            )
        self.client = InferenceClient(model=self.model_name, token=self.hf_token)

        

    def call_model_json_prompt(self, prompt: str) -> Dict[str, Any]:
        """Call the model and return its response as a JSON dictionary.

        Failed API calls are retried with increasing delays. If the response
        contains additional text, the method attempts to extract its JSON object.
        A structured error dictionary is returned when all attempts fail.
        """
        
        wait_times = [1, 3, 8]
        last_error = None
        
        for wait_time in wait_times:
            try:
                # Wait before each retry to reduce rate-limit and overload issues
                time.sleep(wait_time)
                response = self.client.chat_completion(
                    messages=[
                        {
                            "role": "system",
                            "content": "You are a strict JSON-only assistant. Output only valid JSON. Nothing else."
                        },
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ],
                    max_tokens=180,
                    temperature=0.0
                )
                content = response.choices[0].message.content
                try:
                    parsed_json = json.loads(content)
                except json.JSONDecodeError:
                    # Recover a JSON object if the model added surrounding text
                    parsed_json = self.extract_json_object(content)
                if not parsed_json:
                    return {
                        "model_error": True,
                        "error_type": "invalid_json",
                        "error_message": "The model did not return valid JSON.",
                        "raw_content": content
                    }
                return parsed_json
            except Exception as error:
                last_error = error
                
        return {
            "model_error": True,
            "error_type": "api_error",
            "error_message": str(last_error).replace("\n\n", "\n").strip()
        }

        

    def extract_json_object(self, text: str) -> Dict[str, Any]:
        """Extract and parse a JSON object surrounded by additional text."""
        
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return {}
            
        try:
            # Parse only the text between the outermost braces
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}

    
        
    def format_model_error_message(self, data: Dict[str, Any], context: str) -> str:
        """Format a Stage 3 model-call failure for dialogue output."""
        
        error_type = data.get("error_type", "unknown_error")
        error_message = data.get("error_message", "No error message available.")
        return (
            f"Stage 3 {context} skipped: the Hugging Face model call failed "
            f"({error_type}). Falling back to the symbolic resolver output."
            + (f"\nModel error:\n{error_message}" if self.verbose else "")
        )

    

    def safe_float(self, value: Any, default: float = 0.0) -> float:
        """Convert a model-provided value to float or return the default."""
        
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    
    
    def check_parser_intent(
        self,
        command: str,
        parsed: Dict[str, Any],
        parser: Optional[BaseParser] = None
    ) -> Tuple[Dict[str, Any], str]:
        """Validate the parsed intent and reparse accepted model corrections."""
    
        checked = copy.deepcopy(parsed)
        if parser is None:
            parser = RuleBasedParser()
    
        original_intent = checked.get("intent")

        # Classify the command independently of the parser's original prediction
        prompt = INTENT_CLASSIFICATION_PROMPT.format(
            command=command,
        )
        data = self.call_model_json_prompt(prompt)

        if data.get("model_error"):
            return checked, self.format_model_error_message(
                data,
                "intent check",
            )
    
        model_intent = data.get("intent")
        confidence = self.safe_float(data.get("confidence"))
        reason = data.get("reason", "")
    
        if model_intent not in VALID_INTENTS:
            message = (
                "Stage 3 intent check returned an unsupported intent "
                f"'{model_intent}'. Keeping '{original_intent}'."
            )
            if self.verbose and reason:
                message += f"\nReason: {reason}"
            return checked, message
        if model_intent == original_intent:
            message = (
                f"Stage 3 intent check: kept intent '{original_intent}' "
            )
            if self.verbose and reason:
                message += f"\nReason: {reason} (Confidence: {confidence:.2f})"
            return checked, message
        if confidence < self.confidence_threshold:
            message = (
                f"Stage 3 intent check suggested '{model_intent}', "
                f"but confidence was only {confidence:.2f}. "
                f"Keeping '{original_intent}'."
            )
            if self.verbose and reason:
                message += f"\nReason: {reason}"
            return checked, message
    
        # Reparse the command so all arguments match the corrected intent
        try:
            checked = parser.parse_command(
                command,
                forced_intent=model_intent
            )
        except ParseError as error:
            message = (
                f"Stage 3 suggested intent '{model_intent}', but reparsing "
                f"failed. Keeping '{original_intent}'."
            )
            if self.verbose and reason:
                message += f"\nReason: {reason}"
            if self.verbose:
                message += f"\nReparse error: {error}"
            return copy.deepcopy(parsed), message
    
        message = (
            "Stage 3 intent check: corrected intent "
            f"'{original_intent}' -> '{model_intent}' "
        )
    
        if self.verbose and reason:
            message += f"\nReason: {reason} (Confidence: {confidence:.2f})"
        return checked, message


        
    def check_resolved_object(
        self,
        world: World,
        command: str,
        object_class: Optional[str],
        symbolic_ref: Dict[str, Any],
        candidate_ids: List[str],
        resolver_message: str,
        reference_role: Optional[str] = None
    ) -> Tuple[Optional[str], str]:
        """Route a failed or ambiguous reference to the appropriate model check."""

        # Without an object class, let the model reason over all permitted objects
        if object_class is None:
            return self.check_generic_object_case(
                world,
                command,
                symbolic_ref,
                candidate_ids,
                resolver_message,
                reference_role
            )
    
        # No symbolic candidates means the reference could not be matched
        if not candidate_ids:
            return self.check_no_match_case(
                world,
                command,
                object_class,
                symbolic_ref,
                resolver_message,
                reference_role
            )
    
        # Multiple symbolic candidates require an ambiguity check
        return self.check_ambiguous_case(
            world,
            command,
            object_class,
            symbolic_ref,
            candidate_ids,
            resolver_message,
            reference_role
        )


        
    def check_no_match_case(
        self,
        world: World,
        command: str,
        object_class: str,
        symbolic_ref: Dict[str, Any],
        resolver_message: str,
        reference_role: Optional[str] = None
    ) -> Tuple[Optional[str], str]:
        """Try to recover an object ID after symbolic resolution found no match."""
    
        # Limit model selection to existing objects of the requested class
        allowed_ids = world.get_all_object_ids(object_class)
    
        if not allowed_ids:
            stage3_message = (
                f"Stage 3 object recovery: there are no objects of class "
                f"'{object_class}' in the world."
            )
            return None, resolver_message + "\n" + stage3_message
    
        prompt = NO_MATCH_RESOLUTION_PROMPT.format(
            command=command,
            reference_role=reference_role or f"requested {object_class}",
            object_class=object_class,
            symbolic_ref=json.dumps(symbolic_ref, indent=2),
            resolver_message=resolver_message,
            world_state=world.describe(),
            valid_values=world.describe_valid_values(),
            allowed_ids=json.dumps(allowed_ids)
        )
    
        data = self.call_model_json_prompt(prompt)
    
        if data.get("model_error"):
            return None, (
                resolver_message
                + "\n"
                + self.format_model_error_message(data, "object recovery")
            )
    
        selected_id = data.get("selected_id")
        confidence = self.safe_float(data.get("confidence"))
        reason = data.get("reason", "")
    
        # Reject invented or wrong object IDs
        if selected_id not in allowed_ids:
            stage3_message = (
                "Stage 3 object recovery: the model did not select a valid "
                f"{object_class} ID. Keeping symbolic failure."
            )
            return None, resolver_message + "\n" + stage3_message
    
        # Accept the suggestion only when it passes the confidence threshold
        if confidence < self.confidence_threshold:
            stage3_message = (
                f"Stage 3 object recovery: the model suggested {selected_id}, "
                f"but confidence was only {confidence:.2f}. "
                "Keeping symbolic failure."
            )
            return None, resolver_message + "\n" + stage3_message
    
        stage3_message = (
            f"Stage 3 object recovery: selected {selected_id} after symbolic failure."
            + (f"\nReason: {reason}" if self.verbose else "")
        )
        return selected_id, resolver_message + "\n" + stage3_message


        
    def check_ambiguous_case(
        self,
        world: World,
        command: str,
        object_class: str,
        symbolic_ref: Dict[str, Any],
        candidate_ids: List[str],
        resolver_message: str,
        reference_role: Optional[str] = None
    ) -> Tuple[Optional[str], str]:
        """Resolve an ambiguous reference using only symbolic candidates."""

        # Keep only candidates that still exist in the requested object class
        class_ids = set(world.get_all_object_ids(object_class))
        valid_candidate_ids = [
            object_id
            for object_id in candidate_ids
            if object_id in class_ids
        ]
        if not valid_candidate_ids:
            return None, resolver_message
    
        candidate_objects = "\n".join(
            world.describe_object_by_id(object_id)
            for object_id in valid_candidate_ids
        )
    
        prompt = AMBIGUOUS_OBJECT_RESOLUTION_PROMPT.format(
            command=command,
            reference_role=reference_role or f"requested {object_class}",
            object_class=object_class,
            symbolic_ref=json.dumps(symbolic_ref, indent=2),
            resolver_message=resolver_message,
            allowed_ids=json.dumps(valid_candidate_ids),
            candidate_objects=candidate_objects,
            world_state=world.describe(),
            valid_values=world.describe_valid_values()
        )
    
        data = self.call_model_json_prompt(prompt)
    
        if data.get("model_error"):
            return None, (
                resolver_message
                + "\n"
                + self.format_model_error_message(data, "ambiguity check")
            )
    
        selected_id = data.get("selected_id")
        confidence = self.safe_float(data.get("confidence"))
        reason = data.get("reason", "")
    
         # None is a valid response when the available information remains ambiguous
        if selected_id is None:
            stage3_message = (
                "Stage 3 ambiguity check: the model also found the "
                "reference ambiguous."
            )
            return None, resolver_message + "\n" + stage3_message
    
        # Reject any object that was not one of the symbolic candidates
        if selected_id not in valid_candidate_ids:
            stage3_message = (
                "Stage 3 ambiguity check: the model selected an invalid object ID. "
                "Keeping symbolic ambiguity."
            )
            return None, resolver_message + "\n" + stage3_message
    
        # Accept a unique selection only when confidence is high enough
        if confidence < self.confidence_threshold:
            stage3_message = (
                f"Stage 3 ambiguity check: the model suggested {selected_id}, "
                f"but confidence was only {confidence:.2f}. "
                "Keeping symbolic ambiguity."
            )
            return None, resolver_message + "\n" + stage3_message
    
        stage3_message = (
            f"Stage 3 ambiguity check: selected {selected_id} "
            "from multiple candidates."
            + (f"\nReason: {reason}" if self.verbose else "")
        )
        return selected_id, resolver_message + "\n" + stage3_message



    def check_generic_object_case(
        self,
        world: World,
        command: str,
        symbolic_ref: Dict[str, Any],
        candidate_ids: List[str],
        resolver_message: str,
        reference_role: Optional[str] = None
    ) -> Tuple[Optional[str], str]:
        """Resolve an object reference whose object class is unknown."""

        # Use symbolic candidates when available, otherwise consider the full world
        allowed_ids = (
            list(candidate_ids)
            if candidate_ids
            else world.get_all_object_ids()
        )
        if not allowed_ids:
            stage3_message = (
                "Stage 3 generic object recovery: there are no suitable "
                "objects in the world."
            )
            return None, resolver_message + "\n" + stage3_message
    
        allowed_objects = "\n".join(
            world.describe_object_by_id(object_id)
            for object_id in allowed_ids
        )
    
        prompt = GENERIC_OBJECT_RESOLUTION_PROMPT.format(
            command=command,
            reference_role=reference_role or "requested object",
            symbolic_ref=json.dumps(symbolic_ref, indent=2),
            resolver_message=resolver_message,
            allowed_ids=json.dumps(allowed_ids),
            allowed_objects=allowed_objects,
            world_state=world.describe(),
            valid_values=world.describe_valid_values()
        )
    
        data = self.call_model_json_prompt(prompt)
    
        if data.get("model_error"):
            return None, (
                resolver_message
                + "\n"
                + self.format_model_error_message(
                    data,
                    "generic object recovery",
                )
            )
    
        selected_id = data.get("selected_id")
        confidence = self.safe_float(data.get("confidence"))
        reason = data.get("reason", "")
    
        # None is valid when no single object can be identified confidently
        if selected_id is None:
            stage3_message = (
                "Stage 3 generic object recovery: the model could not identify "
                "one suitable object."
            )
            return None, resolver_message + "\n" + stage3_message

        # Reject objects outside the set supplied to the model
        if selected_id not in allowed_ids:
            stage3_message = (
                "Stage 3 generic object recovery: the model selected an invalid "
                "object ID. Keeping symbolic failure."
            )
            return None, resolver_message + "\n" + stage3_message
    
         # Accept a unique selection only when confidence is high enough
        if confidence < self.confidence_threshold:
            stage3_message = (
                f"Stage 3 generic object recovery: the model suggested "
                f"{selected_id}, but confidence was only {confidence:.2f}. "
                "Keeping symbolic failure."
            )
            return None, resolver_message + "\n" + stage3_message
    
        object_class = world.get_object_category(selected_id)
        stage3_message = (
            f"Stage 3 generic object recovery: selected {selected_id}"
            f" ({object_class})."
            + (f"\nReason: {reason}" if self.verbose else "")
        )
        return selected_id, resolver_message + "\n" + stage3_message
