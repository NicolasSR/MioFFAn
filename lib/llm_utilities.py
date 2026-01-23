import json

from lxml import etree


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