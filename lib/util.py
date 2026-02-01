import json

from lxml import etree

from lib.datatypes import Group

# Common utilities

def wrap_custom_group(root, group_id, group_info: Group):

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