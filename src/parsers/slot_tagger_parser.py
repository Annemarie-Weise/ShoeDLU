"""Implementation of the learned intent and slot-tagging parser for shoe-world commands."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import joblib

from .base_parser import BaseParser
from .training_stage2.slot_features import (
    sentence_to_features,
    tokenize_text
)
from ..domain_rules_and_constants import *

# Type aliases used for token labels and reconstructed slot spans to enhance clarity
TokenLabel = Tuple[str, str]
Span = Tuple[int, int]
SlotSpan = Dict[str, Any]
RelationMatch = Dict[str, Any]


class SlotTaggerParser(BaseParser):
    """Parse shoe-world commands using learned intent classification and BIO slot tagging.

    The parser predicts the command intent, applies the CRF slot tagger once to
    the complete normalized command, and converts the resulting slot and
    relation spans into the common semantic-frame structure used for grounding
    by the dialogue manager.
    """

    RELATION_SLOTS = {
        "TARGET_NEXT_TO_RELATION": ("next_to", "target"),
        "NEXT_TO_RELATION": ("next_to", "describing"),
        "TARGET_LOCATION_RELATION": ("location", "target"),
        "LOCATION_RELATION": ("location", "describing"),
    }

    SHOE_SLOT_MAP = {
        "SHOE_TYPE": ("shoe_type", SHOE_TYPE_ALIASES),
        "SHOE_HEIGHT": ("height", HEIGHT_ALIASES),
        "COLOR": ("color", COLOR_ALIASES),
        "MATERIAL": ("material", MATERIAL_ALIASES),
        "CLEANING_STATUS": ("cleaning_status", CLEANING_STATUS_ALIASES),
        "IMPREGNATION_STATUS": ("impregnation_status", IMPREGNATION_STATUS_ALIASES),
        "SOLE_STATUS": ("sole_status", SOLE_STATUS_ALIASES),
        "MATERIAL_STATUS": ("material_status", MATERIAL_STATUS_ALIASES),
        "DRY_STATUS": ("dry_status", DRY_STATUS_ALIASES),
        "DIRT_TYPE": ("dirt_type", DIRT_TYPE_ALIASES),
        "OBJECT_CLASS": ("generic_class", SHOE_CLASS_ALIASES),
    }

    def __init__(self, intent_model=None, vectorizer=None, slot_tagger=None):
        """Initialize the parser and its learned Stage 2 components.

        If all three components are supplied, they are used directly. Otherwise,
        the trained vectorizer, intent classifier, and CRF slot tagger are loaded
        from the project's default model directory.
        """

        self._reset_state()

        if all(model is not None for model in (intent_model, vectorizer, slot_tagger)):
            self.intent_model = intent_model
            self.vectorizer = vectorizer
            self.slot_tagger = slot_tagger
            return

        # Load the trained models from the project's default model directory
        model_dir = Path(__file__).resolve().parents[2] / "models"
        self.vectorizer = joblib.load(model_dir / "intent_vectorizer.joblib")
        self.intent_model = joblib.load(model_dir / "intent_classifier.joblib")
        self.slot_tagger = joblib.load(model_dir / "slot_tagger_crf.joblib")

    

    def _reset_state(self) -> None:
        """Clear command-specific predictions and role ranges before parsing."""

        self._current_text: Optional[str] = None
        self._current_intent: Optional[str] = None
        self._current_token_labels: List[TokenLabel] = []
        self._role_ranges: Dict[str, Span] = {}



    # ------------------
    # Public API methods
    # ------------------
        
    def parse_command(
        self,
        text: str,
        forced_intent: Optional[str] = None
    ) -> Dict[str, Any]:
        """Parse one command using cached intent and slot predictions."""

        self._reset_state()
        normalized = self.normalize_text(text)
    
        self._current_text = normalized
        self._current_intent = (
            forced_intent
            if forced_intent is not None
            else self.parse_intent(normalized)
        )
        self._current_token_labels = self.predict_slots(
            normalized,
            self._current_intent
        )
        self._role_ranges = self._build_role_ranges(
            self._current_token_labels,
            self._current_intent
        )
    
        # BaseParser supplies the shared intent-specific output composition
        # -> parse_intent() returns cached prediction during this call
        return super().parse_command(
            normalized,
            forced_intent=self._current_intent,
        )


    
    def parse_intent(self, text: str) -> str:
        """Predict the intent of a normalized command using the trained classifier."""

        normalized = self.normalize_text(text)
    
        # Reuse intent if already predicted for the current parsing operation
        if self._current_text == normalized and self._current_intent is not None:
            return self._current_intent
    
        features = self.vectorizer.transform([normalized])
        return str(self.intent_model.predict(features)[0])


    
    def predict_slots(self, text: str, intent: str) -> List[TokenLabel]:
        """Predict BIO slot labels for all tokens in the normalized command."""

        tokens = tokenize_text(self.normalize_text(text))
        if not tokens:
            return []
        sentence = {"tokens": tokens, "intent": intent}
        labels = self.slot_tagger.predict(
            [sentence_to_features(sentence)]
        )[0]

        return list(zip(tokens, labels))


    
    # ----------------
    # BIO-span helpers
    # ---------------

    @staticmethod
    def _slot_spans(token_labels: Sequence[TokenLabel]) -> List[SlotSpan]:
        """Convert BIO-labeled tokens into slot spans with values and token boundaries."""

        spans = []
        current_name = None
        current_tokens = []
        start = 0

        # Store the active span and reset the temporary span state
        def flush(end: int) -> None:
            nonlocal current_name, current_tokens, start
            if current_name is not None:
                spans.append({
                    "slot": current_name,
                    "value": "_".join(current_tokens),
                    "start": start,
                    "end": end
                })
            current_name = None
            current_tokens = []

        for index, (token, label) in enumerate(token_labels):
            if label == "O" or "-" not in label:
                flush(index)
                continue
            prefix, name = label.split("-", 1)
            if prefix == "B" or name != current_name:
                flush(index)
                current_name = name
                current_tokens = [token]
                start = index
            else:
                current_tokens.append(token)

        flush(len(token_labels))
        return spans


    
    @classmethod
    def _merged_slots(cls, token_labels: Sequence[TokenLabel]) -> Dict[str, List[str]]:
        """Group reconstructed slot values by slot name without duplicates."""

        result = {}
        for span in cls._slot_spans(token_labels):
            values = result.setdefault(span["slot"], [])
            if span["value"] not in values:
                values.append(span["value"])
        return result


    
    @classmethod
    def _relation_matches(cls, token_labels: Sequence[TokenLabel]) -> List[RelationMatch]:
        """Convert relation slot spans into normalized relation matches."""

        matches: List[RelationMatch] = []
        for span in cls._slot_spans(token_labels):
            relation = cls.RELATION_SLOTS.get(span["slot"])
            if relation is None:
                continue
            relation_type, relation_role = relation
            matches.append({
                **span,
                "relation_type": relation_type,
                "relation_role": relation_role
            })
        return matches


    
    # --------------
    # Role splitting
    # --------------

    def _build_role_ranges(self, token_labels: List[TokenLabel], intent: str) -> Dict[str, Span]:
        """Assign token ranges to the semantic roles used by BaseParser."""

        full = (0, len(token_labels))
        ranges = {
            "main_object": full,
            "main_object_describing_relation": full,
            "shoe": full,
            "shoe_describing_relation": full,
            "utensil": full,
            "utensil_describing_relation": full,
            "repair_tool": full,
            "repair_tool_describing_relation": full,
            "target": full,
            "target_relation": full,
            "target_describing_relation": full,
            "describing_relation": full
        }
        if not token_labels:
            return ranges

        # Tool actions contain separate shoe and tool references
        if intent in {"CLEAN", "IMPREGNATE", "REPAIR"}:
            shoe_span, tool_span = self._split_shoe_and_tool(token_labels)
            self._set_segment_ranges(ranges, token_labels, "shoe", shoe_span)
            self._set_segment_ranges(ranges, token_labels, "utensil", tool_span)
            self._set_segment_ranges(ranges, token_labels, "repair_tool", tool_span)
            return ranges

        self._set_main_and_target_ranges(ranges, token_labels, intent)
        return ranges


    
    def _split_shoe_and_tool(self, token_labels: List[TokenLabel]) -> Tuple[Span, Span]:
        """Determine the token ranges of the shoe and tool references."""

        total = len(token_labels)

        # Prefer the directional split label predicted by the slot tagger
        split = next(
            (
                span for span in self._slot_spans(token_labels)
                if span["slot"] in {"BEFORE_SENTENCE_SPLIT", "AFTER_SENTENCE_SPLIT"}
            ),
            None
        )
        if split is None:
            # Fall back to the predicted positions of shoe and tool attributes
            tool_names = {
                "CLEANING_TOOL_TYPE",
                "IMPREGNATION_TOOL_TYPE",
                "REPAIR_TOOL_TYPE"
            }
            tool_spans = [s for s in self._slot_spans(token_labels) if s["slot"] in tool_names]
            shoe_spans = [
                s for s in self._slot_spans(token_labels)
                if s["slot"] in self.SHOE_SLOT_MAP and s["slot"] != "OBJECT_CLASS"
            ]
            if tool_spans and shoe_spans:
                tool_start = min(s["start"] for s in tool_spans)
                shoe_start = min(s["start"] for s in shoe_spans)
                if shoe_start < tool_start:
                    return (0, tool_start), (tool_start, total)
                return (tool_start + 1, total), (0, tool_start + 1)
            return (0, total), (0, total)

        left = (0, split["start"])
        right = (split["end"], total)
        if split["slot"] == "BEFORE_SENTENCE_SPLIT":
            return left, right
        return right, left


    
    def _set_segment_ranges(
        self,
        ranges: Dict[str, Span],
        token_labels: List[TokenLabel],
        role: str,
        segment: Span
    ) -> None:
        """Store the object and describing-relation ranges for one semantic role."""

        start, end = segment
        relations = self._relation_matches(token_labels[start:end])

        # The direct object phrase ends where its first describing relation begins
        object_end = start + relations[0]["start"] if relations else end

        ranges[role] = (start, object_end)
        ranges[f"{role}_describing_relation"] = segment


    
    def _choose_target_match(
        self,
        intent: str,
        matches: List[RelationMatch]
    ) -> Optional[RelationMatch]:
        """Select the relation that introduces the command's target."""

        explicit = [match for match in matches if match["relation_role"] == "target"]
        if explicit:
            return explicit[0]

        # Fall back to intent-specific relation ordering when no target was tagged
        if intent == "MOVE":
            return matches[-1] if matches else None
        if intent == "PUT_DOWN":
            return next(
                (match for match in matches if match["relation_type"] == "next_to"),
                matches[0] if matches else None,
            )
        return None


    
    def _set_main_and_target_ranges(
        self,
        ranges: Dict[str, Span],
        token_labels: List[TokenLabel],
        intent: str
    ) -> None:
        """Separate the main object, target, and relation token ranges."""

        total = len(token_labels)
        matches = self._relation_matches(token_labels)

        # Only movement commands require a separate target reference
        target = self._choose_target_match(intent, matches) if intent in {"MOVE", "PUT_DOWN"} else None

        if intent == "PUT_DOWN":
            # PUT_DOWN acts on the currently held object, so relations belong to
            # the placement target and not to the source description
            # -> "in hand" is not learned as a relation for PUT_DOWN
            source_end = target["start"] if target else total
            ranges["main_object"] = (0, source_end)
            ranges["main_object_describing_relation"] = (0, source_end)
        else:
            # Keep source-describing relations, but exclude the target relation
            source_relations = matches
            if target is not None:
                source_relations = [m for m in matches if m["start"] < target["start"]]
            source_end = source_relations[0]["start"] if source_relations else (
                target["start"] if target is not None else total
            )
            ranges["main_object"] = (0, source_end)
            ranges["main_object_describing_relation"] = (
                0,
                target["start"] if target is not None else total
            )

        # Single-object commands reuse the main-object ranges for typed parsing
        for role in ("shoe", "utensil", "repair_tool"):
            ranges[role] = ranges["main_object"]
            ranges[f"{role}_describing_relation"] = ranges["main_object_describing_relation"]

        if target is not None:
            # The direct target ends before any relation describing that target
            later = [m["start"] for m in matches if m["start"] > target["start"]]
            immediate_end = min(later) if later else total
            ranges["target"] = (target["end"], immediate_end)
            ranges["target_relation"] = (
                target["start"],
                total if intent == "PUT_DOWN" else immediate_end,
            )
            ranges["target_describing_relation"] = (target["end"], total)
            return

        # Predicted target location can still identify the destination when the
        # model fails to assign a relation label to words such as "on" or "inside"
        target_locations = [
            span for span in self._slot_spans(token_labels)
            if span["slot"] == "TARGET_LOCATION"
        ]
        if target_locations:
            location = target_locations[-1]
            # Exclude the target location from the source-object description
            ranges["main_object"] = (0, location["start"])
            ranges["main_object_describing_relation"] = (0, location["start"])
            for role in ("shoe", "utensil", "repair_tool"):
                ranges[role] = ranges["main_object"]
                ranges[f"{role}_describing_relation"] = ranges["main_object_describing_relation"]
            ranges["target"] = (location["start"], location["end"])
            ranges["target_relation"] = (location["start"], location["end"])


    
    def _labels_for_role(self, role: str) -> List[TokenLabel]:
        """Return the cached token-label pairs assigned to a semantic role."""

        start, end = self._role_ranges.get(
            role,
            (0, len(self._current_token_labels))
        )
        return self._current_token_labels[start:end]


    
    def _get_phrase_for_role(
        self,
        phrase: str,
        intent: str,
        role: str,
        remove_relation: bool = True,
        apply_role_split: bool = True
    ) -> str:
        """Return the cached phrase assigned to a semantic role.

        Role splitting and relation removal are already represented by the
        role-specific token ranges built for the complete command.
        """

        if self._current_intent == intent and self._current_token_labels:
            labels = self._labels_for_role(role)
            role_phrase = " ".join(
                token for token, _ in labels
            ).strip()

            return role_phrase or self.normalize_text(phrase)
        return self.normalize_text(phrase)


    
    # ----------------------
    # Filter/warning helpers
    # ----------------------

    @staticmethod
    def _warning(
        attribute: str,
        message: str,
        **details: Any
    ) -> Dict[str, Any]:
        """Create a structured parser warning."""

        return {"attribute": attribute, **details, "message": message}


    
    def _map_filters(
        self,
        token_labels: Sequence[TokenLabel],
        mapping: Dict[str, Tuple[str, Dict[str, str]]]
    ) -> Dict[str, Any]:
        """Convert predicted slot values into canonical object filters."""

        slots = self._merged_slots(token_labels)
        filters: Dict[str, Any] = {}
        warnings: List[Dict[str, Any]] = []

        for slot_name, (filter_name, aliases) in mapping.items():
            values = slots.get(slot_name, [])
            if not values:
                continue

            # Use the final prediction when the same slot occurs more than once
            raw = values[-1]
            canonical = aliases.get(raw)

            if canonical is None:
                # OBJECT_CLASS is shared by all typed parsers
                # -> value belonging to another object class is not an error here
                if filter_name != "generic_class":
                    warnings.append(self._warning(
                        filter_name,
                        f"Unknown {filter_name}: {raw}",
                        value=raw
                    ))
            else:
                filters[filter_name] = canonical
            if len(values) > 1:
                warnings.append(self._warning(
                    filter_name,
                    f"Multiple values predicted for {filter_name}: {values}. Used last value: {raw}",
                    values=values,
                    used_value=raw
                ))

        if warnings:
            filters["warnings"] = warnings
        return filters


    
    def _add_threshold(
        self,
        filters: Dict[str, Any],
        token_labels: Sequence[TokenLabel],
        normal_key: str,
        bounded_key: str,
        bounded_words: str
    ) -> None:
        """Add a predicted percentage threshold to the object filters."""

        values = self._merged_slots(token_labels).get("THRESHOLD", [])
        if not values:
            return

        warnings = filters.setdefault("warnings", [])
        raw = values[-1]
        number = re.search(r"\b\d{1,3}\b", raw)
        if number is None:
            warnings.append(self._warning(
                normal_key,
                f"Could not extract percentage from threshold: {raw}",
                value=raw
            ))
        else:
            value = int(number.group())
            if not 0 <= value <= 100:
                warnings.append(self._warning(
                    normal_key,
                    f"{normal_key.replace('_', ' ').title()} must be between 0 and 100, got {value}.",
                    value=value
                ))
            elif re.search(
                    bounded_words,
                    (" ".join(token for token, _ in token_labels).strip())
                ):
                filters[bounded_key] = value
            else:
                filters[normal_key] = value

        if len(values) > 1:
            warnings.append(self._warning(
                normal_key,
                f"Multiple values predicted for {normal_key}: {values}. Used last value: {raw}",
                values=values,
                used_value=raw
            ))
        if not warnings:
            filters.pop("warnings", None)


    
    # -------------------------
    # BaseParser abstract hooks
    # -------------------------

    def _parse_shoe_ref(
        self,
        phrase: str,
        intent: str,
        role: str = "main_object",
        **_: Any
    ) -> Dict[str, Any]:
        """Build shoe filters from cached slot labels for the requested role."""

        return self._map_filters(self._labels_for_role(role), self.SHOE_SLOT_MAP)


    
    def _parse_utensil_ref(
        self,
        phrase: str,
        utensil_category: str,
        intent: str,
        role: str = "main_object",
        **_: Any,
    ) -> Dict[str, Any]:
        """Build utensil filters from cached slot labels for the requested role."""

        if utensil_category == "cleaning":
            mapping = {
                "CLEANING_TOOL_TYPE": ("utensil_type", CLEANING_TOOL_ALIASES),
                "OBJECT_CLASS": ("generic_class", CLEANING_UTENSIL_CLASS_ALIASES)
            }
        else:
            mapping = {
                "IMPREGNATION_TOOL_TYPE": ("utensil_type", IMPREGNATION_TOOL_ALIASES),
                "OBJECT_CLASS": ("generic_class", IMPREGNATION_UTENSIL_CLASS_ALIASES)
            }
        labels = self._labels_for_role(role)
        filters = self._map_filters(labels, mapping)

        # Interpret bounded percentages as minimum required fullness
        self._add_threshold(
            filters,
            labels,
            "fullness_percent",
            "min_fullness",
            r"\b(?:min|minimum|at least)\b"
        )

        return filters



    def _parse_repair_tool_ref(
        self,
        phrase: str,
        intent: str,
        role: str = "main_object",
        **_: Any
    ) -> Dict[str, Any]:
        """Build repair-tool filters from cached slot labels for the requested role."""

        labels = self._labels_for_role(role)
        filters = self._map_filters(labels, {
            "REPAIR_TOOL_TYPE": ("tool_type", REPAIR_TOOL_ALIASES),
            "OBJECT_CLASS": ("generic_class", REPAIR_TOOL_CLASS_ALIASES)
        })

        # Interpret bounded percentages as the maximum permitted tool damage.
        self._add_threshold(
            filters,
            labels,
            "damage_status",
            "max_damage",
            r"\b(?:max|maximum|at most)\b"
        )

        return filters



    def _parse_repair_part_ref(
        self,
        phrase: str,
        part: str,
        intent: str
    ) -> Dict[str, Any]:
        """Return the predicted repair target when it matches the requested part."""

        values = self._merged_slots(self._current_token_labels).get("REPAIR_TARGET", [])
        if not values:
            return {}
        raw = values[-1]
        canonical = REPAIR_PART_ALIASES.get(raw)

        # BaseParser requests each supported repair part separately
        if canonical != part:
            return {}

        result: Dict[str, Any] = {"value": part}
        if len(values) > 1:
            result["warnings"] = [self._warning(
                "repair_target",
                f"Multiple values predicted for repair_target: {values}. Used last value: {raw}",
                values=values,
                used_value=raw,
            )]
        return result



    def _parse_walk_ref(self, phrase: str, intent: str) -> Dict[str, Any]:
        """Build walk-condition filters from the command's cached slot labels."""

        return self._map_filters(self._current_token_labels, {
            "WALK_LENGTH": ("walk_length", WALK_LENGTH_ALIASES),
            "WALK_WEATHER": ("weather", WEATHER_ALIASES),
            "WALK_PLACE": ("place", WALK_PLACE_ALIASES)
        })



    # -----------------
    # Relation building
    # -----------------

    def _object_ref_from_labels(
        self,
        token_labels: List[TokenLabel],
        intent: str
    ) -> Optional[Dict[str, Any]]:
        """Build an object reference from the labels of an isolated relation target."""

        phrase = (" ".join(token for token, _ in token_labels).strip())
        candidates = [
            ("cleaning_utensil", self._map_filters(token_labels, {
                "CLEANING_TOOL_TYPE": ("utensil_type", CLEANING_TOOL_ALIASES),
                "OBJECT_CLASS": ("generic_class", CLEANING_UTENSIL_CLASS_ALIASES)
            })),
            ("impregnation_utensil", self._map_filters(token_labels, {
                "IMPREGNATION_TOOL_TYPE": ("utensil_type", IMPREGNATION_TOOL_ALIASES),
                "OBJECT_CLASS": ("generic_class", IMPREGNATION_UTENSIL_CLASS_ALIASES)
            })),
            ("repair_tool", self._map_filters(token_labels, {
                "REPAIR_TOOL_TYPE": ("tool_type", REPAIR_TOOL_ALIASES),
                "OBJECT_CLASS": ("generic_class", REPAIR_TOOL_CLASS_ALIASES)
            })),
            ("shoe", self._map_filters(token_labels, self.SHOE_SLOT_MAP))
        ]

        # Return the first object category supported by a recognized slot value
        for object_class, filters in candidates:
            meaningful = {key: value for key, value in filters.items() if key != "warnings"}
            if meaningful:
                return {
                    "object_class": object_class,
                    "filters": filters,
                    "object_phrase": phrase,
                    "relation_refs": [],
                }
        return None



    def _relation_ref(
        self,
        token_labels: List[TokenLabel],
        matches: List[RelationMatch],
        match: RelationMatch,
        intent: str
    ) -> Optional[Dict[str, Any]]:
        """Build a normalized relation reference from one predicted relation span."""

        # The relation target extends up to the beginning of the next relation.
        next_start = next(
            (other["start"] for other in matches if other["start"] > match["start"]),
            len(token_labels)
        )

        target_labels = token_labels[match["end"]:next_start]
        target_phrase = " ".join(
            token for token, _ in target_labels
        ).strip()
        if not target_phrase:
            return None

        if match["relation_type"] == "location":
            # Target relations always require a destination location
            # Describing relations can refer to either an object or target location
            location_names = {"TARGET_LOCATION"} if match["relation_role"] == "target" else {
                "OBJECT_LOCATION", "TARGET_LOCATION"
            }
            locations = [
                span for span in self._slot_spans(token_labels)
                if span["slot"] in location_names
                and match["end"] <= span["start"] < next_start
            ]
            if not locations:
                return None
            location = LOCATION_ALIASES.get(locations[-1]["value"])
            relation_type = self.get_relation_type_for_location(location) if location else None
            if relation_type is None:
                return None
            return {"relation_type": relation_type, "target_location": location}

        # A next-to relation requires an object reference
        target_ref = self._object_ref_from_labels(target_labels, intent)
        return {
            "relation_type": "next_to",
            "target_ref": target_ref,
            "target_phrase": target_phrase
        }



    def _describing_chain(
        self,
        token_labels: List[TokenLabel],
        matches: List[RelationMatch],
        intent: str,
    ) -> List[Dict[str, Any]]:
        """Build a nested chain of relations describing an object."""

        roots: List[Dict[str, Any]] = []
        current = roots
        for match in matches:
            relation = self._relation_ref(token_labels, matches, match, intent)
            if relation is None:
                continue
            current.append(relation)

            # Further relations describe the target of the preceding next-to relation
            if (
                relation["relation_type"] == "next_to"
                and relation.get("target_ref") is not None
            ):
                relation["target_ref"]["relation_refs"] = []
                current = relation["target_ref"]["relation_refs"]
        return roots



    def _target_location_fallback(
        self,
        token_labels: List[TokenLabel]
    ) -> Optional[Dict[str, Any]]:
        """Build a target-location relation when no relation span was predicted."""

        locations = [
            span for span in self._slot_spans(token_labels)
            if span["slot"] == "TARGET_LOCATION"
        ]
        if not locations:
            return None

        # Use the final target-location prediction if several were produced
        location = LOCATION_ALIASES.get(locations[-1]["value"])
        relation_type = (
            self.get_relation_type_for_location(location)
            if location
            else None
        )

        if relation_type is None:
            return None
        return {"relation_type": relation_type, "target_location": location}



    def _parse_relation_ref(
        self,
        phrase: str,
        intent: str,
        role: str = "describing_relation",
    ) -> List[Dict[str, Any]]:
        """Build target or describing relations from the cached slot labels."""

        labels = self._labels_for_role(role)
        matches = self._relation_matches(labels)

        # Target relations represent the destination of MOVE and PUT_DOWN commands
        if role == "target_relation":
            chosen = self._choose_target_match(intent, matches)

            # A tagged target location can recover a missing relation prediction
            if chosen is None:
                fallback = self._target_location_fallback(labels)
                return [fallback] if fallback is not None else []

            relation = self._relation_ref(labels, matches, chosen, intent)
            if relation is None:
                fallback = self._target_location_fallback(labels)
                return [fallback] if fallback is not None else []

            # PUT_DOWN supports relations that describe its placement target
            # MOVE target nesting is not consumed reliably by the dialogue manager -> omitted
            if (
                intent == "PUT_DOWN"
                and relation["relation_type"] == "next_to"
                and relation.get("target_ref") is not None
            ):
                following = [
                    match for match in matches
                    if (
                        match["relation_role"] == "describing"
                        and match["start"] > chosen["start"]
                    )
                ]
                relation["target_ref"]["relation_refs"] = (
                    self._describing_chain(
                        labels,
                        following,
                        intent
                    )
                )
            return [relation]

        # PUT_DOWN acts on the held object, which requires no source description
        if intent == "PUT_DOWN" and role == "main_object_describing_relation":
            return []

        describing = [
            match
            for match in matches
            if match["relation_role"] == "describing"
        ]

        # For MOVE, exclude the relation that introduces the destination from the
        # relations used to identify the source object
        if intent == "MOVE" and role == "main_object_describing_relation":
            target = self._choose_target_match(intent, matches)
            if target is not None:
                describing = [
                    match
                    for match in describing
                    if match["start"] < target["start"]
                ]
            elif len(describing) <= 1:
                describing = []
            else:
                describing = describing[:-1]

        return self._describing_chain(labels, describing, intent)
