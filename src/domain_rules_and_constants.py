"""Defines domain constants, action rules, and alias maps for the shoe world.

The constants in this module describe valid world values, ordered status levels,
rule dictionaries for actions, and aliases used to normalize user input.
"""

# ----------------------------------------
# Ordered status levels
# ----------------------------------------
# The order matters: lower indexes are better, higher indexes are worse.

CLEANING_LEVELS = ["clean", "a_little_dirty", "medium_dirty","dirty", "very_dirty"]
MATERIAL_LEVELS = ["good", "scratched", "cracked"]
IMPREGNATION_LEVELS = ["protected", "partly_protected", "unprotected"]
SOLE_LEVELS = ["intact", "worn", "loose", "damaged"]


# ----------------------------------------
# Action rules
# ----------------------------------------
# These dictionaries define how actions change object states.
# "steps" values are used with improve_status() or worsen_status().
# "usage_cost" reduces utensil fullness, and "tool_damage" increases repair tool damage.

# Allowed locations by shoe height
SHOE_HEIGTH_LOCATION_CONSTRAINTS = {
            "high": ["floor_box", "bottom_shelf", "drying_area", "hand"],
            "mid": ["floor_box", "middle_shelf", "bottom_shelf", "drying_area", "hand"],
            "low": ["floor_box", "bottom_shelf", "middle_shelf", "top_shelf", "drying_area", "hand"]
}

# Cleaning effectiveness and utensil usage
CLEANING_RULES = {
    "cleaner": {
        "default_steps": 4,
        "dirt_specific_steps": {},
        "material_damage": "cracked",
        "usage_cost": 5
    },
    "rag": {
        "default_steps": 1,
        "dirt_specific_steps": {
            "mud": 2,
            "oil": 2
        },
        "material_damage": None,
        "usage_cost": 3
    },
    "brush": {
        "default_steps": 1,
        "dirt_specific_steps": {
            "grass": 3,
            "sand": 3,
            "dust": 3,
            "mud": 1,
            "oil": 1
        },
        "material_damage": "one_step",
        "usage_cost": 2
    }
}

IMPREGNATION_RULES = {
    "spray": {
        "steps": 1,
        "usage_cost": 5
    },
    "cream": {
        "steps": 2,
        "usage_cost": 10
    }
}

# Sole improvement and tool damage
SOLE_REPAIR_RULES = {
    "needle_and_yarn": {
        "steps": 1,
        "tool_damage": 10
    },
    "sole_glue": {
        "steps": 2,
        "tool_damage": 5
    },
    "sole_hammer": {
        "steps": 3,
        "tool_damage": 1
    }
}
MATERIAL_REPAIR_BY_MATERIAL = {
    "leather": 3,
    "suede": 2,
    "rubber": 2,
    "canvas": 1
}
MATERIAL_REPAIR_TOOL = "needle_and_yarn"
MATERIAL_REPAIR_TOOL_DAMAGE = 5

# Dirt type by walk location
WALK_LOCATIONS = {
    "park": "grass",
    "beach": "sand",
    "forest": "mud",
    "street": "dust",
    "city": "dust",
    "playground": "sand",
    "meadow": "grass",
    "field": "grass",
    "garden": "grass",
    "garage": "oil",
    "workshop": "oil",
    "parking_lot": "oil",
    "construction_site": "dust",
    "trail": "mud"
}

# Status deterioration by walk length
WALK_LENGTH_STEPS = {
    "short": 1,
    "medium": 2,
    "long": 3
}

# Material/Sole damage by shoe type
WALK_DAMAGE_RULES = {
    "sandal": {
        "sole": {
            "short": 2,
            "medium": 3,
            "long": 3,
        },
        "material": {
            "short": 0,
            "medium": 1,
            "long": 2
        }
    },
    "sneaker": {
        "sole": {
            "short": 1,
            "medium": 2,
            "long": 3,
        },
        "material": {
            "short": 0,
            "medium": 1,
            "long": 2
        }
    },
    "boot": {
        "sole": {
            "short": 0,
            "medium": 0,
            "long": 1
        },
        "material": {
            "short": 0,
            "medium": 1,
            "long": 1
        }
    }
}


