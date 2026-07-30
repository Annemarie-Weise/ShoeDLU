"""
Define the shared parser interface and command-parsing pipeline.

This module provides the common intent-specific frame construction used by all
parser implementations, together with abstract hooks for reference extraction
and the ParseError raised for unsupported or unparseable commands.
"""

import re
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List

from ..domain_rules_and_constants import (
    SHELF_LOCATIONS,
    VALID_LOCATIONS
)

class ParseError(Exception):
    """Raised when a command cannot be parsed."""
    pass

class BaseParser(ABC):
    """Abstract base class for command parsers.

    Define the shared parsing pipeline for all command parsers.

    The base class maps predicted intents to a common semantic-frame structure.
    Subclasses implement intent detection and the reference-extraction methods
    for shoes, tools, relations, repair parts, and walk parameters.

    Reference methods return dictionaries containing canonical world values or
    empty dictionaries when no matching reference is found. They may also
    include a warnings list for non-fatal parsing issues.
    """


    
    #-------------------
    # Public API methods
    #-------------------

    def parse_command(
        self,
        text: str,
        forced_intent: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Parse command text, optionally using a predefined intent."""
    
        normalized_text = self.normalize_text(text)
        intent = (
            forced_intent
            if forced_intent is not None
            else self.parse_intent(normalized_text)
        )
    
        parser_map = self.__get_parser_map()
        if intent not in parser_map:
            raise ParseError(f"No parser implemented for intent: {intent}")
    
        argument_text = self.prepare_argument_text(
            normalized_text,
            intent
        )
    
        return parser_map[intent](argument_text)



    @abstractmethod
    def parse_intent(self, text: str) -> str:
        """Parse or predict the command intent."""
        pass



    #-----------------------
    # General helper methods
    #-----------------------

    def normalize_text(self, text: str) -> str:
        """Lowercase text, remove sentence punctuation, and normalize spaces."""
        
        text = text.lower().strip()
        text = re.sub(r"[^\w\s%]", " ", text) # remove , . ! ? ; : ( )
        text = re.sub(r"\s+", " ", text)
        return text



    def prepare_argument_text(self, text: str, intent: str) -> str:
        """Return text prepared for intent-specific parsing.

        The base parser leaves the text unchanged. Subclasses can override this
        method if they need to remove command words or otherwise adapt the text
        before parsing arguments.
        """
        
        return text



    def get_relation_type_for_location(self, location: str) -> Optional[str]:
        """Return the symbolic relation type that fits this world location."""

        if location in SHELF_LOCATIONS:
            return "on"
        if location in VALID_LOCATIONS:
            return "inside"
        return None
    
        

    # --------------------------------
    # Private intent-specific parsers
    # --------------------------------

    def __get_parser_map(self):
        """Return the parser method for each supported intent."""
        
        return {
            "PICK_UP": self.__parse_pick_up,
            "PUT_DOWN": self.__parse_put_down,
            "MOVE": self.__parse_move,
            "CLEAN": self.__parse_clean,
            "IMPREGNATE": self.__parse_impregnate,
            "DRY": self.__parse_dry,
            "REPAIR": self.__parse_repair,
            "GET_NEW_TOOL": self.__parse_get_new_tool,
            "GO_ON_WALK": self.__parse_go_on_walk
        }

    
        
    def __parse_pick_up(self, text: str) -> Dict[str, Any]:
        """Parse a pick-up command into an object reference."""
    
        intent = "PICK_UP"
        return {
            "intent": intent,
            "object_ref": self._parse_object_ref(text, intent, "main_object")
        }
    

    
    def __parse_put_down(self, text: str) -> Dict[str, Any]:
        """Parse a put-down command into object and target references."""
    
        intent = "PUT_DOWN"
        return {
            "intent": intent,
            "object_ref": self._parse_object_ref(text, intent, "main_object"),
            "target_relation_refs": self._parse_relation_ref(text, intent, "target_relation")
        }

    
    
    def __parse_move(self, text: str) -> Dict[str, Any]:
        """Parse a move command into object and target references."""
    
        intent = "MOVE"
        return {
            "intent": intent,
            "object_ref": self._parse_object_ref(text, intent, role="main_object"),
            "target_relation_refs": self._parse_relation_ref(text, intent, "target_relation")
        }


        
    def __parse_clean(self, text: str) -> Dict[str, Any]:
        """Parse a clean command into shoe and cleaning utensil references."""
    
        intent = "CLEAN"
        return {
            "intent": intent,
            "shoe_ref": self._parse_typed_object_ref(text, "shoe", intent, role="shoe"),
            "utensil_ref": self._parse_typed_object_ref(
                text,
                "cleaning_utensil",
                intent,
                role="utensil"
            )
        }


        
    def __parse_impregnate(self, text: str) -> Dict[str, Any]:
        """Parse an impregnation command into shoe and impregnation utensil references."""
    
        intent = "IMPREGNATE"
        return {
            "intent": intent,
            "shoe_ref": self._parse_typed_object_ref(text, "shoe", intent, role="shoe"),
            "utensil_ref": self._parse_typed_object_ref(
                text,
                "impregnation_utensil",
                intent,
                role="utensil"
            )
        }


    
    def __parse_dry(self, text: str) -> Dict[str, Any]:
        """Parse a dry command into a shoe reference."""
    
        intent = "DRY"
        return {
            "intent": intent,
            "shoe_ref": self._parse_typed_object_ref(text, "shoe", intent, role="shoe")
        }

    
    
    def __parse_repair(self, text: str) -> Dict[str, Any]:
        """Parse a repair command into a shoe reference, repair parts, and repair tool reference."""
    
        intent = "REPAIR"
        return {
            "intent": intent,
            "shoe_ref": self._parse_typed_object_ref(text, "shoe", intent, role="shoe"),
            "material_ref": self._parse_repair_part_ref(text, "material", intent),
            "sole_ref": self._parse_repair_part_ref(text, "sole", intent),
            "tool_ref": self._parse_typed_object_ref(
                text,
                "repair_tool",
                intent,
                role="repair_tool"
            )
        }

        

    def __parse_get_new_tool(self, text: str) -> Dict[str, Any]:
        """Parse a request for a new tool into possible tool references.

        Exactly one tool reference is expected to match.
        """
        
        intent = "GET_NEW_TOOL"
        return {
            "intent": intent,
            "tool_cleaning_ref": self._parse_utensil_ref(
                text,
                "cleaning",
                intent,
                role="utensil"
            ),
            "tool_impregnation_ref": self._parse_utensil_ref(
                text,
                "impregnation",
                intent,
                role="utensil"
            ),
            "tool_repair_ref": self._parse_repair_tool_ref(
                text,
                intent,
                role="repair_tool"
            )
        }

        
    
    def __parse_go_on_walk(self, text: str) -> Dict[str, Any]:
        """Parse a walk command into a shoe reference and walk details."""
    
        intent = "GO_ON_WALK"
        return {
            "intent": intent,
            "shoe_ref": self._parse_typed_object_ref(text, "shoe", intent, role="shoe"),
            "walk_ref": self._parse_walk_ref(text, intent)
        }

    
    
    #---------------------------
    # Protected structure helper
    #---------------------------

    def _get_phrase_for_role(
        self,
        phrase: str,
        intent: str,
        role: str,
        remove_relation: bool = True,
        apply_role_split: bool = False
    ) -> str:
        """Return the normalized phrase relevant to an object role.

        Subclasses can override this method to split role-specific phrases
        or remove relational descriptions.
        """
        return self.normalize_text(phrase)

        

    def _parse_typed_object_ref(
        self,
        phrase: str,
        object_class: str,
        intent: str,
        role: str = "main_object",
        apply_role_split: bool = True
    ) -> Dict[str, Any]:
        """Build a typed object reference for the requested semantic role."""
    
        object_phrase = self._get_phrase_for_role(
            phrase, 
            intent, 
            role,
            apply_role_split=apply_role_split
        )

        match object_class:
            case "shoe":
                filters = self._parse_shoe_ref(
                    object_phrase,
                    intent,
                    role=role
                )
    
            case "cleaning_utensil":
                filters = self._parse_utensil_ref(
                    object_phrase,
                    "cleaning",
                    intent,
                    role=role
                )
    
            case "impregnation_utensil":
                filters = self._parse_utensil_ref(
                    object_phrase,
                    "impregnation",
                    intent,
                    role=role
                )
    
            case "repair_tool":
                filters = self._parse_repair_tool_ref(
                    object_phrase,
                    intent,
                    role=role
                )
    
            case _:
                filters = {}
    
        return {
            "object_class": object_class,
            "filters": filters,
            "object_phrase": object_phrase,
            "relation_refs": self._parse_relation_ref(
                phrase,
                intent,
                f"{role}_describing_relation"
            )
        }
    

        
    def _parse_object_ref(
        self,
        phrase: str,
        intent: str,
        role: str = "main_object"
    ) -> Dict[str, Any]:
        """Parse a generic object reference using the first matching object class."""
    
        # The first object class with matching filters determines the reference type
        for object_class in [
            "cleaning_utensil",
            "impregnation_utensil",
            "repair_tool",
            "shoe"
        ]:
            object_ref = self._parse_typed_object_ref(
                phrase, 
                object_class, 
                intent, 
                role,
                apply_role_split=False
            )
            if object_ref["filters"]:
                return object_ref
    
        object_phrase = self._get_phrase_for_role(phrase, intent, role)
        return {
            "object_class": None,
            "filters": {},
            "object_phrase": object_phrase,
            "relation_refs": self._parse_relation_ref(
                phrase,
                intent,
                f"{role}_describing_relation"
            )
        }



    #----------------------------------
    # Abstract protected subclass hooks
    #----------------------------------

    @abstractmethod
    def _parse_relation_ref(
        self,
        phrase: str,
        intent: str,
        role: str = "describing_relation",
    ) -> List[Dict[str, Any]]:
        """Parse relation references for the requested semantic role.

        Return canonical relation-reference dictionaries, or an empty list
        if no relation is found.
        """
        pass

    
    
    @abstractmethod
    def _parse_shoe_ref(
        self,
        phrase: str,
        intent: str,
        role: str = "main_object"
    ) -> Dict[str, Any]:
        """Parse a shoe reference into canonical filter values.

        Return an empty dictionary if the phrase does not describe a shoe.

        Possible filter keys include:
        - shoe_type
        - height
        - color
        - material
        - cleaning_status
        - impregnation_status
        - sole_status
        - material_status
        - dry_status
        - dirt_type

        The result may also include a warnings key.
        """
        pass

    

    @abstractmethod
    def _parse_utensil_ref(
        self,
        phrase: str,
        utensil_category: str,
        intent: str,
        role: str = "main_object"
    ) -> Dict[str, Any]:
        """Parse a utensil reference into canonical filter values.

        utensil_category must be either "cleaning" or "impregnation".

        Return an empty dictionary if the phrase does not describe the requested
        utensil category.

        Possible filter keys include:
        - utensil_type
        - location
        - fullness_percent
        - min_fullness

        The result may also include a warnings key.
        """
        pass


    
    @abstractmethod
    def _parse_repair_tool_ref(
        self,
        phrase: str,
        intent: str,
        role: str = "main_object"
    ) -> Dict[str, Any]:
        """Parse a repair-tool reference into canonical filter values.

        Return an empty dictionary if the phrase does not describe a repair tool.

        Possible filter keys include:
        - tool_type
        - location
        - damage_status
        - max_damage

        The result may also include a warnings key.
        """
        pass

    

    @abstractmethod
    def _parse_repair_part_ref(
        self,
        phrase: str,
        part: str,
        intent: str
    ) -> Dict[str, Any]:
        """Parse whether a requested shoe part is mentioned for repair.

        part must be either "sole" or "material".

        Return {"value": part} if the requested part is mentioned, or an
        empty dictionary otherwise.

        The result may also include a warnings key.
        """
        pass



    @abstractmethod
    def _parse_walk_ref(self, phrase: str, intent: str) -> Dict[str, Any]:
        """Parse walk details into canonical values.

        Return an empty dictionary if no walk details are found.

        Possible keys include:
        - walk_length
        - weather
        - place

        The result may also include a warnings key.
        """
        pass


    
