from json_logic import jsonLogic
from typing import Dict

def validate_properties(fields_config: Dict, properties: Dict[str, str]):
    """
    Returns (True, None) if valid, or (False, error_message) if invalid.
    """

    # Check each field defined in the taxonomy
    # Note: Your JSON structure used 'concept_fields' based on our previous step
    for field_id, field_info in fields_config.items():
        rule = field_info.get('display_rule')
        
        # If the rule is a boolean (True/False), it's always valid/invalid
        if isinstance(rule, bool):
            is_allowed = rule
        elif rule:
            # Run the JSON-Logic engine! 
            # It compares the rule against the whole submitted_data object
            is_allowed = jsonLogic(rule, properties)
        else:
            is_allowed = True # No rule means it's always allowed

        # If the field has data but the logic says it shouldn't be visible/active
        if not is_allowed and field_id in properties:
            # You can either delete the extra data or return an error
            return False, f"Field '{field_id}' is not allowed for the current configuration."

    return True, None