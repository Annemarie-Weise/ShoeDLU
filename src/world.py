"""Defines the shoe-rack world model and its available actions.

The module contains classes for shoes, cleaning and impregnation utensils,
and repair tools. The World class stores the current world state and
implements actions such as moving, cleaning, drying, impregnating, repairing,
and using shoes for walks.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import random

from .domain_rules_and_constants import *



@dataclass
class Shoe:
    """Represents a shoe in the shoe-rack world."""
    
    shoe_id: str
    shoe_type: str 
    height: str 
    color: str
    material: str  
    cleaning_status: str 
    dirt_type: Optional[str] 
    impregnation_status: str 
    sole_status: str 
    material_status: str 
    dry_status: str 
    location: str  



@dataclass
class CleaningUtensil:
    """Represents a tool used for cleaning shoes."""
    
    utensil_id: str
    utensil_type: str  
    fullness_percent: int  # 0 = empty, 100 = full
    location: str



@dataclass
class ImpregnationUtensil:
    """Represents a tool used for protecting shoes."""
    
    utensil_id: str
    utensil_type: str
    fullness_percent: int  # 0 = empty, 100 = full
    location: str



@dataclass
class RepairTool:
    """Represents a tool used for repairing shoe damage."""
    
    tool_id: str
    tool_type: str 
    damage_status: int  # 0 = new/usable, 100 = broken
    location: str



def worsen_status(current_status: str, levels: list[str], steps: int) -> str:
    """Move a status toward the worst level without exceeding the list."""

    current_index = levels.index(current_status)
    new_index = min(current_index + steps, len(levels) - 1)
    return levels[new_index]


    
def improve_status(current_status: str, levels: list[str], steps: int) -> str:
    """Move a status toward the best level without exceeding the list."""

    current_index = levels.index(current_status)
    new_index = max(0, current_index - steps)
    return levels[new_index]


@dataclass
class World:
    """Stores and manages the state of the shoe-rack world.

    Attributes:
        shoes: Shoes indexed by object ID.
        cleaning_utensils: Cleaning utensils indexed by object ID.
        impregnation_utensils: Impregnation utensils indexed by object ID.
        repair_tools: Repair tools indexed by object ID.
        shelf_slots: Object IDs stored in each shelf slot.
        on_relations: Objects placed on shelves.
        inside_relations: Objects placed inside areas.
        next_to_relations: Neighboring objects.
        holding: ID of the currently held object.
    """

    
    shoes: Dict[str, Shoe]
    cleaning_utensils: Dict[str, CleaningUtensil]
    impregnation_utensils: Dict[str, ImpregnationUtensil]
    repair_tools: Dict[str, RepairTool]
    shelf_slots: Dict[str, List[Optional[str]]]

    on_relations: Optional[Dict[str, str]] = None
    inside_relations: Optional[Dict[str, str]] = None
    next_to_relations: Optional[Dict[str, List[str]]] = None
    holding: Optional[str] = None


    def __post_init__(self) -> None:
        """Build relation fields from the initial world state."""
        
        self._update_relations()



    def _add_next_to_relation(self, source_id: str, target_id: str) -> None:
        """Add a directed next_to relation."""
    
        if self.next_to_relations is None:
            self.next_to_relations = {}
        if source_id not in self.next_to_relations:
            self.next_to_relations[source_id] = []
        if target_id not in self.next_to_relations[source_id]:
            self.next_to_relations[source_id].append(target_id)



    def _add_all_next_to_relations_in_location(self, location: str) -> None:
        """Mark all objects in a non-shelf location as next to each other."""
    
        object_ids = [
            object_id
            for object_id in self.get_all_object_ids()
            if self.get_location(object_id) == location
        ]
        for index, object_id_1 in enumerate(object_ids):
            for object_id_2 in object_ids[index + 1:]:
                self._add_next_to_relation(object_id_1, object_id_2)
                self._add_next_to_relation(object_id_2, object_id_1)


    
    def get_all_object_ids(
        self,
        object_class: Optional[str] = None
    ) -> List[str]:
        """Return object IDs in the world, optionally only for one object class."""

        object_ids = []
        match object_class:
            case "shoe":
                object_ids.extend(self.shoes.keys())
            case "cleaning_utensil":
                object_ids.extend(self.cleaning_utensils.keys())
            case "impregnation_utensil":
                object_ids.extend(self.impregnation_utensils.keys())
            case "repair_tool":
                object_ids.extend(self.repair_tools.keys())
            case _:
                object_ids.extend(self.shoes.keys())
                object_ids.extend(self.cleaning_utensils.keys())
                object_ids.extend(self.impregnation_utensils.keys())
                object_ids.extend(self.repair_tools.keys())
        return object_ids



    def get_object_by_id(
        self,
        object_id: str,
        object_class: Optional[str] = None
    ) -> Any:
        """Return an object by ID, optionally searching only one object class."""

        the_object = None
        match object_class:
            case "shoe":
                the_object = self.shoes.get(object_id)
            case "cleaning_utensil":
                the_object = self.cleaning_utensils.get(object_id)
            case "impregnation_utensil":
                the_object = self.impregnation_utensils.get(object_id)
            case "repair_tool":
                the_object = self.repair_tools.get(object_id)
            case _:
                if object_id in self.shoes:
                    the_object = self.shoes[object_id]
                elif object_id in self.cleaning_utensils:
                    the_object = self.cleaning_utensils[object_id]
                elif object_id in self.impregnation_utensils:
                    the_object = self.impregnation_utensils[object_id]
                elif object_id in self.repair_tools:
                    the_object = self.repair_tools[object_id]
        return the_object
    


    def _update_relations(self) -> None:
        """Rebuild symbolic relations from the current object locations.

        Relations:
            on: Objects stored on shelves.
            inside: Objects stored in areas or held in hand.
            next_to: Objects in adjacent shelf slots or the same area.
            holding: Object currently held by the agent.
        """
    
        self.on_relations = {}
        self.inside_relations = {}
        self.next_to_relations = {}
    
        for object_id in self.get_all_object_ids():
            location = self.get_location(object_id)
            match location:
                case "top_shelf" | "middle_shelf" | "bottom_shelf":
                    self.on_relations[object_id] = location
                case "floor_box" | "drying_area":
                    self.inside_relations[object_id] = location
                case "hand":
                    self.inside_relations[object_id] = location
                    self.holding = object_id
                case "tool_area":
                    if object_id not in self.shoes:
                        self.inside_relations[object_id] = "tool_area"
    
        # Adjacent shelf objects
        for shelf_name, slots in sorted(self.shelf_slots.items()):
            for index in range(len(slots) - 1):
                left_object_id = slots[index]
                right_object_id = slots[index + 1]
    
                if left_object_id is not None and right_object_id is not None:
                    self._add_next_to_relation(left_object_id, right_object_id)
                    self._add_next_to_relation(right_object_id, left_object_id)

        # Objects in the same non-shelf area
        for location in ["floor_box", "drying_area", "tool_area"]:
            self._add_all_next_to_relations_in_location(location)



    def check_location_relation(
        self,
        relation_type: str,
        object_id: str,
        location: str
    )-> bool:
        """Check whether an object has an inside or on relation."""
    
        match relation_type:
            case "inside":
                if self.inside_relations is None:
                    return False
                return self.inside_relations.get(object_id) == location
            case "on":
                if self.on_relations is None:
                    return False
                return self.on_relations.get(object_id) == location
            case _:
                return False

    
    
    def check_next_to_relation(
        self,
        object_id_1: str,
        object_id_2: str
    ) -> bool:
        """Return True if the two objects are next to each other."""
    
        if self.next_to_relations is None:
            return False
        return (
            object_id_2 in self.next_to_relations.get(object_id_1, [])
            or object_id_1 in self.next_to_relations.get(object_id_2, [])
        )


    
    def describe_object_by_id(self, object_id: str) -> str:
        """Return a readable one-line description of a specific object."""
    
        if object_id in self.shoes:
            shoe = self.shoes[object_id]
            parts = [
                f"{shoe.dry_status}",
                f"{shoe.color}",
                f"{shoe.material}",
                f"{shoe.shoe_type}",
            ]
            details = [
                f"h={shoe.height}",
                f"clean={shoe.cleaning_status}",
                f"material={shoe.material_status}",
                f"sole={shoe.sole_status}",
                f"imp={shoe.impregnation_status}",
                f"loc={shoe.location}",
            ]
            if shoe.dirt_type is not None:
                details.insert(2, f"dirt={shoe.dirt_type}")
            return (
                f"- {shoe.shoe_id}: "
                f"{' '.join(parts)} "
                f"({', '.join(details)})"
            )
    
        if object_id in self.cleaning_utensils:
            utensil = self.cleaning_utensils[object_id]
            return (
                f"- {utensil.utensil_id}: "
                f"{utensil.utensil_type} "
                f"(full={utensil.fullness_percent}%, loc={utensil.location})"
            )
    
        if object_id in self.impregnation_utensils:
            utensil = self.impregnation_utensils[object_id]
            return (
                f"- {utensil.utensil_id}: "
                f"{utensil.utensil_type} "
                f"(full={utensil.fullness_percent}%, loc={utensil.location})"
            )
    
        if object_id in self.repair_tools:
            tool = self.repair_tools[object_id]
            return (
                f"- {tool.tool_id}: "
                f"{tool.tool_type} "
                f"(damage={tool.damage_status}%, loc={tool.location})"
            )
    
        return object_id
    

    
    def describe_objects_by_class(self, object_class: str) -> str:
        """Return descriptions of all objects in one object class."""
        
        lines = []
        match object_class:
            case "shoe":
                for shoe_id in sorted(self.shoes):
                    lines.append(self.describe_object_by_id(shoe_id))
            case "cleaning_utensil":
                for utensil_id in sorted(self.cleaning_utensils):
                    lines.append(self.describe_object_by_id(utensil_id))
            case "impregnation_utensil":
                for utensil_id in sorted(self.impregnation_utensils):
                    lines.append(self.describe_object_by_id(utensil_id))
            case "repair_tool":
                for tool_id in sorted(self.repair_tools):
                    lines.append(self.describe_object_by_id(tool_id))
        return "\n".join(lines)

        

    def describe(self) -> str:
        """Return a complete text description of the current world state."""
    
        lines = [
            "Shoes:",
            self.describe_objects_by_class("shoe"),
            "\nCleaning utensils:",
            self.describe_objects_by_class("cleaning_utensil"),
            "\nImpregnation utensils:",
            self.describe_objects_by_class("impregnation_utensil"),
            "\nRepair tools:",
            self.describe_objects_by_class("repair_tool"),
            "\nShelf layout:"
        ]
    
        for shelf_name, slots in self.shelf_slots.items():
            slot_text = [
                f"{index}: {object_id or 'empty'}"
                for index, object_id in enumerate(slots)
            ]
            lines.append(f"- {shelf_name}: " + ", ".join(slot_text))
    
        if self.next_to_relations:
            lines.append("\nNext-to relations:")
            for object_id, neighbors in self.next_to_relations.items():
                lines.append(f'- "{object_id}": {neighbors}')
    
        lines.append(f"\nHolding: {self.holding}")
        return "\n".join(lines)



    def describe_valid_values(self) -> str:
        """Return valid domain values grouped by category."""
    
        sections = {
            "Object classes": {
                "object_class": VALID_OBJECT_CLASSES
            },
            "Shoe attributes": {
                "shoe_type": SHOE_TYPES,
                "height": HEIGHTS,
                "color": COLORS,
                "material": MATERIALS,
                "cleaning_level": CLEANING_LEVELS,
                "dirt_type": VALID_SOILS,
                "impregnation_level": IMPREGNATION_LEVELS,
                "sole_level": SOLE_LEVELS,
                "material_level": MATERIAL_LEVELS,
                "dry_level": DRY_LEVEL
            },
            "Cleaning utensil attributes": {
                "utensil_type": CLEANING_TOOLS
            },
            "Impregnation utensil attributes": {
                "utensil_type": IMPREGNATION_TOOLS
            },
            "Repair tool attributes": {
                "tool_type": REPAIR_TOOLS
            },
            "World relations and locations": {
                "location": VALID_LOCATIONS,
                "relation_type": ["on", "inside", "next_to"]
            }
        }
    
        lines = []
        for section_name, attributes in sections.items():
            lines.append(f"{section_name}:")
            for attribute_name, valid_values in attributes.items():
                values_text = ", ".join(map(str, valid_values))
                lines.append(f"- {attribute_name}: [{values_text}]")
            lines.append("")
    
        return "\n".join(lines).rstrip()    

        
    
    def object_exists(self, object_id: str) -> bool:
        """Check whether an object exists in the world."""
        
        return (object_id in self.get_all_object_ids())

        

    def get_object_category(self, object_id: str) -> Optional[str]:
        """Return the object category, or None if the object does not exist."""
        
        if object_id in self.shoes:
            return "shoe"
        if object_id in self.cleaning_utensils:
            return "cleaning_utensil"
        if object_id in self.impregnation_utensils:
            return "impregnation_utensil"
        if object_id in self.repair_tools:
            return "repair_tool"
        return None


    
    def get_location(self, object_id: str) -> str:
        """Return an object's current location.

        Raises:
            RuntimeError: If the object does not exist.
        """
        
        if object_id in self.shoes:
            return self.shoes[object_id].location
        if object_id in self.cleaning_utensils:
            return self.cleaning_utensils[object_id].location
        if object_id in self.impregnation_utensils:
            return self.impregnation_utensils[object_id].location
        if object_id in self.repair_tools:
            return self.repair_tools[object_id].location

        raise RuntimeError(f"Object '{object_id}' does not exist.")



    def _make_unique_id(self, base_name: str) -> str:
        """Create a unique numbered ID from a base name."""
        
        base_name = base_name.replace(" ", "_")

        # Collect all existing object IDs to avoid duplicates
        existing_ids = self.get_all_object_ids()
        counter = 1
        new_id = f"{base_name}_{counter}"
        while new_id in existing_ids:
            counter += 1
            new_id = f"{base_name}_{counter}"
        return new_id


        
    def _find_object_slot(self, object_id: str) -> Optional[Tuple[str, int]]:
        """Return the object's shelf and slot, or None if it is not on a shelf."""
        
        for shelf_name, slots in self.shelf_slots.items():
            for index, stored_object_id in enumerate(slots):
                if stored_object_id == object_id:
                    return shelf_name, index
        return None

        

    def _remove_from_shelf_slots(self, object_id: str) -> None:
        """Remove an object from its shelf slot, if present."""
        
        current_slot = self._find_object_slot(object_id)
        if current_slot is None:
            return
            
        shelf_name, index = current_slot
        self.shelf_slots[shelf_name][index] = None



    def _find_adjacent_free_slot(
        self,
        shelf_name: str,
        index: int
    ) -> Optional[int]:
        """Return a free adjacent slot, checking left before right."""
    
        left_index = index - 1
        if (
            left_index >= 0
            and self.shelf_slots[shelf_name][left_index] is None
        ):
            return left_index
        right_index = index + 1
        if (
            right_index < len(self.shelf_slots[shelf_name])
            and self.shelf_slots[shelf_name][right_index] is None
        ):
            return right_index
        return None


    
    def _find_free_slot(self, shelf_name: str) -> Optional[int]:
        """Return the first free slot, or None if the shelf is full."""
        
        for index, stored_object_id in enumerate(self.shelf_slots[shelf_name]):
            if stored_object_id is None:
                return index
        return None



    def _resolve_next_to_location(
        self,
        object_id: str,
        next_to_id: str
    ) -> Tuple[bool, Optional[str], Optional[int], str]:
        """Resolve a next-to target into a location and optional shelf slot."""

        if not self.object_exists(next_to_id):
            return False, None, None, f"Object '{next_to_id}' does not exist."

        next_to_obj = self.get_object_by_id(next_to_id)
        next_to_location = next_to_obj.location
        if next_to_location not in self.shelf_slots:
            return True, next_to_location, None, ""

        next_to_slot = self._find_object_slot(next_to_id)
        if next_to_slot is None:
            raise RuntimeError(
                f"Object '{next_to_id}' has location '{next_to_location}' "
                "but is missing from the shelf slots."
            )

        shelf_name, index = next_to_slot
        target_slot = self._find_adjacent_free_slot(shelf_name, index)
        if target_slot is None:
            return (
                False,
                None,
                None,
                f"Cannot place {object_id} next to {next_to_id}. "
                "No adjacent shelf slot is free."
            )

        return True, shelf_name, target_slot, ""
    
        

    def _set_location(
        self,
        object_id: str,
        new_location: Optional[str] = None,
        next_to_id: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """Move an object and update shelf slots and spatial relations.

        A next-to target takes priority over a direct location.
        """

        side_effect = None
        target_slot = None

        object_to_move = self.get_object_by_id(object_id)
        if object_to_move is None:
            return False, f"Object '{object_id}' does not exist.", side_effect

        # Resolve a relative target
        if next_to_id is not None:
            if object_id == next_to_id:
                return (
                    False,
                    f"Cannot place {object_id} next to itself.",
                    side_effect
                )
            success, new_location, target_slot, error_message = (
                self._resolve_next_to_location(object_id, next_to_id)
            )
            if not success:
                return False, error_message, side_effect

        # Validate the target location
        if new_location is None:
            return False, "Unknown location.", side_effect
        if new_location not in VALID_LOCATIONS:
            return False, f"Unknown location: {new_location}.", side_effect

        # Apply shoe-specific rules
        if object_id in self.shoes:
            shoe = self.shoes[object_id]
            if new_location not in SHOE_HEIGTH_LOCATION_CONSTRAINTS[shoe.height]:
                return (
                    False,
                    f"Cannot move {object_id} to {new_location}. "
                    f"This shoe has height '{shoe.height}' and does not fit there.",
                    side_effect
                )
            if new_location == "drying_area":
                shoe.dry_status = "dry"
                side_effect = " The shoe is now drying."

        # Select a shelf slot
        if new_location in self.shelf_slots and target_slot is None:
            current_slot = self._find_object_slot(object_id)
            if current_slot is not None and current_slot[0] == new_location:
                target_slot = current_slot[1]
            else:
                target_slot = self._find_free_slot(new_location)

        if new_location in self.shelf_slots and target_slot is None:
            return (
                False,
                f"Cannot move {object_id} to {new_location}. "
                f"{new_location} is full.",
                side_effect
            )

        # Commit the location change
        self._remove_from_shelf_slots(object_id)
        if target_slot is not None:
            self.shelf_slots[new_location][target_slot] = object_id
        object_to_move.location = new_location
        self._update_relations()

        if next_to_id is not None:
            message = (
                f"Set location of {object_id} to {new_location}, "
                f"next to {next_to_id}.\n"
            )
        else:
            message = f"Set location of {object_id} to {new_location}.\n"

        if side_effect is not None:
            message += side_effect
        return True, message, side_effect


        
    def pick_up(self, object_id: str) -> Tuple[bool, str]:
        """Pick up an object and move it to the hand.
        Set the holding relation of the world to the requested object.

        Returns:
            A success flag and the executed action steps message.
        """

        if not self.object_exists(object_id):
            return False, f"Object '{object_id}' does not exist."
        if self.holding is not None:
            return False, (
                f"Cannot pick up {object_id}. "
                f"Already holding {self.holding}."
            )
    
        old_location = self.get_location(object_id)
    
        success, message, _ = self._set_location(
            object_id=object_id,
            new_location="hand"
        )
        if not success:
            return False, message
        self.holding = object_id
        self._update_relations()

        return True, f"Picked up {object_id} from {old_location}."


        
    def put_down(
        self,
        object_id: Optional[str] = None,
        new_location: Optional[str] = None,
        next_to_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """Put down the held object at a location or next to another object.

        Returns:
            A success flag and the executed action steps message.
        """

        if object_id is not None and not self.object_exists(object_id):
            return False, f"Object '{object_id}' does not exist."

        # Use the currently held object if no ID is given
        if object_id is None:
            object_id = self.holding

        if object_id is None:
            return False, "Cannot put anything down. No object is currently held."
        if self.holding != object_id:
            return False, (
                f"Cannot put down {object_id}. You are holding {self.holding}."
            )

        success, set_location_message, side_effect = self._set_location(
            object_id=object_id,
            new_location=new_location,
            next_to_id=next_to_id
        )
        if not success:
            return False, set_location_message + f" {object_id} stays in hand."

        if self.get_location(object_id) != "hand":
            self.holding = None

        self._update_relations()
        message = f"Put {object_id} down at {self.get_location(object_id)}."
        if side_effect is not None:
            message += side_effect

        return True, message


        
    def _ensure_holding(self, object_id: str) -> Tuple[bool, List[str]]:
        """Ensure that the specified object is held.

        If another object is held, put it in its default location first.
        Returns:
            A success flag and the executed action steps message.
        """

        steps = []

        if not self.object_exists(object_id):
            return False, [f"Object '{object_id}' does not exist."]
        if self.holding == object_id:
            return True, [f"{object_id} is already held."]
        if self.holding is not None:
            held_id = self.holding
            held_category = self.get_object_category(held_id)

            # Return shoes to the floor box and tools to the tool area
            put_down_location = (
                "floor_box" if held_category == "shoe" else "tool_area"
            )

            put_down_success, put_down_message = self.put_down(
                object_id=held_id,
                new_location=put_down_location
            )
            steps.append(put_down_message)
            if not put_down_success:
                steps.append(
                    f"Could not put down {held_id}, so {object_id} "
                    "could not be picked up."
                )
                return False, steps

        pick_up_success, pick_up_message = self.pick_up(object_id)
        steps.append(pick_up_message)

        return pick_up_success, steps



    def move_object(
        self,
        object_id: str,
        new_location: Optional[str] = None,
        next_to_id: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Move an object using pick-up and put-down steps.

        Returns:
            A success flag and the executed action steps message.
        """
    
        if not self.object_exists(object_id):
            return False, f"Object '{object_id}' does not exist."
    
        holding_success, steps = self._ensure_holding(object_id)
        if not holding_success:
            # Preserve all completed steps in the result, including failed actions
            message = (
                "Action sequence:\n"
                + "\n".join(
                    f"{index + 1}. {step}"
                    for index, step in enumerate(steps)
                )
                + "\n\nResult:\nThe object could not be moved."
            )
            return False, message
    
        put_down_success, put_down_message = self.put_down(
            object_id=object_id,
            new_location=new_location,
            next_to_id=next_to_id
        )
        steps.append(put_down_message)
        message = (
            "Action sequence:\n"
            + "\n".join(
                f"{index + 1}. {step}"
                for index, step in enumerate(steps)
            )
        )
    
        if not put_down_success:
            message += (
                f"\n\nResult:\n{object_id} could not be placed "
                "at the requested target."
            )
            return False, message
    
        return True, message

        
        
    def clean_shoe(
        self,
        shoe_id: str,
        utensil_id: str,
    ) -> Tuple[bool, str]:
        """Clean a shoe with a cleaning utensil.

        Apply the utensil-specific cleaning effects, update the world state.
        Returns:
            A success flag and the executed action steps message.
        """

        if shoe_id not in self.shoes:
            return False, f"Shoe '{shoe_id}' does not exist."
        if utensil_id not in self.cleaning_utensils:
            return False, f"Cleaning utensil '{utensil_id}' does not exist."

        shoe = self.shoes[shoe_id]
        utensil = self.cleaning_utensils[utensil_id]

        holding_ok, action_steps = self._ensure_holding(utensil_id)
        if not holding_ok:
            message = (
                "Action sequence:\n"
                + "\n".join(
                    f"{index + 1}. {step}"
                    for index, step in enumerate(action_steps)
                )
                + "\n\nResult:\nCleaning could not be started."
            )
            return False, message

        if shoe.cleaning_status == "clean":
            _, put_down_message = self.put_down(
                object_id=utensil_id,
                new_location="tool_area"
            )
            action_steps.append(put_down_message)
            message = (
                "Action sequence:\n"
                + "\n".join(
                    f"{index + 1}. {step}"
                    for index, step in enumerate(action_steps)
                )
                + f"\n\nResult:\n{shoe_id} is already clean."
            )
            return False, message

        rule = CLEANING_RULES[utensil.utensil_type]
        steps = rule["dirt_specific_steps"].get(
            shoe.dirt_type,
            rule["default_steps"]
        )

        old_cleaning_status = shoe.cleaning_status
        old_dirt_type = shoe.dirt_type
        old_material_status = shoe.material_status
        old_fullness = utensil.fullness_percent

        # Apply the utensil-specific effects to the shoe and utensil
        shoe.cleaning_status = improve_status(
            shoe.cleaning_status,
            CLEANING_LEVELS,
            steps
        )
        if shoe.cleaning_status == "clean":
            shoe.dirt_type = None
        if rule["material_damage"] == "cracked":
            shoe.material_status = "cracked"
        elif rule["material_damage"] == "one_step":
            shoe.material_status = worsen_status(
                shoe.material_status,
                MATERIAL_LEVELS,
                1
            )
        utensil.fullness_percent = max(
            0,
            utensil.fullness_percent - rule["usage_cost"]
        )
        action_steps.append(f"Used {utensil.utensil_type} on {shoe_id}.")

        # Remove empty utensils, otherwise return them to the tool area
        removed_note = ""
        if utensil.fullness_percent == 0:
            del self.cleaning_utensils[utensil_id]
            if self.holding == utensil_id:
                self.holding = None
            self._update_relations()
            removed_note = (
                f"\n{utensil_id} is now empty and was removed "
                "from the world."
            )
        else:
            _, put_down_message = self.put_down(
                object_id=utensil_id,
                new_location="tool_area",
            )
            action_steps.append(put_down_message)

        message = (
            "Action sequence:\n"
            + "\n".join(
                f"{index + 1}. {step}"
                for index, step in enumerate(action_steps)
            )
            + "\n\nResult:\n"
            f"Dirt type: {old_dirt_type} -> {shoe.dirt_type}\n"
            f"Cleaning status: "
            f"{old_cleaning_status} -> {shoe.cleaning_status}\n"
            f"Material status: "
            f"{old_material_status} -> {shoe.material_status}\n"
            f"{utensil_id} fullness: "
            f"{old_fullness}% -> {utensil.fullness_percent}%"
            f"{removed_note}"
        )
        return True, message



    def dry_shoe(self, shoe_id: str) -> Tuple[bool, str]:
        """Dry a shoe by moving it to the drying area.

        Returns:
            A success flag and the executed action steps message.
        """

        if shoe_id not in self.shoes:
            return False, f"Shoe '{shoe_id}' does not exist."
    
        shoe = self.shoes[shoe_id]
        old_dry_status = shoe.dry_status
        if shoe.location == "drying_area":
            return False, (
                f"{shoe_id} is already in the drying area.\n"
                f"Dry status: {shoe.dry_status}\n"
                f"Location: {shoe.location}"
            )
        move_success, move_message = self.move_object(
            object_id=shoe_id,
            new_location="drying_area"
        )
    
        if not move_success:
            return False, move_message + "\nDrying was not performed."
    
        message = (
            move_message
            + "\n\nResult:\n"
            f"{shoe_id} was dried.\n"
            f"Dry status: {old_dry_status} -> {shoe.dry_status}\n"
            f"Location: {shoe.location}"
        )
        return True, message

        
        
    def impregnate_shoe(
        self,
        shoe_id: str,
        utensil_id: str,
    ) -> Tuple[bool, str]:
        """Impregnate a shoe using the specified utensil.

        Apply the utensil-specific protection effect, update the world state.
        Returns:
            A success flag and the executed action steps message.
        """

        if shoe_id not in self.shoes:
            return False, f"Shoe '{shoe_id}' does not exist."
        if utensil_id not in self.impregnation_utensils:
            return False, f"Impregnation utensil '{utensil_id}' does not exist."
    
        shoe = self.shoes[shoe_id]
        utensil = self.impregnation_utensils[utensil_id]
        holding_ok, action_steps = self._ensure_holding(utensil_id)
        if not holding_ok:
            message = (
                "Action sequence:\n"
                + "\n".join(
                    f"{index + 1}. {step}"
                    for index, step in enumerate(action_steps)
                )
                + "\n\nResult:\nImpregnation could not be started."
            )
            return False, message
        if shoe.impregnation_status == "protected":
            _, put_down_message = self.put_down(
                object_id=utensil_id,
                new_location="tool_area",
            )
            action_steps.append(put_down_message)
            message = (
                "Action sequence:\n"
                + "\n".join(
                    f"{index + 1}. {step}"
                    for index, step in enumerate(action_steps)
                )
                + f"\n\nResult:\n{shoe_id} is already protected."
            )
            return False, message
    
        rule = IMPREGNATION_RULES[utensil.utensil_type]
        old_impregnation_status = shoe.impregnation_status
        old_fullness = utensil.fullness_percent
        old_utensil_type = utensil.utensil_type
        steps = rule["steps"]
        wet_note = ""
    
        # Reduce the impregnation effect when the shoe is still wet
        if shoe.dry_status == "wet":
            steps = max(0, steps - 1)
            wet_note = (
                "\nNote: The shoe is wet, so the impregnation "
                "effect was reduced by one step."
            )
    
        shoe.impregnation_status = improve_status(
            shoe.impregnation_status,
            IMPREGNATION_LEVELS,
            steps
        )
        utensil.fullness_percent = max(
            0,
            utensil.fullness_percent - rule["usage_cost"]
        )
        action_steps.append(f"Used {old_utensil_type} on {shoe_id}.")
    
        # Remove an empty utensil, otherwise return it to the tool area
        removed_note = ""
        if utensil.fullness_percent == 0:
            del self.impregnation_utensils[utensil_id]
            if self.holding == utensil_id:
                self.holding = None
            self._update_relations()
            removed_note = (
                f"\n{utensil_id} is now empty and was removed "
                "from the world."
            )
        else:
            _, put_down_message = self.put_down(
                object_id=utensil_id,
                new_location="tool_area",
            )
            action_steps.append(put_down_message)
    
        current_fullness = (
            self.impregnation_utensils[utensil_id].fullness_percent
            if utensil_id in self.impregnation_utensils
            else 0
        )
        message = (
            "Action sequence:\n"
            + "\n".join(
                f"{index + 1}. {step}"
                for index, step in enumerate(action_steps)
            )
            + "\n\nResult:\n"
            f"Impregnation status: "
            f"{old_impregnation_status} -> {shoe.impregnation_status}\n"
            f"{utensil_id} fullness: "
            f"{old_fullness}% -> {current_fullness}%"
            f"{wet_note}"
            f"{removed_note}"
        )
        return True, message


    
    def repair_shoe(
        self,
        shoe_id: str,
        tool_id: str,
        repair_target: str = "both",
    ) -> Tuple[bool, str]:
        """Repair the requested parts of a shoe using the specified tool.

        Update the shoe and tool states and return whether at least one repair
        was applied.
        Returns:
            A success flag and the executed action steps message.
        """
    
        if shoe_id not in self.shoes:
            return False, f"Shoe '{shoe_id}' does not exist."
        if tool_id not in self.repair_tools:
            return False, f"Repair tool '{tool_id}' does not exist."
    
        repair_target = repair_target.lower().strip()
        if repair_target not in {"sole", "material", "both"}:
            return False, f"Unknown repair target: {repair_target}."
    
        shoe = self.shoes[shoe_id]
        tool = self.repair_tools[tool_id]
        holding_ok, action_steps = self._ensure_holding(tool_id)
        if not holding_ok:
            message = (
                "Action sequence:\n"
                + "\n".join(
                    f"{index + 1}. {step}"
                    for index, step in enumerate(action_steps)
                )
                + "\n\nResult:\nRepair could not be started."
            )
            return False, message
    
        old_sole_status = shoe.sole_status
        old_material_status = shoe.material_status
        old_tool_damage = tool.damage_status
        old_tool_type = tool.tool_type
    
        result_notes = []
        repair_applied = False
        removed_note = ""

        # Determine which parts of the shoe should be repaired
        should_repair_sole = repair_target in {"sole", "both"}
        should_repair_material = repair_target in {"material", "both"}
    
        # Repair the sole first because the tool may break before material repair
        if should_repair_sole:
            if shoe.sole_status == "intact":
                result_notes.append("Sole is already intact.")
            elif tool.tool_type not in SOLE_REPAIR_RULES:
                result_notes.append(
                    f"{tool.tool_type} cannot be used for sole repair."
                )
            elif tool.tool_type == "sole_glue" and shoe.dry_status == "wet":
                action_steps.append(
                    f"Used sole_glue on {shoe_id}, but it had no effect."
                )
                result_notes.append(
                    "The shoe is wet, so sole_glue cannot repair the sole."
                )
    
            else:
                rule = SOLE_REPAIR_RULES[tool.tool_type]
                new_sole_status = improve_status(
                    shoe.sole_status,
                    SOLE_LEVELS,
                    rule["steps"]
                )
                if new_sole_status != shoe.sole_status:
                    repair_applied = True
                shoe.sole_status = new_sole_status
                tool.damage_status = min(
                    100,
                    tool.damage_status + rule["tool_damage"]
                )
                action_steps.append(
                    f"Used {old_tool_type} to repair the sole "
                    f"of {shoe_id}."
                )
    
        # Stop if the tool broke during sole repair
        if tool.damage_status >= 100:
            del self.repair_tools[tool_id]
            if self.holding == tool_id:
                self.holding = None
            self._update_relations()
            removed_note = (
                f"\n{tool_id} is now broken and was removed "
                "from the world."
            )
            message = (
                "Action sequence:\n"
                + "\n".join(
                    f"{index + 1}. {step}"
                    for index, step in enumerate(action_steps)
                )
                + "\n\nResult:\n"
                f"Sole status: "
                f"{old_sole_status} -> {shoe.sole_status}\n"
                f"Material status: "
                f"{old_material_status} -> {shoe.material_status}\n"
                f"{tool_id} damage: {old_tool_damage}% -> 100%"
                f"{removed_note}"
            )
            return repair_applied, message
    
        # Repair the material only if requested and the tool is still usable
        if should_repair_material:
            if shoe.material_status == "good":
                result_notes.append("Material is already good.")
            elif tool.tool_type != MATERIAL_REPAIR_TOOL:
                result_notes.append(
                    f"{tool.tool_type} cannot repair material damage. "
                    f"Only {MATERIAL_REPAIR_TOOL} can repair "
                    "material damage."
                )
    
            else:
                steps = MATERIAL_REPAIR_BY_MATERIAL.get(shoe.material)
                if steps is None:
                    result_notes.append(
                        f"Unknown shoe material: {shoe.material}."
                    )
                else:
                    new_material_status = improve_status(
                        shoe.material_status,
                        MATERIAL_LEVELS,
                        steps
                    )
                    if new_material_status != shoe.material_status:
                        repair_applied = True
                    shoe.material_status = new_material_status
                    tool.damage_status = min(
                        100,
                        tool.damage_status
                        + MATERIAL_REPAIR_TOOL_DAMAGE
                    )
                    action_steps.append(
                        f"Used {old_tool_type} to repair the "
                        f"material of {shoe_id}."
                    )
    
        # Remove a broken tool or return it to the tool area
        if tool.damage_status >= 100:
            del self.repair_tools[tool_id]
            if self.holding == tool_id:
                self.holding = None
            self._update_relations()
            removed_note = (
                f"\n{tool_id} is now broken and was removed "
                "from the world."
            )
        else:
            put_down_success, put_down_message = self.put_down(
                object_id=tool_id,
                new_location="tool_area"
            )
            action_steps.append(put_down_message)
            if not put_down_success:
                result_notes.append(
                    f"{tool_id} could not be returned to the tool area."
                )

        notes_text = ""
        if result_notes:
            notes_text = "\n" + "\n".join(result_notes)
        current_tool_damage = (
            self.repair_tools[tool_id].damage_status
            if tool_id in self.repair_tools
            else 100
        )
    
        message = (
            "Action sequence:\n"
            + "\n".join(
                f"{index + 1}. {step}"
                for index, step in enumerate(action_steps)
            )
            + "\n\nResult:\n"
            f"Sole status: "
            f"{old_sole_status} -> {shoe.sole_status}\n"
            f"Material status: "
            f"{old_material_status} -> {shoe.material_status}\n"
            f"{tool_id} damage: "
            f"{old_tool_damage}% -> {current_tool_damage}%"
            f"{notes_text}"
            f"{removed_note}"
        )
        return repair_applied, message



    def get_new_tool_from_infinite_toolbox(
        self,
        tool_class: str,
        tool_type: str,
    ) -> Tuple[bool, str, Optional[str]]:
        """Create a new tool of the requested class and type.

        Place the tool in the tool area and return its generated ID.
        Returns:
            A success flag and the executed action steps message.
        """
    
        if self.holding is not None:
            return (
                False,
                (
                    "Cannot get a new tool from the infinite toolbox. "
                    f"I am already holding {self.holding}."
                ),
                None
            )
        tool_class = tool_class.lower().strip()
        tool_type = tool_type.lower().strip()

        # Create a fully available tool with class-specific initial state
        match tool_class:
            case "cleaning":
                if tool_type not in CLEANING_TOOLS:
                    return (
                        False,
                        f"Unknown cleaning utensil type: {tool_type}.",
                        None
                    )
                new_id = self._make_unique_id(tool_type)
                self.cleaning_utensils[new_id] = CleaningUtensil(
                    utensil_id=new_id,
                    utensil_type=tool_type,
                    fullness_percent=100,
                    location="tool_area"
                )
                label = "cleaning utensil"
    
            case "impregnation":
                if tool_type not in IMPREGNATION_TOOLS:
                    return (
                        False,
                        f"Unknown impregnation utensil type: {tool_type}.",
                        None
                    )
                new_id = self._make_unique_id(tool_type)
                self.impregnation_utensils[new_id] = ImpregnationUtensil(
                    utensil_id=new_id,
                    utensil_type=tool_type,
                    fullness_percent=100,
                    location="tool_area"
                )
                label = "impregnation utensil"
    
            case "repair":
                if tool_type not in REPAIR_TOOLS:
                    return (
                        False,
                        f"Unknown repair tool type: {tool_type}.",
                        None
                    )
                new_id = self._make_unique_id(tool_type)
                self.repair_tools[new_id] = RepairTool(
                    tool_id=new_id,
                    tool_type=tool_type,
                    damage_status=0,
                    location="tool_area"
                )
                label = "repair tool"
    
            case _:
                return (
                    False,
                    (
                        f"Unknown tool class: {tool_class}. "
                        "Use 'cleaning', 'impregnation', or 'repair'."
                    ),
                    None
                )
    
        # Register the new tool in the symbolic relation model
        self._update_relations()

        message = (
            "Action sequence:\n"
            "1. Opened the infinite toolbox.\n"
            f"2. Created a new {label}: {new_id}.\n"
            f"3. Put {new_id} down at tool_area.\n\n"
            f"Result:\n{new_id} is now in the tool_area."
        )
        return True, message, new_id


        
    def go_on_a_walk(
        self,
        shoe_id: str,
        length: str,
        place: str,
        weather: str,
    ) -> Tuple[bool, str]:
        """Use a shoe for a walk and update its condition.

        Apply wear, dirt, and weather effects, then return the shoe to the
        floor box.
        Returns:
            A success flag and the executed action steps message.
        """
        
        length = length.lower().strip()
        place = place.lower().strip()
        weather = weather.lower().strip()
        if shoe_id not in self.shoes:
            return False, f"Shoe '{shoe_id}' does not exist."
        if length not in WALK_LENGTH_STEPS:
            return False, f"Unknown walk length: {length}."
        if place not in WALK_LOCATIONS:
            return False, f"Unknown walk place: {place}."
        if weather not in VALID_WEATHER:
            return False, f"Unknown weather: {weather}."
    
        shoe = self.shoes[shoe_id]
        holding_ok, action_steps = self._ensure_holding(shoe_id)
        if not holding_ok:
            message = (
                "Action sequence:\n"
                + "\n".join(
                    f"{index + 1}. {step}"
                    for index, step in enumerate(action_steps)
                )
                + "\n\nResult:\nCould not start the walk."
            )
            return False, message
    
        old_cleaning_status = shoe.cleaning_status
        old_dirt_type = shoe.dirt_type
        old_sole_status = shoe.sole_status
        old_material_status = shoe.material_status
        old_dry_status = shoe.dry_status
        old_impregnation_status = shoe.impregnation_status
    
        # Apply shoe-specific wear and length-dependent dirt effects
        damage_rule = WALK_DAMAGE_RULES[shoe.shoe_type]
        shoe.sole_status = worsen_status(
            shoe.sole_status,
            SOLE_LEVELS,
            damage_rule["sole"][length],
        )
        shoe.material_status = worsen_status(
            shoe.material_status,
            MATERIAL_LEVELS,
            damage_rule["material"][length],
        )
        shoe.cleaning_status = worsen_status(
            shoe.cleaning_status,
            CLEANING_LEVELS,
            WALK_LENGTH_STEPS[length],
        )
        shoe.dirt_type = WALK_LOCATIONS[place]
    
        # Rain makes the shoe wet and can reduce protection on longer walks
        if weather == "sunny":
            shoe.dry_status = "dry"
        elif weather == "rainy":
            shoe.dry_status = "wet"
            if length in {"medium", "long"}:
                shoe.impregnation_status = worsen_status(
                    shoe.impregnation_status,
                    IMPREGNATION_LEVELS,
                    1
                )
    
        action_steps.append(
            f"Went on a {length} walk with {shoe_id} "
            f"through a {place} in {weather} weather."
        )

        # Return the shoe to its default location after the walk
        put_down_success, put_down_message = self.put_down(
            object_id=shoe_id,
            new_location="floor_box",
        )
        action_steps.append(put_down_message)
    
        if not put_down_success:
            message = (
                "Action sequence:\n"
                + "\n".join(
                    f"{index + 1}. {step}"
                    for index, step in enumerate(action_steps)
                )
                + "\n\nResult:\n"
                "The walk was performed, but the shoe could not "
                "be placed in the floor box."
            )
            return False, message
    
        message = (
            "Action sequence:\n"
            + "\n".join(
                f"{index + 1}. {step}"
                for index, step in enumerate(action_steps)
            )
            + "\n\nResult:\n"
            f"Cleaning status: "
            f"{old_cleaning_status} -> {shoe.cleaning_status}\n"
            f"Dirt type: {old_dirt_type} -> {shoe.dirt_type}\n"
            f"Sole status: "
            f"{old_sole_status} -> {shoe.sole_status}\n"
            f"Material status: "
            f"{old_material_status} -> {shoe.material_status}\n"
            f"Dry status: "
            f"{old_dry_status} -> {shoe.dry_status}\n"
            f"Impregnation status: "
            f"{old_impregnation_status} -> "
            f"{shoe.impregnation_status}\n"
            f"Location: {shoe.location}\n"
            f"Holding: {self.holding}"
        )
        return True, message



    @classmethod
    def create_random(
        cls,
        seed: Optional[int] = None,
        min_shelf_size: int = 1,
        max_shelf_size: int = 10,
    ) -> "World":
        """Create a reproducible random shoe world.

        The same seed produces the same initial world. All shelves receive the
        same random number of slots, and overflow shoes are moved to the floor box.
        """
    
        rng = random.Random(seed)
    
        # Create shelf layout
        shelf_size = rng.randint(min_shelf_size, max_shelf_size)
        shelf_slots: Dict[str, List[Optional[str]]] = {
            "top_shelf": [None] * shelf_size,
            "middle_shelf": [None] * shelf_size,
            "bottom_shelf": [None] * shelf_size,
        }
    
        # Create shoes
        number_of_shoes = rng.randint(2, 2 * shelf_size)
        shoes: Dict[str, Shoe] = {}
        shoe_type_counts: Dict[str, int] = {}
    
        for index in range(2, number_of_shoes + 1):
            cleaning_status = rng.choice(CLEANING_LEVELS)
            # Clean shoes have no dirt type
            dirt_type = (
                None
                if cleaning_status == "clean"
                else rng.choice(sorted(VALID_SOILS))
            )
            
            requested_location = rng.choice(sorted(SHELF_LOCATIONS))
            height = rng.choice(sorted(HEIGHTS))
            # Shoes should only be assigned to locations where its height fits
            if requested_location not in SHOE_HEIGTH_LOCATION_CONSTRAINTS[height]:
                requested_location = "floor_box"
    
            dry_status = rng.choice(sorted(DRY_LEVEL))
            shoe_type=rng.choice(sorted(SHOE_TYPES))
            shoe_type_counts[shoe_type] = shoe_type_counts.get(shoe_type, 0) + 1
            shoe_id = f"{shoe_type}_{shoe_type_counts[shoe_type]}"
    
            shoes[shoe_id] = Shoe(
                shoe_id=shoe_id,
                shoe_type=shoe_type,
                height=height,
                color=rng.choice(sorted(COLORS)),
                material=rng.choice(sorted(MATERIALS)),
                cleaning_status=cleaning_status,
                dirt_type=dirt_type,
                impregnation_status=rng.choice(IMPREGNATION_LEVELS),
                sole_status=rng.choice(SOLE_LEVELS),
                material_status=rng.choice(MATERIAL_LEVELS),
                dry_status=dry_status,
                location=requested_location
            )
    
        # Assign shoes to random shelf slots
        for shelf_name, slots in shelf_slots.items():
            shoe_ids_for_shelf = [
                shoe_id
                for shoe_id, shoe in shoes.items()
                if shoe.location == shelf_name
            ]
            # Randomize which shoes receive the available slots
            rng.shuffle(shoe_ids_for_shelf)
            available_slot_indexes = list(range(len(slots)))
            rng.shuffle(available_slot_indexes)
            number_that_fit = min(
                len(shoe_ids_for_shelf),
                len(available_slot_indexes)
            )
            # Put as many shoes as possible into unique random slots
            for shoe_id, slot_index in zip(
                shoe_ids_for_shelf[:number_that_fit],
                available_slot_indexes[:number_that_fit]
            ):
                slots[slot_index] = shoe_id
            # Overflow shoes are moved into the floor box
            for shoe_id in shoe_ids_for_shelf[number_that_fit:]:
                shoes[shoe_id].location = "floor_box"
    
        # Create cleaning utensils
        cleaning_utensils: Dict[str, CleaningUtensil] = {}
        cleaning_type_counts: Dict[str, int] = {}
        number_of_cleaning_utensils = rng.randint(2, 4)
        for _ in range(number_of_cleaning_utensils):
            utensil_type = rng.choice(sorted(CLEANING_TOOLS))
            cleaning_type_counts[utensil_type] = (
                cleaning_type_counts.get(utensil_type, 0) + 1
            )
            utensil_id =  f"{utensil_type}_{cleaning_type_counts[utensil_type]}"
            cleaning_utensils[utensil_id] = CleaningUtensil(
                utensil_id=utensil_id,
                utensil_type=utensil_type,
                fullness_percent=rng.randint(10, 100),
                location="tool_area"
            )

        # Create impregnation utensils
        impregnation_utensils: Dict[str, ImpregnationUtensil] = {}
        impregnation_type_counts: Dict[str, int] = {}
        number_of_impregnation_utensils = rng.randint(1, 3)
        for _ in range(number_of_impregnation_utensils):
            utensil_type = rng.choice(sorted(IMPREGNATION_TOOLS))
            impregnation_type_counts[utensil_type] = (
                impregnation_type_counts.get(utensil_type, 0) + 1
            )
            utensil_id = f"{utensil_type}_{impregnation_type_counts[utensil_type]}"
            impregnation_utensils[utensil_id] = ImpregnationUtensil(
                utensil_id=utensil_id,
                utensil_type=utensil_type,
                fullness_percent=rng.randint(10, 100),
                location="tool_area"
            )
    

        # Create repair tools
        repair_tools: Dict[str, RepairTool] = {}
        repair_type_counts: Dict[str, int] = {}
        number_of_repair_tools = rng.randint(2, 4)
        for _ in range(number_of_repair_tools):
            tool_type = rng.choice(sorted(REPAIR_TOOLS))
            repair_type_counts[tool_type] = (
                repair_type_counts.get(tool_type, 0) + 1
            )
            tool_id = f"{tool_type}_{repair_type_counts[tool_type]}"
            repair_tools[tool_id] = RepairTool(
                tool_id=tool_id,
                tool_type=tool_type,
                damage_status=rng.randint(0, 90),
                location="tool_area"
            )
    
        # __post_init__ automatically calls _update_relations()
        return cls(
            shoes=shoes,
            cleaning_utensils=cleaning_utensils,
            impregnation_utensils=impregnation_utensils,
            repair_tools=repair_tools,
            shelf_slots=shelf_slots,
            holding=None
        )

