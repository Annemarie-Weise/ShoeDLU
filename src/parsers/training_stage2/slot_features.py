"""Defines tokenization and feature extraction helpers for building and using 
the slot tagger.

The functions in this module convert command sentences into token-level feature
dictionaries used by the CRF slot-tagging model during training and prediction.
"""

from typing import Any, Dict, List


def tokenize_text(text: str) -> List[str]:
    """Lowercase text and split it into cleaned word tokens."""

    normalized = text.lower().strip()
    return [
        token.strip(".,!?;:")
        for token in normalized.split()
        if token.strip(".,!?;:")
    ]



def token_to_features(tokens: List[str], index: int, intent: str) -> Dict[str, Any]:
    """Build CRF feature values for one token in a command sentence."""

    token = tokens[index].strip(".,!?;:")
    token_lower = token.lower()

    features = {
        # Current token features
        "bias": 1.0,  # Always-on feature that helps the model learn common default labels such as O
        "token.lower": token_lower,
        "token.isdigit": token.isdigit(),  # Useful for damage and fullness percentages
        "token.has_digit": any(character.isdigit() for character in token),  # Useful for object IDs
        "token.has_underscore": "_" in token,  # Structured concepts can contain underscores, e.g. tool_area
        "token.prefix3": token_lower[:3],
        "token.suffix2": token_lower[-2:],  # Useful for endings such as -ed
        "token.suffix3": token_lower[-3:],  # Useful for endings such as -ing
        "intent": intent  # Intent is used as context for slot tagging
    }

    # Previous token features give the model left-side context
    if index > 0:
        previous_token = tokens[index - 1]
        previous_token_lower = previous_token.lower()
        features.update({
            "-1:token.lower": previous_token_lower,
            "-1:token.isdigit": previous_token.isdigit(),
            "-1:token.has_digit": any(character.isdigit() for character in previous_token),
            "-1:token.has_underscore": "_" in previous_token,
        })
    else:
        features["BOS"] = True

    # Next token features give the model right-side context
    if index < len(tokens) - 1:
        next_token = tokens[index + 1]
        next_token_lower = next_token.lower()
        features.update({
            "+1:token.lower": next_token_lower,
            "+1:token.isdigit": next_token.isdigit(),
            "+1:token.has_digit": any(character.isdigit() for character in next_token),
            "+1:token.has_underscore": "_" in next_token,
        })
    else:
        features["EOS"] = True

    return features



def sentence_to_features(sentence: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert a sentence dictionary into CRF features for all tokens."""
    
    tokens = sentence["tokens"]
    intent = sentence["intent"]
    
    return [
        token_to_features(tokens, index, intent)
        for index in range(len(tokens))
    ]
