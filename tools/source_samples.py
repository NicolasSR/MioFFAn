import json
import requests
from docopt import docopt
from pathlib import Path

from lxml import etree

from lib.version import VERSION
from lib.logger import main_logger
from tools.preprocess import preprocess_html

# meta
PROG_NAME = "tools.source_samples"
HELP = """Obtain and preprocess samples for MioFFAn

Usage:
    {p} [options]

Options:
    --overwrite         Overwrite output files if already exist

    --data=DIR          Dir for data outputs [default: ./data]
    --templates=DIR     Dir for template outputs [default: ./templates]
    --sources=DIR       Dir for HTML outputs [default: ./sources]

    --debug             Show debug messages
    -q, --quiet         Show less messages

    -h, --help          Show this screen and exit
    -V, --version       Show version
""".format(
    p=PROG_NAME
)

logger = main_logger.getChild(PROG_NAME)

def get_xml_from_sciencedirect(api_key, article_pii):
    article_request_url = 'https://api.elsevier.com/content/article/pii/'+str(article_pii)+'?view=FULL'
    article_request_headers = {'X-ELS-APIKey': api_key}
    article_request_result = requests.get(article_request_url, headers=article_request_headers)
    article_request_status_code = article_request_result.status_code

    if article_request_status_code != 200:
        False, f"Could not retrieve article XML for pii: {article_pii}"

    article_xml_content = article_request_result.content.decode()
    return True, article_xml_content

def get_xml_from_springernature(api_key, article_doi):
    # SpringerNature has an Openaccess API to retrieve Full Text of open access papers from DOI (or other query parameters)
    # article_request_url = f'https://api.springernature.com/openaccess/jats?api_key={api_key}&q=doi:{article_doi}'
    # They also have a FullText API to do so with closed access content, however we do not have access to it in order to test it

    # Furthermore, the XML versions of the papers (at least from the Openaccess API) have their mathematical expressions written in LaTeX.
    # So further processing will be needed.

    False, f"Sourcing from Springer Nature is not implemented yet"

def get_node_by_index_path(root_node, path_str):
    """Navigates children by index. '1.3' -> second child, then its fourth child."""
    current = root_node
    try:
        indices = [int(i) for i in path_str.split('.')]
        for idx in indices:
            current = current[idx]
        return current
    except (IndexError, ValueError):
        return None
    
def prune_xml(tree, references_list, namespaces):
    def select_nodes_to_keep(xpath_query, sub_paths, keep_nodes):
        refs = tree.xpath(xpath_query, namespaces=namespaces)
        for ref in refs:
            keep_nodes.add(ref)
            # Keep ancestors of the reference node
            keep_nodes.update(ref.xpath('ancestor::*'))
            
            if not sub_paths:
                # Keep everything inside if list is empty
                keep_nodes.update(ref.xpath('descendant::*'))
            else:
                # Keep only specific indexed paths
                for path in sub_paths:
                    child_node = get_node_by_index_path(ref, path)
                    if child_node is not None:
                        keep_nodes.add(child_node)
                        keep_nodes.update(child_node.xpath('ancestor::*'))
                        # Keep all descendants of this specific child
                        keep_nodes.update(child_node.xpath('descendant::*'))

    keep_nodes = set()

    for ref in references_list:
        tag_name = ref["tag"]
        print(tag_name)
        attr_strings_list = []
        for k,v in ref.get("attr",{}).items():
            if v is None:
                attr_strings_list.append(f"@{k}")
            else:
                attr_strings_list.append(f"@{k}='{v}'")
        if attr_strings_list:
            attr_string = " and ".join(attr_strings_list)
            attr_string = f"[{attr_string}]"
        else:
            attr_string = ""

        xpath_query = f"//{tag_name}{attr_string}"
        sub_paths = ref.get("sub_paths", [])
        select_nodes_to_keep(xpath_query, sub_paths, keep_nodes)

    # 2. Final Pruning
    for element in tree.xpath('//*'):
        if element not in keep_nodes and element.getparent() is not None:
            element.getparent().remove(element)

def prune_sciencedirect_xml(tree, references_dict):
    namespaces={
        "ce": "http://www.elsevier.com/xml/common/dtd"
    }
    prune_xml(tree, references_dict, namespaces)

