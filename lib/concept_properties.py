occurence_pulldown_properties_dict = {
    'notation_options': {
        'all': [
            ['bold','Bold'],
            ['italic','Italic'],
            ['bold italic', 'Bold Italic'],
            ['calligraphic','Calligraphic']
        ]
    },
    'applied_operator_options': {
        'all': [],
        'rank0': [],
        'rank124': [
            ['transpose','Transpose']
        ]
    }
}

occurence_check_properties_dict = {
    'all': [],
    'rank24': [['occurence-option-voigt', 'Voigt notation']]
}

concept_pulldown_properties_dict = {
    'test_trial': {
        'all': [
            ['trial-function', 'Trial Function'],
            ['test-function', 'Test Function'],
            ['nodal-variable', 'Nodal Variable'],
            ['symbolic-variable', 'Symbolic Variable'],
            ['numerical-variable', 'Numerical Variable'],
            ['undefined-function', 'Undefined Function'],
            ['defined-function', 'Defined Function'],
            ['operator', 'Operator'],
            ['domain', 'Domain'],
            ['integration-var', 'Integration var.'],
            ['other', 'Other']
        ]
    }
}

concept_check_properties_dict = {
    'all': [],
    'rank0': [
        ['concept-option-positive','Positive']
    ],
    'rank124': [
        ['concept-option-symmetric','Symmetric']
    ]
}

def construct_pulldown_node(properties_dict: dict[list[list[str]]], li_node_name: str,
                            categories: list[str], previous_options: list[str]) -> str:
    full_options_list = properties_dict['all'].copy()
    for cat in categories:
        full_options_list += properties_dict.get(cat, [])
    
    out_html = f'<ol><li><select name="{li_node_name}">\n<option value="">-----</option>\n'
    for opt in full_options_list:
        checked_option = ' selected' if opt[0] in previous_options else ''
        out_html += f'<option value="{opt[0]}"{checked_option}>{opt[1]}</option>\n'
    out_html += '</select></li></ol>\n'
    
    return out_html

def construct_checkbox_list_node(properties_dict: dict[list[list[str]]],
                            categories: list[str], previous_options: list[str]) -> str:
    full_options_list = properties_dict['all'].copy()
    for cat in categories:
        full_options_list += properties_dict.get(cat, [])
    out_html = f'<p>\n'
    for opt in full_options_list:
        checked_option = ' checked' if opt[0] in previous_options else ''
        out_html += f'<label for="{opt[0]}"><input type="checkbox" id="{opt[0]}"{checked_option}>{opt[1]}</label>\n'
    out_html += '</p>\n' 

    return out_html


def build_occurence_properties_options_html(tensor_rank: int, previous_options: list[str]) -> str:
    out_html = ''

    # For pulldown properties
    for pulldown_dict_name, pulldown_dict in occurence_pulldown_properties_dict.items():
        relevant_categories = []
        for category_name in pulldown_dict.keys():
            # Get relevant categories based on tensor rank
            if 'rank' in category_name and str(tensor_rank) in category_name:
                relevant_categories.append(category_name)
        out_html += construct_pulldown_node(
            occurence_pulldown_properties_dict[pulldown_dict_name],
            pulldown_dict_name,
            relevant_categories,
            previous_options
        )

    # For checkbox properties
    relevant_checkbox_categories = []
    for category_name in occurence_check_properties_dict.keys():
        # Get relevant categories based on tensor rank
        if 'rank' in category_name and str(tensor_rank) in category_name:
            relevant_checkbox_categories.append(category_name)
    out_html += construct_checkbox_list_node(
        occurence_check_properties_dict,
        relevant_checkbox_categories,
        previous_options
    )
    
    return out_html
    

def build_concept_properties_options_html(tensor_rank: int, previous_options: list[str]) -> str:
    out_html = ''

    # For pulldown properties
    for pulldown_dict_name, pulldown_dict in concept_pulldown_properties_dict.items():
        relevant_categories = []
        for category_name in pulldown_dict.keys():
            # Get relevant categories based on tensor rank
            if 'rank' in category_name and str(tensor_rank) in category_name:
                relevant_categories.append(category_name)
        out_html += construct_pulldown_node(
            concept_pulldown_properties_dict[pulldown_dict_name],
            pulldown_dict_name,
            relevant_categories,
            previous_options
        )

    # For checkbox properties
    relevant_checkbox_categories = []
    for category_name in concept_check_properties_dict.keys():
        # Get relevant categories based on tensor rank
        if 'rank' in category_name and str(tensor_rank) in category_name:
            relevant_checkbox_categories.append(category_name)
    out_html += construct_checkbox_list_node(
        concept_check_properties_dict,
        relevant_checkbox_categories,
        previous_options
    )
    
    return out_html
    