import json
from dataclasses import asdict

from lxml import etree

from lib.datatypes import Group, Occurence

# Common utilities

def sort_ids_by_dfs(tree, id_list):
    # Create a mapping of element -> DFS index
    # .iter() follows DFS order by default
    dfs_map = {el: i for i, el in enumerate(tree.iter())}
    
    # Get the actual elements for your IDs
    elements = [tree.get_element_by_id(node_id) for node_id in id_list]
    
    # Sort elements based on their position in the DFS map
    elements.sort(key=lambda x: dfs_map[x])
    sorted_ids = []
    for el in elements:
        sorted_ids.append(el.get('id'))
    return sorted_ids

def find_lowest_common_ancestor(tree, el1, el2):
    # Step 2: Find LCA (using the path-comparison method)
    anc1 = list(el1.iterancestors())[::-1] + [el1]
    anc2 = list(el2.iterancestors())[::-1] + [el2]
    lca = None
    for a, b in zip(anc1, anc2):
        if a == b: lca = a
        else: break
    return lca

def get_nodes_distance(el1, el2):
    #Positive if el1 deeper than el2
    el1_depth = len(list(el1.iterancestors()))
    el2_depth = len(list(el2.iterancestors()))
    return el1_depth - el2_depth

def generate_group_info_from_mi_ids(root, mi_ids_list):
    ordered_entry_ids = sort_ids_by_dfs(root, mi_ids_list)
    entry_element_start = root.get_element_by_id(ordered_entry_ids[0])
    entry_element_stop = root.get_element_by_id(ordered_entry_ids[-1])

    lca = find_lowest_common_ancestor(root, entry_element_start, entry_element_stop)

    lca_children = lca.getchildren()

    target_child_start = next(c for c in lca_children if c == entry_element_start or entry_element_start in c.iterdescendants())
    target_child_stop = next(c for c in reversed(lca_children) if c == entry_element_stop or entry_element_stop in c.iterdescendants())
    mi_start = target_child_start.xpath("descendant-or-self::*[local-name()='mi']")[0]
    mi_stop = target_child_stop.xpath("descendant-or-self::*[local-name()='mi']")[0]

    # As we are using LCA from two identified nodes to define groups, this should be unnecessary.
    # Remodel Group annoation to keep only first and last mi ids as identifiers
    ancestry_level_start = get_nodes_distance(mi_start, lca) - 1
    ancestry_level_stop = get_nodes_distance(mi_stop, lca) - 1

    final_group = Group(ancestry_level_start, ancestry_level_stop, mi_start.get('id'), mi_stop.get('id'))
    return asdict(final_group)

def get_group_sibling_elements(tree, group: Group):
    start_element = tree.get_element_by_id(group.start_id)
    stop_element = tree.get_element_by_id(group.stop_id)

    lca = find_lowest_common_ancestor(tree, start_element,stop_element)

    sibling_elements = list()
    record = False
    for c in lca.getchildren():
        if record == False and (c == start_element or start_element in c.iterdescendants()):
            record = True
        if record == True:
            sibling_elements.append(c)
            if c == stop_element or stop_element in c.iterdescendants():
                break
    return sibling_elements

def get_element_primitive_hex_set(element):
    hex_set = set()
    mi_elements = element.xpath("descendant-or-self::*[local-name()='mi']")
    for mi_elem in mi_elements:
        mi_elem_text = mi_elem.text
        hex_set.add(mi_elem_text.encode('utf-8').hex())
    return hex_set

def get_group_primitive_hex_set(tree, group: Group):
    sibling_elements = get_group_sibling_elements(tree, group)
    group_primitive_hex_set = set()
    for element in sibling_elements:
        group_primitive_hex_set.update(get_element_primitive_hex_set(element))
    return group_primitive_hex_set

def get_comp_tag_primitive_hex_set(tree, comp_tag_id):
    element = tree.get_element_by_id(comp_tag_id)
    return get_element_primitive_hex_set(element)