# ----------------------------------------
# Valid world values
# ----------------------------------------
# These sets define canonical values accepted by the world and parser.

SHELF_LOCATIONS = {"top_shelf", "middle_shelf", "bottom_shelf"}
VALID_SHOE_LOCATIONS = SHELF_LOCATIONS | {"floor_box", "drying_area", "hand"}
VALID_LOCATIONS = VALID_SHOE_LOCATIONS | {"tool_area"}
VALID_SOILS = {"mud", "dust", "sand", "grass", "oil"}
VALID_WEATHER = {"sunny", "rainy"}
COLORS = {"red", "green", "blue", "yellow", "black", "white", "brown"}
DRY_LEVEL ={"dry", "wet"}
VALID_OBJECT_CLASSES = {"shoe", "cleaning_utensil", "impregnation_utensil", "repair_tool"}
VALID_INTENTS = {"PICK_UP", "PUT_DOWN", "MOVE", "CLEAN", "IMPREGNATE", "DRY", "REPAIR", "GET_NEW_TOOL", "GO_ON_WALK"}


# ----------------------------------------
# Derived valid values
# ----------------------------------------
# These sets are generated from the rule dictionaries above so that valid
# values mainly need to be maintained in one place.

HEIGHTS = set(SHOE_HEIGTH_LOCATION_CONSTRAINTS.keys())
SHOE_TYPES = set(WALK_DAMAGE_RULES.keys())
MATERIALS = set(MATERIAL_REPAIR_BY_MATERIAL.keys())
CLEANING_TOOLS = set(CLEANING_RULES.keys())
IMPREGNATION_TOOLS = set(IMPREGNATION_RULES.keys())
REPAIR_TOOLS = set(SOLE_REPAIR_RULES.keys()) | {MATERIAL_REPAIR_TOOL}
ALL_TOOLS = CLEANING_TOOLS | IMPREGNATION_TOOLS | REPAIR_TOOLS
WALK_LENGTHS = set(WALK_LENGTH_STEPS.keys())
WALK_PLACES = set(WALK_LOCATIONS.keys())


# ----------------------------------------
# Alias maps for language normalization
# ----------------------------------------
# Alias maps translate user-friendly words into canonical world values.
# Each map also contains identity aliases, so canonical values are accepted too.

def identity_aliases(values):
    """Map every canonical value to itself for use in alias dictionaries."""
    
    return {value: value for value in values}


SHOE_TYPE_ALIASES = {
    **identity_aliases(SHOE_TYPES),
    "sneakers": "sneaker",
    "trainer": "sneaker",
    "trainers": "sneaker",
    "running_shoe": "sneaker",
    "running_shoes": "sneaker",
    "boots": "boot",
    "sandals": "sandal"
}

COLOR_ALIASES = {
    **identity_aliases(COLORS),
    "tan": "brown",
    "beige": "brown",
    "navy": "blue",
    "dark_blue": "blue",
    "light_blue": "blue"
}

HEIGHT_ALIASES = {
    **identity_aliases(HEIGHTS),
    "small": "low",
    "tall": "high"
}

MATERIAL_ALIASES = {
    **identity_aliases(MATERIALS),
    "fabric": "canvas",
    "cloth": "canvas"
}

CLEANING_STATUS_ALIASES = {
    **identity_aliases(CLEANING_LEVELS),
    "spotless": "clean",
    "slightly_dirty": "a_little_dirty",
    "little_dirty": "a_little_dirty",
    "somewhat_dirty": "medium_dirty",
    "moderately_dirty": "medium_dirty",
    "filthy": "very_dirty",
    "really_dirty": "very_dirty",
    "extremely_dirty": "very_dirty"
}

MATERIAL_STATUS_ALIASES = {
    **identity_aliases(MATERIAL_LEVELS),
    "okay": "good",
    "fine": "good",
    "cracking": "cracked"
}

IMPREGNATION_STATUS_ALIASES = {
    **identity_aliases(IMPREGNATION_LEVELS),
    "waterproof": "protected",
    "waterproofed": "protected",
    "partially_protected": "partly_protected",
    "not_protected": "unprotected",
    "not_waterproof": "unprotected"
}

