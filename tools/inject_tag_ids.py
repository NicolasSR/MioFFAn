import os
import sys
import glob
import json

from lxml import etree as ET
from lxml.etree import HTMLParser

def find_tag_and_add_ID(tree, tag_name, class_name=None):
    # 4. Find all MathML identifier tags <mi> using XPath.
    # We use local-name()='mi' to find <mi> tags regardless of how their
    # MathML namespace (http://www.w3.org/1998/Math/MathML) is prefixed in the source document.
    if class_name is None:
        xpath_expr = f"//*[local-name()='{tag_name}']"
        identifier = tag_name
    else:
        xpath_expr = f"//*[local-name()='{tag_name}' and @class='{class_name}']"
        identifier = class_name
    matching_tags = tree.xpath(xpath_expr)
    
    print(f"Found {len(matching_tags)} <{tag_name}> tags to inspect.")
    
    tags_counter = 1
    modified_count = 0
    
    # 5. Iterate over tags and assign/check IDs
    for tag in matching_tags:
        # Check if the 'id' attribute exists and has content
        if not tag.get('id'):
        # if True:
            # Generate a new unique ID
            new_id = f"{identifier}_{tags_counter}"
            
            # Assign the new ID using the .set() method
            tag.set('id', new_id)
            modified_count += 1
            
        # The logic here preserves existing IDs, per your original request.
        tags_counter += 1

    print(f"Successfully added {modified_count} unique IDs.")


def add_ids_to_html(html_tree):
    """
    Parses an HTML file containing MathML, finds all <mi> tags, as well as <msup> or <msub>, and assigns 
    a unique ID to those that are missing one, using the lxml library.

    Args:
        html_tree: HTML tree (lxml etree) to modify
    """

    with open('config.json', 'r') as f:
        config = json.load(f)
    
    tags_to_process = ['p','div.formula','mi'] + config['COMPOUND_CONCEPT_TAGS']
    for tag_name in tags_to_process:
        tag_and_class = tag_name.split('.')
        if len(tag_and_class) == 1:
            tag_name = tag_and_class[0]
            class_name = None
        elif len(tag_and_class) == 2:
            tag_name = tag_and_class[0]
            class_name = tag_and_class[1]
        else:
            print(f"Could not get tag name and class from '{tag_name}'")
        find_tag_and_add_ID(html_tree, tag_name, class_name)