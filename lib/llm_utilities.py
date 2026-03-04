import json
from copy import deepcopy
from dataclasses import asdict
import requests
from typing import Dict
from pathlib import Path

from lxml import etree
from pydantic import ValidationError
from openai import OpenAI

from lib.datatypes import MathConcept, Group
from lib.util import generate_group_info_from_mi_ids, get_group_primitive_hex_set, get_comp_tag_primitive_hex_set

# Get OpenAI's API key and API base to use vLLM's API server.
with open("config.json", "r") as config_file:
    config=json.load(config_file)
    openai_api_key = config["OPENAI_API_KEY"]
    openai_api_base = config["OPENAI_API_BASE"]
    max_context_length = config["MAX_CONTEXT_LENGTH"]

client = OpenAI(
    api_key=openai_api_key,
    base_url=openai_api_base,
)

def get_running_model_name():
    """
    Asks the vLLM server which model it is currently serving.
    Returns: The model ID string (e.g., 'meta-llama/Meta-Llama-3-8B-Instruct')
    """
    try:
        # Standard OpenAI endpoint to list models
        models = client.models.list()
        
        # vLLM usually serves just one model, so we take the first one.
        # If multiple are loaded (rare in vLLM), you might need logic to pick one.
        first_model = models.data[0].id
        return first_model
    except Exception as e:
        print(f"Error fetching model name: {e}")
        return None
    