def prune_manual_html(tree, references_dict):
    namespaces={}
    prune_xml(tree, references_dict, namespaces)

def xml_to_html(xml_tree, source_type):
    xml_root = xml_tree.getroot() if hasattr(xml_tree, 'getroot') else xml_tree

    # Use no namespace map for the HTML root to keep it clean for HTML5
    html_root = etree.Element("html")
    head = etree.SubElement(html_root, "head")
    
    # 1. FORCE UTF-8 ENCODING
    etree.SubElement(head, "meta", charset="utf-8")
    etree.SubElement(head, "meta", name="viewport", content="width=device-width, initial-scale=1.0")

    style = etree.SubElement(head, "style")
    style.text = """
    body { 
        max-width: 700px; 
        margin: 40px 40px; 
        padding: 0 20px; 
        font-family: sans-serif; 
        line-height: 1.6; 
        color: #333;
        background-color: #fdfdfd;
    }
    h1 { 
        display: flex; 
        align-items: baseline; 
        border-bottom: 1px solid #eee; 
        padding-bottom: 5px; 
    }
    h2 { 
        display: flex; 
        align-items: baseline; 
        border-bottom: 1px solid #eee; 
        padding-bottom: 5px; 
    }
    .section-number { 
        font-weight: bold; 
        margin-right: 12px; 
        color: #005587; 
    }
    p { text-align: justify; margin-bottom: 1.5em; }
    p + .formula {
        margin-top: -0.5em; /* Pull formula closer to the preceding text */
    }
    .formula + p {
        margin-top: 1em; /* Standard gap for following text */
    }
    p span, p math {
        display: inline;
    }
    /* Ensure math has a tiny bit of breathing room if it hits text */
    math {
        margin: 0 2px;
    }
    /* Enable horizontal scrolling if the math is just too wide */
    .formula {
        display: block;
        overflow-x: auto;
        overflow-y: hidden;
        max-width: 100%;
    }
    .section-label {
        margin: 0 2px;
    }
    """
    
    body = etree.SubElement(html_root, "body")

    def transform_node_sciencedirect(xml_node, html_parent, context=None):
        """
        context: A dictionary to keep track of the 'current_p' bucket 
                within the current parent level.
        """
        if context is None:
            context = {"current_p": None}

        local = etree.QName(xml_node).localname
        
        # Helper to get/create a paragraph bucket
        def get_p():
            if context["current_p"] is None:
                context["current_p"] = etree.SubElement(html_parent, "p")
            return context["current_p"]
        
        def set_p(parent_element):
            context["current_p"] = parent_element

        # Helper to reset bucket (when hitting block elements)
        def reset_p():
            context["current_p"] = None

        # --- 1. HANDLE TEXT (Start of Node) ---
        if xml_node.text and xml_node.text.strip():
            if get_p().tag == "span":
                get_p().text = xml_node.text
            else:
                span = etree.SubElement(get_p(), "span", attrib={"class": "gd_text"})
                span.text = xml_node.text

        # --- 2. HANDLE CHILDREN ---
        for i, child in enumerate(xml_node):
            c_local = etree.QName(child).localname

            if local == "formula" and c_local == "math":
                reset_p() # Formulas are block, so close the paragraph
                div = etree.SubElement(html_parent, "div", attrib={"class": "formula"})
                # Inline math stays in the current paragraph
                strip_ns(child, div)
                # # For nested formulas, we use a fresh context inside the div
                # transform_node(child, div, context={"current_p": div})
                reset_p() # Ensure text after formula starts a new p
                
                
            # INLINE MATH
            elif c_local == "math":
                # Inline math stays in the current paragraph
                strip_ns(child, get_p())

            elif c_local == "title":
                reset_p()
                h1 = etree.SubElement(html_parent, "h1")
                span = etree.SubElement(h1, "span", attrib={"class": "article-title"})
                span.text = ''.join(child.itertext())
                # transform_node(child, span, context={"current_p": span})
                reset_p()

            elif c_local == "label":
                if len(xml_node) > i+2 and etree.QName(xml_node[i+1]).localname == "section-title":
                    reset_p()
                    h2 = etree.SubElement(html_parent, "h2")
                    span = etree.SubElement(h2, "span", attrib={"class": "section-label"})
                    transform_node(child, span, context={"current_p": span})
                    set_p(h2)
                else:
                    reset_p()
                    span = etree.SubElement(get_p(), "span", attrib={"class": "formula-label"})
                    transform_node(child, span, context={"current_p": span})
                    reset_p()

            elif c_local == "section-title":
                if get_p().tag == "h2":
                    span = etree.SubElement(get_p(), "span", attrib={"class": "section-title"})
                    # transform_node(child, span, context={"current_p": span})
                else:
                    reset_p()
                    h2 = etree.SubElement(html_parent, "h2")
                    span = etree.SubElement(h2, "span", attrib={"class": "section-title"})
                    # transform_node(child, span, context={"current_p": span})
                span.text = ''.join(child.itertext())
                reset_p()

            # RECURSIVE CONTAINERS (like sections or paragraphs)
            elif c_local in ["section", "para", "sections", "body"]:
                # If it's a structural container, we don't reset p yet, 
                # we just let the children decide.
                transform_node(child, html_parent, context)

            # DEFAULT (Unknown tags)
            else:
                transform_node(child, html_parent, context)

            # --- 3. HANDLE TAIL TEXT (Text after a child) ---
            if child.tail and child.tail.strip():
                # Tail text always belongs in a paragraph
                span = etree.SubElement(get_p(), "span", attrib={"class": "gd_text"})
                span.text = child.tail

    def transform_node_manual_springernature(xml_node, html_parent, context=None):
        """
        context: A dictionary to keep track of the 'current_p' bucket 
                within the current parent level.
        """
        if context is None:
            context = {"current_p": None}

        local = etree.QName(xml_node).localname
        
        # Helper to get/create a paragraph bucket
        def get_p():
            if context["current_p"] is None:
                context["current_p"] = etree.SubElement(html_parent, "p")
            return context["current_p"]
        
        def set_p(parent_element):
            context["current_p"] = parent_element

        # Helper to reset bucket (when hitting block elements)
        def reset_p():
            context["current_p"] = None

        # --- 1. HANDLE TEXT (Start of Node) ---
        if xml_node.text and xml_node.text.strip():
            if get_p().tag == "span":
                get_p().text = xml_node.text
            else:
                span = etree.SubElement(get_p(), "span", attrib={"class": "gd_text"})
                span.text = xml_node.text

        # --- 2. HANDLE CHILDREN ---
        for i, child in enumerate(xml_node):
            c_local = etree.QName(child).localname

            if c_local=="div" and "class" in child.attrib and child.attrib["class"]=="c-article-equation__content":
                reset_p() # Formulas are block, so close the paragraph
                div = etree.SubElement(html_parent, "div", attrib={"class": "formula"})
                transform_node(child, div, context={"current_p": div})
                reset_p() # Ensure text after formula starts a new p

            elif c_local=="div" and "class" in child.attrib and child.attrib["class"]=="c-article-equation__number":
                reset_p()
                span = etree.SubElement(get_p(), "span", attrib={"class": "formula-label"})
                transform_node(child, span, context={"current_p": span})
                reset_p()
                # reset_p() # Formulas are block, so close the paragraph
                # div = etree.SubElement(html_parent, "div", attrib={"class": "formula-label"})
                # transform_node(child, div, context={"current_p": div})
                # reset_p() # Ensure text after formula starts a new p

            # INLINE MATH
            elif c_local == "math":
                # Inline math stays in the current paragraph
                strip_ns(child, get_p())

            elif c_local == "h1":                
                reset_p()
                h1 = etree.SubElement(html_parent, "h1")
                span = etree.SubElement(h1, "span", attrib={"class": "article-title"})
                span.text = ''.join(child.itertext())
                reset_p()

            elif c_local == "h2":
                reset_p()
                h2 = etree.SubElement(html_parent, "h2")
                span = etree.SubElement(h2, "span", attrib={"class": "section-title"})
                span.text = ''.join(child.itertext())
                reset_p()

            elif c_local == "script":
                continue

            # DEFAULT (Unknown tags)
            else:
                transform_node(child, html_parent, context)

            # --- 3. HANDLE TAIL TEXT (Text after a child) ---
            if child.tail and child.tail.strip():
                # Tail text always belongs in a paragraph
                span = etree.SubElement(get_p(), "span", attrib={"class": "gd_text"})
                span.text = child.tail

    def strip_ns(node, parent):
        """Cleanly copies MathML while stripping prefixes and handling mfenced."""
        local = etree.QName(node).localname
        
        # mfenced polyfill (as discussed before)
        if local == "mfenced":
            target = etree.SubElement(parent, "mrow")
            etree.SubElement(target, "mo").text = node.get("open", "(")
            for child in node:
                strip_ns(child, target)
            etree.SubElement(target, "mo").text = node.get("close", ")")
        else:
            # Standard copy
            new_node = etree.SubElement(parent, local, attrib=node.attrib)
            new_node.text = node.text
            for child in node:
                strip_ns(child, new_node)
            # Note: We do NOT handle tail here because the parent logic handles it

    if source_type == "science_direct":
        transform_node = transform_node_sciencedirect
    elif source_type == "manual_springernature":
        transform_node = transform_node_manual_springernature
    transform_node(xml_root, body)
    
    return html_root





