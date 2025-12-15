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