def check_token_usage(messages):
    """
    Queries the vLLM server to get token count and context limit.
    Returns: (num_tokens, max_model_len)
    """
    # vLLM exposes this at the root /tokenize, not /v1/tokenize
    # If your base_url is http://localhost:8000/v1, strip the /v1
    base_url = str(client.base_url).replace("/v1", "").replace("/v1/", "")
    url = f"{base_url}/tokenize"
    
    model_name = get_running_model_name()
    payload = {
        "model": model_name,
        "messages": messages  # Pass the same messages list you would send to chat.completions
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        
        # vLLM returns 'count' (tokens) and 'max_model_len' (context limit)
        return data["count"], data["max_model_len"]
        
    except requests.exceptions.RequestException as e:
        print(f"Error checking tokens: {e}")
        return None, None

def send_message_to_llm(messages: list[Dict[str,str]]):
    tokens_count, max_model_len = check_token_usage(messages)
    max_token_len = min(max_context_length,max_model_len)
    if tokens_count >= max_token_len:
        raise(f"Token count for prompt ({tokens_count}) is higher than allowed ({max_token_len})")
    return client.chat.completions.create(
        model=get_running_model_name(),
        messages=messages
    )

def validate_llm_output_schema(raw_data, ExpectedSchema):
    try:
        # This will attempt to parse and validate the dictionary
        validated_data = ExpectedSchema(**raw_data)
        return True, validated_data.model_dump()
    except ValidationError as e:
        # Generate a human-readable error response
        return False, e.errors()
    
def get_or_create_llm_log_file(paper_id):
    output_log_file_path = Path(f"./data/{paper_id}/{paper_id}_llm_log.json")
    if not output_log_file_path.parent.exists():
        raise "Directory specified for LLM log does not exist"
    if not output_log_file_path.exists():
        with open(output_log_file_path, 'w') as file:
            init_dict = {
                "paper_id": paper_id
            }
            json.dump(init_dict, file)
    return output_log_file_path

def get_local_name(tag):
    """
    Extracts the tag name without the namespace.
    E.g., '{http://www.w3.org/1998/Math/MathML}mi' -> 'mi'
    """
    # Safety check: comments/PIs in lxml have non-string tags
    if not isinstance(tag, str): 
        return ""
    return etree.QName(tag).localname

def strip_pattern_mrows(node):
    """
    Recursively simplifies the XML tree by removing <mrow> tags 
    that have exactly one child. Returns the new effective root.
    """
    # 1. Unwrap the current node if it is itself a redundant mrow
    # We do this in a loop to catch nested wrappers like <mrow><mrow>...
    while get_local_name(node.tag) == 'mrow' and len(node) == 1:
        node = node[0]

    # 2. Recursively process and replace children
    # We iterate over a list(node) because we might modify the tree during iteration
    for child in list(node):
        new_child = strip_pattern_mrows(child)
        
        # If the child was unwrapped, replace the old element with the new one
        if new_child is not child:
            node.replace(child, new_child)
            
    return node

def get_effective_node(node):
    """
    Recursively drills down through single-child <mrow> wrappers.
    """
    # We use get_local_name so we catch <m:mrow>, <mrow>, etc.
    while node is not None and get_local_name(node.tag) == 'mrow' and len(node) == 1:
        node = node[0]
    return node

def elements_match(pattern, target):
    """
    Recursively checks if target matches pattern (subset logic).
    """
    # 1. Unwrap the target (ignore mrows)
    effective_target = get_effective_node(target)
    
    # If unwrap failed or node is not an element (e.g. comment), fail
    if effective_target is None or not isinstance(effective_target.tag, str):
        return False

    # 2. Check Tag Name (Namespace Agnostic)
    if get_local_name(pattern.tag) != get_local_name(effective_target.tag):
        return False

    # 3. Check Text Content
    # We strip whitespace to handle formatting differences
    p_text = (pattern.text or "").strip()
    t_text = (effective_target.text or "").strip()
    if p_text != t_text:
        return False

    # 4. Check Attributes (Subset Logic)
    # We check if pattern attributes exist in target.
    # Note: This simple check assumes attributes in pattern are NOT namespaced.
    for key, value in pattern.attrib.items():
        if effective_target.get(key) != value:
            return False

    # 5. Check Children Structure
    # lxml elements are iterable
    if len(pattern) != len(effective_target):
        return False

    for p_child, t_child in zip(pattern, effective_target):
        if not elements_match(p_child, t_child):
            return False

    return True

def find_mathml_occurrences(target_xml_str, pattern_xml_fragment):
    parser = etree.XMLParser(remove_blank_text=True)
    
    # 1. Parse Pattern (Wrap in dummy root because it might have multiple siblings)
    try:
        # We wrap in <root> to handle "<a>...</a> <b>...</b>"
        raw_pattern = etree.fromstring(f"<root>{pattern_xml_fragment}</root>", parser)
        # Clean the pattern (remove mrows)
        clean_pattern_root = strip_pattern_mrows(raw_pattern)
        # The actual pattern is the LIST of children
        pattern_sequence = list(clean_pattern_root)
    except etree.XMLSyntaxError:
        print("Error parsing pattern.")
        return []

    # 2. Parse Target
    try:
        target_root = etree.fromstring(f"<root>{target_xml_str}</root>", parser)
        target_root = strip_pattern_mrows(target_root)
    except etree.XMLSyntaxError:
        print("Error parsing target.")
        return []

    matches = []
    
    # If pattern is empty, nothing to match
    if not pattern_sequence:
        return []

    # 3. Traverse every node in target to check its children
    for parent in target_root.iter():
        children = list(parent)
        
        # We need at least as many children as there are pattern elements
        if len(children) < len(pattern_sequence):
            continue

        # Sliding Window Search
        # We stop when the remaining children are fewer than the pattern length
        for i in range(len(children) - len(pattern_sequence) + 1):
            
            # Optimization: Check first element before looping through the rest
            if elements_match(pattern_sequence[0], children[i]):
                
                # Potential match found, check the rest of the sequence
                full_match = True
                current_match_nodes = []
                
                for j, pattern_node in enumerate(pattern_sequence):
                    target_candidate = children[i + j]
                    
                    if not elements_match(pattern_node, target_candidate):
                        full_match = False
                        break
                    
                    # Store the "effective" node (the real content, not the wrapper)
                    current_match_nodes.append(get_effective_node(target_candidate))
                
                if full_match:
                    matches.append(current_match_nodes)

    return matches

def find_first_match_info(root):
    # Define the tags we care about (ignoring namespaces later)
    with open("config.json", "r") as config_file:
        config=json.load(config_file)
    target_tags = config['COMPOUND_CONCEPT_TAGS']
    target_tags.append("mi")

    # 1. Iterate over elements in document order (Depth First)
    for node in root.iter():
        # Get local name to ignore namespaces (e.g., match 'mi' and 'm:mi')
        local_tag = get_local_name(node.tag)
        if local_tag in target_tags:
            # 2. Match Found! Get the ID.
            found_id = node.get('id', None)

            # 3. Calculate Depth
            # We walk up the parents until we hit the root element
            depth = 0
            curr = node
            while curr != root:
                curr = curr.getparent()
                depth += 1
            
            # Return the result immediately
            return {
                "tag_name": local_tag,
                "id": found_id,
                "depth": depth,
                "element": node
            }

    return None # No match found

def get_all_ids_as_set(root_element):
    """
    Extracts all 'id' attributes from an lxml element tree 
    and returns them as a Python set.
    """
    # //@id selects all id attributes anywhere in the tree
    return set(root_element.xpath('.//@id'))

def find_relationships_through_contained_ids(symbols_info_list):

    # 1. Sort by number of IDs (smallest first)
    # This helps us prune: we only check against trees that are equal or larger
    symbols_info_list.sort(key=lambda x: x['ids_count'])
    
    matches = []
    
    # 2. Compare efficiently
    for i, child in enumerate(symbols_info_list):
        # We only need to check trees that come AFTER the current one in the sorted list
        # (or define your own range if relationships can be bidirectional or unordered)
        for parent in symbols_info_list[i+1:]:
            
            # Optimization: If parent has same ID count, they might be identical
            # If parent has more, it might be a superset.
            
            if child['ids_set'].issubset(parent['ids_set']):
                matches.append({
                    "parent_variable_name": parent['variable_name'],
                    "parent_representative_id": parent['representative_id'],
                    "parent_mathml": parent['mathml'],
                    "child_variable_name": child['variable_name'],
                    "child_representative_id": child['representative_id'],
                    "child_mathml": child['mathml']
                })
    return matches

def get_primitive_hex_set(elem, html_tree_raw):
    hex_set = set()
    mi_elements = elem.xpath("descendant-or-self::*[local-name()='mi']")
    for mi_elem in mi_elements:
        mi_elem_id = mi_elem.attrib.get('id')
        mi_text = html_tree_raw.xpath(f"//*[@id='{mi_elem_id}']")[0].text
        hex_set.add(mi_text.encode('utf-8').hex())
    return hex_set


def check_if_tag_with_id_in_tree(html_tree, tag_name, id):
    xpath_pattern = f".//*[@id='{id}']"
    node_with_id_list = html_tree.xpath(xpath_pattern)
    if node_with_id_list is not None and len(node_with_id_list)==1:
        if get_local_name(node_with_id_list[0].tag)==tag_name:
            return True
    return False

def process_auto_segment_symbol_data(dom_tree_copy, validated_data):
    groups_description_list = validated_data["new_groups"]
    occurrences_description_list = validated_data["new_occurrences"]

    concept_primitive_hex_sets_dict = dict()

    new_groups_dict =  dict()
    for group_description in groups_description_list:
        symbol_name = group_description["symbol_name"]
        new_group_info = generate_group_info_from_mi_ids(dom_tree_copy, group_description["included_mi_ids"])
        group_primitive_hex_set = get_group_primitive_hex_set(dom_tree_copy, Group(**new_group_info))
        if symbol_name in new_groups_dict.keys():
            new_groups_dict[symbol_name].append(new_group_info)
            concept_primitive_hex_sets_dict[symbol_name].update(group_primitive_hex_set)
        else:
            new_groups_dict[symbol_name] = [new_group_info]
            concept_primitive_hex_sets_dict[symbol_name] = group_primitive_hex_set

    new_occurrences_dict = dict()
    for occurrence_description in occurrences_description_list:
        symbol_name = occurrence_description["symbol_name"]
        comp_tag_id = occurrence_description["comp_tag_id"]
        new_occurrence_info = {
            "comp_tag_id": comp_tag_id,
            "tag_name": dom_tree_copy.get_element_by_id(comp_tag_id).tag
        }
        primitive_hex_set = get_comp_tag_primitive_hex_set(dom_tree_copy, comp_tag_id)
        if symbol_name in new_groups_dict.keys():
            new_occurrences_dict[symbol_name].append(new_occurrence_info)
            concept_primitive_hex_sets_dict[symbol_name].update(primitive_hex_set)
        else:
            new_occurrences_dict[symbol_name] = [new_occurrence_info]
            concept_primitive_hex_sets_dict[symbol_name] = primitive_hex_set

    new_concepts_dict = dict()
    for symbol_name in new_groups_dict.keys() | new_occurrences_dict.keys():
        new_concept = MathConcept(symbol_name, "", "symbol-placeholder", {}, [], list(deepcopy(concept_primitive_hex_sets_dict[symbol_name])))
        new_concepts_dict[symbol_name] = asdict(new_concept)

    return new_concepts_dict, new_groups_dict, new_occurrences_dict