INTENT_CLASSIFICATION_PROMPT = """
    You classify the requested action in a shoe-rack robot world.
    Choose exactly one intent that best matches the user's requested action.
    
    Judge only the requested action:
    - Ignore whether the referenced object exists.
    - Ignore whether the action can succeed.
    - If the command is ambiguous, choose the most plausible intent with low confidence.
    
    Valid intents:
    - PICK_UP: take or pick up an existing object into the hand
    - PUT_DOWN: put down an already held object
    - MOVE: move an object to a destination
    - CLEAN: remove dirt, stains, dust, mud, oil, or improve cleanliness
    - IMPREGNATE: waterproof or protect against water or rain
    - DRY: remove moisture from a wet, soaked, or dripping shoe
    - REPAIR: repair physical damage
    - GET_NEW_TOOL: explicitly request creation or acquisition of a new,
      additional, replacement, fresh, or unused tool
    - GO_ON_WALK: go for a walk or hike using a shoe
    
    EXAMPLE Decision rules:
    - Explicit object states override vague phrases such as "make it better".
    - If a shoe is described as wet, soaked, dripping, or full of water and the user asks to improve or fix that condition, choose DRY.
    - Do not choose CLEAN merely because the user says "make it better", "take care of it", or "improve its condition".
    - CLEAN requires evidence about dirt, stains, washing, wiping, brushing, scrubbing, or appearance-related cleaning.
    - IMPREGNATE requires a request for future water protection, waterproofing, rain resistance, coating, or impregnation.
    
    EXAMPLE Tool rules:
    - PICK_UP means taking an existing tool into the hand.
    - GET_NEW_TOOL requires an explicit indication that a new tool should be obtained or created.
    - Words such as "random", "any", "arbitrary", or "some" select among existing tools and do not mean new.
    - "Pick up a random cleaning tool" is PICK_UP.
    - "Get me a new cleaning tool" is GET_NEW_TOOL.
    - "Use a random tool" does not imply GET_NEW_TOOL.
    
    Additional rules:
    - PICK_UP requires a request to take, grab, hold, or pick up an object.
    - MOVE requires a destination.
    - The reason must be consistent with the selected intent.
    
    User command:
    {command}
    
    Return exactly:
    {{
      "intent": "<one valid intent>",
      "confidence": <number from 0.0 to 1.0>,
      "reason": "<one short sentence explaining why this intent best matches the command>"
    }}
    
    Output only valid JSON.
    """



NO_MATCH_RESOLUTION_PROMPT = """
    You are part of a shoe-rack robot world where users interact with the system using natural language.
    
    The symbolic resolver could not find an object matching the parsed reference.
    Your task is to decide whether one existing object of the required class is still a plausible match.
    
    The parser and symbolic resolver may be incomplete or incorrect.
    Use the full user command as the primary evidence and treat the parsed reference only as supporting information.
    
    Object role being resolved:
    {reference_role}
    
    Required object class:
    {object_class}
    
    Full user command:
    {command}
    
    Parsed symbolic reference:
    {symbolic_ref}
    
    Symbolic resolver result:
    {resolver_message}
    
    Allowed object IDs:
    {allowed_ids}
    
    Current world state:
    {world_state}
    
    Valid values in the shoe world:
    {valid_values}
    
    Rules:
    
    - Select only an ID from the allowed object IDs.
    - Never invent or modify an object ID.
    - The selected object must belong to the required object class.
    - Consider synonyms, paraphrases, and semantically similar attribute values.
    - Consider nested relations in the symbolic reference.
    - Do not blindly trust the parsed symbolic reference.
    - Do not select an object merely because it is the only available object.
    - If several objects are equally plausible, return selected_id as null.
    - If the command is too unspecific, return selected_id as null.
    - If the user explicitly requests a random, arbitrary, or any suitable object, you may select one valid object.
    - If no listed object plausibly matches the command, return selected_id as null.
    
    Use confidence as follows:

    0.90-1.00: 
    - The command clearly identifies one object. All relevant attributes and relations support this object, and no stated constraint contradicts it.
    0.75-0.89: 
    - One object is the most plausible match, but the description contains a minor inconsistency, an unsupported attribute, or incomplete evidence.
    Below 0.75: 
    - The reference is uncertain, contradictory, or insufficiently supported.
   
    If several candidates are equally plausible, do not select one of them solely based on confidence.

    
    Return exactly one JSON object in this format:
    {{
    "selected_id": "<one allowed object ID or null>",
    "confidence": <number between 0.0 and 1.0>,
    "reason": "<one short sentence explaining the decision>"
    }}
    
    If no object is a plausible match, return:
    {{
    "selected_id": null,
    "confidence": 0.0,
    "reason": "No listed object is a plausible match."
    }}
    
    Output only valid JSON.
    """

