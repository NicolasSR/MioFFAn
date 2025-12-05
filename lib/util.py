import json

# Common utilities

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

def check_missing_variables(variables_list):
    if any(var is None for var in variables_list):
        error_message = {
            "status": "error",
            "code": "MISSING_FIELDS",
            "message": f"Some of the following fields were missing or None: {str(variables_list)}"
        }
        # Return 400 Bad Request
        return json.dumps(error_message), 400
    
def check_document_edit_id(current_edit_id, edit_id_in_request):     
    # If the mcdict used in the request differs from the latest, then redirect (i.e., reload the page).
    if edit_id_in_request is None or str(current_edit_id) != edit_id_in_request:
        error_message = {
            "status": "error",
            "code": "VERSION_MISMATCH",
            "message": "Invalid Action! The annotation has been modified elsewhere. Reloading.",
            "action": "reload" # Frontend can check for this string
        }
        return json.dumps(error_message), 409