def wrap_custom_group(root, group_id, group_info: Group):
        
    # SHOULD BE MODIFIED TO USE get_group_sibling_elements()

    def check_contains_by_traversal(ancestor_element, descendant_element) -> bool:
        """
        Checks if ancestor_element contains (is an ancestor of) descendant_element
        by traversing up the parent chain of the descendant.
        """
        current_element = descendant_element.getparent()
        
        # Traverse up the tree until the root (None) is reached
        while current_element is not None:
            if current_element is ancestor_element:
                return True
            current_element = current_element.getparent()
            
        return False
    
    start_id = group_info.start_id
    stop_id = group_info.stop_id
    ancestry_level_start = group_info.ancestry_level_start
    ancestry_level_stop = group_info.ancestry_level_stop

    parent_start_path_part = "/parent::*"*ancestry_level_start if ancestry_level_start is not None else ""
    parent_stop_path_part = "/parent::*"*ancestry_level_stop if ancestry_level_stop is not None else ""

    start_element_list = root.xpath("//*[@id='{}']{}".format(start_id, parent_start_path_part))
    start_element = start_element_list[0] if len(start_element_list)==1 else None
    stop_element_list = root.xpath("//*[@id='{}']{}".format(stop_id, parent_stop_path_part))
    stop_element = stop_element_list[0] if len(stop_element_list)==1 else None

    # # Find all elements between start_id and stop_id (inclusive)
    # xpath_expression = "//*[@id='{}']{}/following::*[preceding::*[@id='{}']{}]".format(
    #     start_id, parent_start_path_part, stop_id, parent_stop_path_part)
    # elements_in_group = root.xpath(xpath_expression)

    if start_element is None or stop_element is None:
        print('No elements found for group %s (%s to %s)', group_id, start_id, stop_id)
        return False

    # Get the parent element to wrap the group
    parent = start_element.getparent()
    insert_index = parent.index(start_element)

    # Find all elements between start_element and stop_element (inclusive)
    elements_in_group = []
    current_element = start_element
    while current_element is not None:
        elements_in_group.append(current_element)
        if current_element is stop_element or check_contains_by_traversal(current_element, stop_element):
            break
        current_element = current_element.getnext()

    # Create a new span element
    mstyle = etree.Element('mstyle', id=group_id, attrib={'class': 'custom-group'})

    # Move the elements into the span
    for elem in elements_in_group:
        parent.remove(elem)
        mstyle.append(elem)

    parent.insert(insert_index, mstyle)

    return True

def get_mi2idf(tree):
    raise("mi2idf deprecated. Please update code to use get_mi2hex instead.")

def get_mi2hex(tree):
    root = tree.getroot()
    mi2hex = dict()

    # dirty settings
    non_identifiers = [
        'e280a6',  # HORIZONTAL ELLIPSIS (…)
        'e28baf',  # MIDLINE HORIZONTAL ELLIPSIS (⋯)
        'e28bae',  # VERTICAL ELLIPSIS (⋮)
        'e28bb1',  # DOWN RIGHT DIAGONAL ELLIPSIS (⋱)
        'e296a1',  # QED BOX (□)
    ]

    # loop mi in the tree
    for e in root.xpath('//mi'):
        mi_id = e.attrib.get('id')

        # skip if empty
        if e.text is None:
            continue

        # get idf hex
        idf_hex = e.text.encode().hex()

        # None if non-identifiers
        if idf_hex in non_identifiers:
            mi2hex[mi_id] = None
            continue

        mi2hex[mi_id] = idf_hex

    return mi2hex

class PostRequestError(Exception):
    """Custom exception for handling POST request errors."""
    def __init__(self, code: str, message: str, http_status: int = 400):
        self.code = code
        self.message = message
        self.http_status = http_status
        super().__init__(message)

    def to_dict(self):
        return {
            "status": "error",
            "code": self.code,
            "message": self.message
        }

def check_missing_variables(**kwargs):
    missing_vars = [name for name, value in kwargs.items() if value is None]
    if missing_vars:
        raise PostRequestError(
            code="MISSING_FIELDS",
            message=f"The following fields were missing: {', '.join(missing_vars)}",
            http_status=400
        )
    
def check_document_edit_id(current_edit_id, edit_id_in_request):     
    # If the mcdict used in the request differs from the latest, then redirect (i.e., reload the page).
    if edit_id_in_request is None or str(current_edit_id) != edit_id_in_request:
        raise PostRequestError(
            code="VERSION_MISMATCH",
            message=f"Annotation version mismatch. Server:{current_edit_id} vs Request:{edit_id_in_request}.",
            http_status=400
        )