def main():
    # parse options
    args = docopt(HELP, version=VERSION)

    # dirs and files
    data_dir = Path(args['--data'])
    templates_dir = Path(args['--templates'])
    sources_dir = Path(args['--sources'])

    overwrite = args["--overwrite"]

    main_logger.set_logger(args['--quiet'], args['--debug'])

    with open('credentials.json', 'r') as credentials_file:
        credentials_config = json.load(credentials_file)
    sd_api_key = credentials_config["science_direct_api"]["key"]
    sn_api_key = credentials_config["springer_nature_api"]["key"]
    with open('sourcing_info/sources_config.json', 'r') as sources_config_file:
        sources_config = json.load(sources_config_file)

    for sample_name, sample_info in sources_config["science_direct"]["samples"].items():
        logger.info('Processing sample with name: {}'.format(sample_name))
        article_pii = sample_info["pii"]

        # now prepare for the preprocess
        logger.info('Obtaining XML for SicenceDirect PII: "{}"'.format(article_pii))

        success, data = get_xml_from_sciencedirect(sd_api_key, article_pii)
        if not success:
            raise f"Error: {data}"
        xml_content = data

        xml_tree = etree.fromstring(xml_content, parser = etree.XMLParser(remove_blank_text=True))
        if sample_info.get("pruning_references", None) is not None:
            pruning_config = sample_info["pruning_references"]
        else:
            pruning_config = [
                {"tag": "ce:title"},
                {"tag": "ce:sections"}
            ]
        
        logger.info('Pruning XML content')
        prune_sciencedirect_xml(xml_tree, pruning_config)

        logger.info('Converting XML to HTML')
        raw_html_tree = xml_to_html(xml_tree, "science_direct")

        logger.info('Processing HTML')
        preprocess_html(sample_name, raw_html_tree, data_dir, templates_dir, sources_dir, overwrite)

    for sample_name, sample_info in sources_config["springer_nature"]["samples"].items():
        logger.info('Processing sample with name: {}'.format(sample_name))
        article_doi = sample_info["doi"]

        # now prepare for the preprocess
        logger.info('Obtaining XML for Springer Nature DOI: "{}"'.format(article_doi))

        success, data = get_xml_from_springernature(sn_api_key, article_doi)

        if not success:
            raise f"Error: {data}"
        
    for sample_name, sample_info in sources_config["manual_html"]["samples"].items():
        sample_file_name = sample_info["filename"]
        pruning_references = sample_info["pruning_references"]
        with open(f"manual_sources/{sample_file_name}.html", "r") as f:
            raw_html_tree = etree.parse(f, parser = etree.HTMLParser(encoding='utf-8', remove_blank_text=True))
        prune_manual_html(raw_html_tree, pruning_references)

        html_tree = xml_to_html(raw_html_tree, "manual_springernature")

        logger.info('Processing HTML')
        preprocess_html(sample_name, html_tree, data_dir, templates_dir, sources_dir, overwrite)


if __name__ == '__main__':
    main()