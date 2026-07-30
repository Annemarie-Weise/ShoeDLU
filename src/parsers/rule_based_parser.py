"""Implementation of the rule-based parser for shoe-world commands."""

import re
from typing import Dict, Any, Optional, List, Mapping

from .base_parser import BaseParser, ParseError
from ..domain_rules_and_constants import *

class RuleBasedParser(BaseParser):
    """Parse shoe-world commands using regular expressions and alias matching.

    The parser identifies intents, extracts object and relation references,
    and converts recognized aliases into canonical world values for grounding
    by the dialogue manager.
    """

    
    INTENT_PATTERNS = {
        "PICK_UP": r"\b(?:pick up|pick|grab|take)\b",
        "PUT_DOWN": r"\b(?:put down|set down|down|drop|leave)\b",
        "MOVE": r"\b(?:move|place|put)\b",
        "CLEAN": r"\b(?:clean|wash)\b",
        "IMPREGNATE": r"\b(?:impregnate|protect|waterproof)\b",
        "REPAIR": r"\b(?:repair|fix)\b",
        "GET_NEW_TOOL": r"\b(?:get new|get a new|get replacement|replace)\b",
        "GO_ON_WALK": r"\b(?:go on a|go on|go for a|walk|hike|hiking)\b",
        # Keep DRY last because "dry" can also be a shoe property
        "DRY": r"\bdry\b"
    }

    RELATION_PATTERNS = [
        ("next_to", r"\b(?:right next to|next to|beside)\b"),
        ("inside", r"\b(?:inside|within|into)\b"),  # Plain "in" would be to risky -> handled through Fallback
        ("on", r"\b(?:on top of|on|onto)\b"),  # Plain "to" would be to risky -> handled through Fallback
    ]
    DESCRIBING_RELATION_PATTERNS = [
        ("on", r"\b(?:off of|from|off)\b")
    ]

    TOOL_SPLIT_PHRASE = r"\b(?:with|using|by using)\b"

    

    def parse_intent(self, text: str) -> str:
        """Return the first intent whose regex pattern matches the command text."""
        
        t = self.normalize_text(text)
        for intent, pattern in self.INTENT_PATTERNS.items():
            if re.search(pattern, t):
                return intent
        raise ParseError(f"Could not identify intent in command: '{text}'")


        
    def prepare_argument_text(self, text: str, intent: str) -> str:
        """Remove the matched intent phrase before parsing arguments.

        This prevents intent words such as "dry" from also being parsed
        as object attributes.
        """
        
        pattern = self.INTENT_PATTERNS[intent]
        return re.sub(pattern, "", text, count=1).strip()


    
    def find_alias_match(
        self,
        symbol_text: str,
        aliases: Mapping[str, str],
    ) -> Optional[str]:
        """Find an alias in symbolic text and return its canonical value."""

        matches = [
            value for value in aliases.keys()
            if re.search(rf"(^|_){re.escape(value)}($|_)", symbol_text) is not None
        ]
        if not matches:
            return None
        the_match = max(matches, key=len)
        return aliases[the_match]



    def find_relation_matches(
        self,
        phrase: str,
        role: str = "describing_relation",
    )  -> List[Dict[str, Any]]:
        """Return all relation mentions in the phrase, ordered by position."""
    
        normalized = self.normalize_text(phrase)
        relation_patterns = list(self.RELATION_PATTERNS)
        if role.endswith("_describing_relation") or role == "describing_relation":
            relation_patterns += self.DESCRIBING_RELATION_PATTERNS
    
        matches = []
        for relation_type, pattern in relation_patterns:
            for match in re.finditer(pattern, normalized):
                matches.append({
                    "relation_type": relation_type,
                    "start": match.start(),
                    "end": match.end(),
                    "text": match.group(0),
                })
        matches.sort(key=lambda item: item["start"])
        return matches



    def build_relation_ref_from_match(
        self,
        phrase: str,
        intent: str,
        relation_match: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Build a relation reference from one matched relation phrase."""
    
        relation_type = relation_match["relation_type"]
        target_phrase = phrase[relation_match["end"]:].strip()
        if not target_phrase:
            return None
    
        # on / inside point only to locations in this world
        if relation_type in {"on", "inside"}:
            symbol = self.normalize_text(target_phrase).replace(" ", "_")
            location = self.find_alias_match(symbol, LOCATION_ALIASES)
            if location is None:
                return None
            canonical_relation_type = self.get_relation_type_for_location(location)
            if canonical_relation_type is None:
                return None
            return {
                "relation_type": canonical_relation_type,
                "target_location": location
            }
    
        # next_to points only to another object
        if relation_type == "next_to":
            target_ref = self._parse_object_ref(
                    target_phrase, 
                    intent
                )

            # A next-to target may remain unresolved when it is a raw object ID
            if not target_ref["filters"] and not target_ref["relation_refs"]:
                target_ref = None

            return {
                "relation_type": relation_type,
                "target_ref": target_ref,
                "target_phrase": target_phrase
            }
    
        return None



    def build_put_down_target_relation(
        self,
        phrase: str,
        intent: str,
        relation_matches: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """Build the target relation for PUT_DOWN.
    
        For PUT_DOWN, the object is assumed to be held already.
        Therefore, relations do not describe the held object.
    
        Priority:
        - first next_to relation wins
        - following relations describe the next_to target object
        - if there is no next_to relation, use the first location relation
        """
    
        if not relation_matches:
            return self.parse_target_location_as_relation(phrase)
    
        # Prefer the first next-to relation over location relations
        for index, relation_match in enumerate(relation_matches):
            if relation_match["relation_type"] == "next_to":
                target_phrase = phrase[relation_match["end"]:].strip()
                if not target_phrase:
                    return None
    
                next_relation_matches = relation_matches[index:]
    
                relation_refs = self.build_describing_relation_chain(
                    phrase[relation_match["start"]:],
                    intent,
                    [
                        {
                            **match,
                            "start": match["start"] - relation_match["start"],
                            "end": match["end"] - relation_match["start"],
                        }
                        for match in next_relation_matches
                    ]
                )
    
                if not relation_refs:
                    return None
    
                return relation_refs[0]
    
        # Without next-to, use the first location relation as the target
        first_match = relation_matches[0]
        return self.build_relation_ref_from_match(
            phrase,
            intent,
            first_match,
        )



    def parse_target_location_as_relation(
        self,
        phrase: str
    ) -> Optional[Dict[str, Any]]:
        """Parse a plain location into a canonical target relation."""
    
        symbol = self.normalize_text(phrase).replace(" ", "_")
        location = self.find_alias_match(symbol, LOCATION_ALIASES)
        if location is None:
            return None
        relation_type = self.get_relation_type_for_location(location)
        if relation_type is None:
            return None
        return {
            "relation_type": relation_type,
            "target_location": location
        }



    def build_describing_relation_chain(
        self,
        phrase: str,
        intent: str,
        relation_matches: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Build nested relation constraints for an object description.

        Location relations constrain the current object. A next_to relation
        changes the current object so that following relations describe its target.

        Unparsed next-to targets are preserved with target_ref=None because
        the grounding layer may still resolve the raw target phrase.
        """
    
        if not relation_matches:
            return []
    
        root_relation_refs = []
        current_relation_refs = root_relation_refs
    
        for index, relation_match in enumerate(relation_matches):
            relation_type = relation_match["relation_type"]
            next_start = (
                relation_matches[index + 1]["start"]
                if index + 1 < len(relation_matches)
                else len(phrase)
            )
            target_phrase = phrase[relation_match["end"]:next_start].strip()
    
            if not target_phrase:
                continue
    
            if relation_type in {"on", "inside"}:
                symbol = self.normalize_text(target_phrase).replace(" ", "_")
                location = self.find_alias_match(symbol, LOCATION_ALIASES)
                if location is None:
                    continue
                canonical_relation_type = self.get_relation_type_for_location(location)
                if canonical_relation_type is None:
                    continue
                current_relation_refs.append({
                    "relation_type": canonical_relation_type,
                    "target_location": location,
                })

                # Location relations do not change the current reference object
                continue
    
            if relation_type == "next_to":
                target_ref = self._parse_object_ref(
                    target_phrase, 
                    intent
                )
                if not target_ref["filters"] and not target_ref["relation_refs"]:
                    target_ref = None
                relation_ref = {
                    "relation_type": "next_to",
                    "target_ref": target_ref,
                    "target_phrase": target_phrase
                }
                current_relation_refs.append(relation_ref)
        
                # Attach following relations to the resolved next-to target
                if target_ref is not None:
                    target_ref["relation_refs"] = []
                    current_relation_refs = target_ref["relation_refs"]
        
                continue
        return root_relation_refs



    def _parse_relation_ref(
        self,
        phrase: str,
        intent: str,
        role: str = "describing_relation",
    ) -> List[Dict[str, Any]]:
        """Parse relation references for the requested semantic role.

        Target relations are interpreted according to the command intent.
        Describing relations are returned as nested object constraints.
        """
    
        role_phrase = self._get_phrase_for_role(
            phrase,
            intent,
            role,
            remove_relation=False
        )
        if not role_phrase:
            return []
        relation_matches = self.find_relation_matches(role_phrase, role)
    
        # Resolve the placement target for MOVE and PUT_DOWN commands
        if role == "target_relation":
            if intent == "PUT_DOWN":
                relation_ref = self.build_put_down_target_relation(
                    role_phrase,
                    intent,
                    relation_matches
                )
            elif relation_matches:
                # For MOVE, the final relation describes the destination
                relation_ref = self.build_relation_ref_from_match(
                    role_phrase,
                    intent,
                    relation_matches[-1]
                )
            else:
                relation_ref = self.parse_target_location_as_relation(role_phrase)
        
            return [] if relation_ref is None else [relation_ref]
    
        if not relation_matches:
            return []
    
        # Build relations that describe the referenced object
        if role.endswith("_describing_relation") or role == "describing_relation":
            if intent == "PUT_DOWN" and role == "main_object_describing_relation":
                return []
            if intent == "MOVE" and role == "main_object_describing_relation":
                if len(relation_matches) == 1:
                    return []
                target_relation_start = relation_matches[-1]["start"]
                role_phrase = role_phrase[:target_relation_start].strip()
                relation_matches = relation_matches[:-1]
        
            return self.build_describing_relation_chain(
                role_phrase,
                intent,
                relation_matches
            )
        return []



    def _get_phrase_for_role(
        self,
        phrase: str,
        intent: str,
        role: str,
        remove_relation: bool = True,
        apply_role_split: bool = True
    ) -> str:
        """Extract the normalized phrase relevant to a semantic role."""
    
        normalized = self.normalize_text(phrase)

        # Separate the main object phrase from an explicitly introduced tool phrase
        if apply_role_split:
            if intent in {"CLEAN", "IMPREGNATE", "REPAIR"}:
                parts = re.split(self.TOOL_SPLIT_PHRASE, normalized, maxsplit=1)
                before_tool = parts[0].strip()
                after_tool = parts[1].strip() if len(parts) > 1 else before_tool
        
                if role.startswith("shoe"):
                    normalized = before_tool
                elif role.startswith(("utensil", "repair_tool")):
                    normalized = after_tool
    
        if not remove_relation:
            return normalized
    
        # Keep only the phrase before the first describing relation
        relation_matches = self.find_relation_matches(
            normalized,
            role=f"{role}_describing_relation"
        )
        if not relation_matches:
            return normalized
    
        return normalized[:relation_matches[0]["start"]].strip()


        
    def _parse_shoe_ref(
        self,
        phrase: str,
        intent: str,
        role: str = "main_object"
    ) -> Dict[str, Any]:
        """Parse a shoe phrase into canonical shoe filters."""
    
        symbol = self.normalize_text(phrase).replace(" ", "_")
    
        shoe_attribute_aliases = {
            "shoe_type": SHOE_TYPE_ALIASES,
            "height": HEIGHT_ALIASES,
            "color": COLOR_ALIASES,
            "material": MATERIAL_ALIASES,
            "cleaning_status": CLEANING_STATUS_ALIASES,
            "impregnation_status": IMPREGNATION_STATUS_ALIASES,
            "sole_status": SOLE_STATUS_ALIASES,
            "material_status": MATERIAL_STATUS_ALIASES,
            "dry_status": DRY_STATUS_ALIASES,
            "dirt_type": DIRT_TYPE_ALIASES,
            "generic_class": SHOE_CLASS_ALIASES
        }
        ref = {}
        for attribute_name, aliases in shoe_attribute_aliases.items():
            value = self.find_alias_match(symbol, aliases)
            if value is not None:
                ref[attribute_name] = value
    
        return ref

    

    def _parse_utensil_ref(
        self,
        phrase: str,
        utensil_category: str,
        intent: str,
        role: str = "main_object"
    ) -> Dict[str, Any]:
        """Parse a cleaning or impregnation utensil phrase into canonical filters."""
    
        symbol = self.normalize_text(phrase).replace(" ", "_")
        alias_lookup = {
            "cleaning": {
                "generic_class": CLEANING_UTENSIL_CLASS_ALIASES,
                "utensil_type": CLEANING_TOOL_ALIASES,
            },
            "impregnation": {
                "generic_class": IMPREGNATION_UTENSIL_CLASS_ALIASES,
                "utensil_type": IMPREGNATION_TOOL_ALIASES,
            },
        }
        ref = {}
        for filter_key, aliases in alias_lookup.get(utensil_category, {}).items():
            value = self.find_alias_match(symbol, aliases)
            if value is not None:
                ref[filter_key] = value
    
        # Parse either a minimum or an exact fullness percentage
        min_match = re.search(
            r"\b(?:min|minimum|at least)\.?\s*(\d{1,3})\s*%",
            phrase.lower()
        )
        if min_match:
            value = int(min_match.group(1))
            if 0 <= value <= 100:
                ref["min_fullness"] = value
            else:
                raise ParseError(
                    f"Fullness percentage must be between 0 and 100, got {value}."
                )
        else:
            explicit_match = re.search(r"\b(\d{1,3})\s*%", phrase.lower())
            if explicit_match:
                value = int(explicit_match.group(1))
                if 0 <= value <= 100:
                    ref["fullness_percent"] = value
                else:
                    raise ParseError(
                        f"Fullness percentage must be between 0 and 100, got {value}."
                    )
    
        return ref


        
    def _parse_repair_tool_ref(
        self,
        phrase: str,
        intent: str,
        role: str = "main_object"
    ) -> Dict[str, Any]:
        """Parse a repair-tool phrase into canonical filters."""
    
        symbol = self.normalize_text(phrase).replace(" ", "_")
        ref = {}
    
        generic_class = self.find_alias_match(symbol, REPAIR_TOOL_CLASS_ALIASES)
        if generic_class is not None:
            ref["generic_class"] = generic_class
        tool_type = self.find_alias_match(symbol, REPAIR_TOOL_ALIASES)
        if tool_type is not None:
            ref["tool_type"] = tool_type
    
        # Parse either a maximum or an exact damage percentage
        max_match = re.search(
            r"\b(?:max|maximum|at most)\.?\s*(\d{1,3})\s*%?(?:\s*damage|\s*damaged)?",
            phrase.lower()
        )
        if max_match:
            value = int(max_match.group(1))
            if 0 <= value <= 100:
                ref["max_damage"] = value
            else:
                raise ParseError(
                    f"Damage percentage must be between 0 and 100, got {value}."
                )
        else:
            explicit_match = re.search(
                r"\b(\d{1,3})\s*%?\s*(?:damage|damaged)\b",
                phrase.lower()
            )
            if explicit_match:
                value = int(explicit_match.group(1))
                if 0 <= value <= 100:
                    ref["damage_status"] = value
                else:
                    raise ParseError(
                        f"Damage percentage must be between 0 and 100, got {value}."
                    )
    
        return ref
        


    def _parse_repair_part_ref(self, phrase: str, part: str, intent: str) -> Dict[str, Any]:
        """Return a repair-part reference if the requested part is mentioned."""
    
        normalized = self.normalize_text(phrase)
    
        # Ignore any explicitly introduced tool phrase
        parts = re.split(self.TOOL_SPLIT_PHRASE, normalized, maxsplit=1)
        normalized = parts[0].strip()

        # Ignore relational descriptions following the repair part
        relation_matches = self.find_relation_matches(
            normalized,
            role="repair_part_describing_relation",
        )
        if relation_matches:
            normalized = normalized[:relation_matches[0]["start"]].strip()
    
        symbol = normalized.replace(" ", "_")
        matched_part = self.find_alias_match(symbol, REPAIR_PART_ALIASES)
        if matched_part == part:
            return {"value": part}
        return {}


    
    def _parse_walk_ref(self, phrase: str, intent: str) -> Dict[str, Any]:
        """Parse walk details into canonical walk filters."""
        
        symbol = self.normalize_text(phrase).replace(" ", "_")
        ref = {}
        
        walk_length = self.find_alias_match(symbol, WALK_LENGTH_ALIASES)
        if walk_length is not None:
            ref["walk_length"] = walk_length
            
        weather = self.find_alias_match(symbol, WEATHER_ALIASES)
        if weather is not None:
            ref["weather"] = weather
            
        place = self.find_alias_match(symbol, WALK_PLACE_ALIASES)
        if place is not None:
            ref["place"] = place
            
        return ref