AMBIGUOUS_OBJECT_RESOLUTION_PROMPT = """
    You are part of a shoe-rack robot world where users interact with the system using natural language.
    
    The symbolic resolver found multiple possible objects.
    Your task is to decide whether the full user command contains enough information to select exactly one candidate.
    
    The parser and symbolic resolver may be incomplete or incorrect.
    Use the full user command as the primary evidence and treat the parsed reference only as supporting information.
    
    Object role being resolved:
    {reference_role}
    
    Required object class:
    {object_class}
    
    Full user command:
    {command}
    
    Parsed symbolic reference:
    {symbolic_ref}
    
    Symbolic resolver result:
    {resolver_message}
    
    Allowed candidate IDs:
    {allowed_ids}
    
    Candidate objects:
    {candidate_objects}
    
    Current world state:
    {world_state}
    
    Valid values in the shoe world:
    {valid_values}
    
    Rules:
    - Select only one ID from the allowed candidate IDs.
    - Never invent or modify an object ID.
    - Never select an object outside the candidate list.
    - Use information from the full command that may not be represented correctly in the symbolic reference.
    - Do not select a candidate merely because it appears first in the list.
    - If several candidates remain equally plausible, return selected_id as null.
    - If the command is too unspecific, return selected_id as null.
    - If the user explicitly requests a random, arbitrary, or any suitable object, you may select one candidate from the list.
    
    Use confidence as follows:

    0.90-1.00: 
    - The command clearly identifies one object. All relevant attributes and relations support this object, and no stated constraint contradicts it.
    0.75-0.89: 
    - One object is the most plausible match, but the description contains a minor inconsistency, an unsupported attribute, or incomplete evidence.
    Below 0.75: 
    - The reference is uncertain, contradictory, or insufficiently supported.
    
    If several candidates are equally plausible, do not select one of them solely based on confidence. Return the result as ambiguous.
    
    
    Return exactly one JSON object in this format:
    {{
    "selected_id": "<one allowed candidate ID or null>",
    "confidence": <number between 0.0 and 1.0>,
    "reason": "<one short sentence explaining the decision>"
    }}
    
    If the command remains ambiguous, return:
    {{
    "selected_id": null,
    "confidence": 0.0,
    "reason": "The command is still ambiguous between the candidate objects."
    }}
    
    Output only valid JSON.
    """



GENERIC_OBJECT_RESOLUTION_PROMPT = """
    You are part of a shoe-rack robot world where users interact with the system using natural language.
    
    The symbolic resolver could not determine the object class or resolve one unique object.
    Your task is to identify whether one existing object in the current world is the intended object.
    
    The parser and symbolic resolver may be incomplete or incorrect.
    Use the full user command as the primary evidence and treat the parsed reference only as supporting information.
    
    Object role being resolved:
    {reference_role}
    
    Full user command:
    {command}
    
    Parsed symbolic reference:
    {symbolic_ref}
    
    Symbolic resolver result:
    {resolver_message}
    
    Allowed object IDs:
    {allowed_ids}
    
    Allowed objects:
    {allowed_objects}
    
    Current world state:
    {world_state}
    
    Valid values in the shoe world:
    {valid_values}
    
    Rules:
    - Select only one ID from the allowed object IDs.
    - Never invent or modify an object ID.
    - Use the object role to distinguish between multiple objects mentioned in the command.
    - Consider object attributes, locations, and next-to relations.
    - Do not blindly trust the parsed symbolic reference.
    - Do not select an object merely because it is the only object of its class.
    - If several objects are equally plausible, return selected_id as null.
    - If the command is too unspecific, return selected_id as null.
    - If the user explicitly requests a random, arbitrary, or any suitable object, you may select one allowed object.
    
    Use confidence as follows:

    0.90-1.00: 
    - The command clearly identifies one object. All relevant attributes and relations support this object, and no stated constraint contradicts it.
    0.75-0.89: 
    - One object is the most plausible match, but the description contains a minor inconsistency, an unsupported attribute, or incomplete evidence.
    Below 0.75: 
    - The reference is uncertain, contradictory, or insufficiently supported.
   
    If several candidates are equally plausible, do not select one of them solely based on confidence.
    - below 0.75: the result is uncertain.
    
    Return exactly one JSON object in this format:
    {{
    "selected_id": "<one allowed object ID or null>",
    "confidence": <number between 0.0 and 1.0>,
    "reason": "<one short sentence explaining the decision>"
    }}
    
    If no object is a plausible match, return:
    {{
    "selected_id": null,
    "confidence": 0.0,
    "reason": "No allowed object is a plausible match."
    }}
    
    Output only valid JSON.
    """