SOLE_STATUS_ALIASES = {
    **identity_aliases(SOLE_LEVELS),
    "okay": "intact",
    "fine": "intact",
    "undamaged": "intact",
    "used": "worn",
    "unstable": "loose",
    "broken": "damaged"
}

DRY_STATUS_ALIASES = {
    **identity_aliases(DRY_LEVEL),
    "damp": "wet",
    "soaked": "wet"
}

DIRT_TYPE_ALIASES = {
    **identity_aliases(VALID_SOILS),
    "muddy": "mud",
    "dusty": "dust",
    "sandy": "sand",
    "grassy": "grass",
    "oily": "oil"
}

COMMON_LOCATION_ALIASES = {
    "top": "top_shelf",
    "upper_shelf": "top_shelf",
    "middle": "middle_shelf",
    "center_shelf": "middle_shelf",
    "bottom": "bottom_shelf",
    "lower_shelf": "bottom_shelf",
    "ground": "floor_box",
    "floor": "floor_box",
    "drying_spot": "drying_area",
    "drying_corner": "drying_area",
    "in_hand": "hand"
}
SHOE_LOCATION_ALIASES = {
    **identity_aliases(VALID_SHOE_LOCATIONS),
    **COMMON_LOCATION_ALIASES
}
LOCATION_ALIASES = {
    **identity_aliases(VALID_LOCATIONS),
    **COMMON_LOCATION_ALIASES,
    "tool_zone": "tool_area",
    "tool_box": "tool_area"
}

CLEANING_TOOL_ALIASES = {
    **identity_aliases(CLEANING_TOOLS),
    "cloth": "rag",
    "towel": "rag",
    "cleaning_cloth": "rag",
    "cleaning_liquid": "cleaner",
    "shoe_cleaner": "cleaner"
}

IMPREGNATION_TOOL_ALIASES = {
    **identity_aliases(IMPREGNATION_TOOLS),
    "waterproofing_spray": "spray",
    "protector_spray": "spray",
    "shoe_cream": "cream",
    "wax": "cream"
}

REPAIR_TOOL_ALIASES = {
    **identity_aliases(REPAIR_TOOLS),
    "needle": "needle_and_yarn",
    "yarn": "needle_and_yarn",
    "thread": "needle_and_yarn",
    "glue": "sole_glue",
    "hammer": "sole_hammer"
}

REPAIR_PART_ALIASES = {
    "material": "material",
    "fabric": "material",
    "surface": "material",
    "upper": "material",
    "sole": "sole",
    "underside": "sole"
}

WALK_LENGTH_ALIASES = {
    **identity_aliases(WALK_LENGTHS),
    "brief": "short",
    "quick": "short",
    "fast": "short",
    "normal": "medium",
    "regular": "medium",
    "far": "long",
    "extended": "long"
}

WALK_PLACE_ALIASES = {
    **identity_aliases(WALK_PLACES),
    "road": "street",
    "sidewalk": "street",
    "woods": "forest",
    "seaside": "beach",
    "yard": "garden"
}

WEATHER_ALIASES = {
    **identity_aliases(VALID_WEATHER),
    "sunny_weather": "sunny",
    "rainy_weather": "rainy",
    "sun": "sunny",
    "dry_weather": "sunny",
    "nice_weather": "sunny",
    "rain": "rainy",
    "wet_weather": "rainy",
    "stormy": "rainy",
    "stormy_weather": "rainy"
}

SHOE_CLASS_ALIASES = {
    "shoe":"shoe",
    "shoes":"shoe"
}

CLEANING_UTENSIL_CLASS_ALIASES = {
    "cleaning_utensil":"cleaning_utensil",
    "cleaning_tool":"cleaning_utensil",
    "cleaning_tools":"cleaning_utensil",
    "cleaning_utensils":"cleaning_utensil"
}

IMPREGNATION_UTENSIL_CLASS_ALIASES = {
    "impregnation_utensil":"impregnation_utensil",
    "impregnation_utensils":"impregnation_utensil",
    "impregnation_tools":"impregnation_utensil",
    "impregnation_utensils":"impregnation_utensil"
}

REPAIR_TOOL_CLASS_ALIASES = {
    "repair_tool":"repair_tool",
    "repair_tools":"repair_tool",
    "repair_utensils":"repair_tool",
    "repair_utensil":"repair_tool"
}
