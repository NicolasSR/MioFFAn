# The preprocess tool for MioGatto
import lxml.html
import unicodedata
from docopt import docopt
from pathlib import Path
import re
import json

from lib.version import VERSION
from lib.logger import main_logger
from lib.util import get_mi2hex
from lib.annotation import dump_json
from tools.inject_tag_ids import add_ids_to_html

from lxml.html.builder import SPAN

# meta
PROG_NAME = "tools.preprocess"
HELP = """Preprocess tool for MioGatto

Usage:
    {p} [options] HTML

Options:
    --embed-floats      Preserve embed figure/table codes
    --overwrite         Overwrite output files if already exist

    -d DIR, --data=DIR  Dir for data outputs [default: ./templates]
    --templates=DIR     Dir for template outputs [default: ./templates]
    --sources=DIR       Dir for HTML outputs [default: ./sources]

    -D, --debug         Show debug messages
    -q, --quiet         Show less messages

    -h, --help          Show this screen and exit
    -V, --version       Show version
""".format(
    p=PROG_NAME
)

logger = main_logger.getChild(PROG_NAME)


def hex2surface(idf_hex):
    idf_text = bytes.fromhex(idf_hex).decode()
    surface = {'text': idf_text}

    if len(idf_text) < 2:
        surface['unicode_name'] = unicodedata.name(idf_text)
    else:
        surface['unicode_name'] = None

    return surface


# add word span tags to text directly
def split_words_into_span_tags(text, parent_id, idx):
    def word_span(w, p, i, c):
        s = SPAN(w)
        s.attrib['class'] = 'gd_word'
        s.attrib['id'] = '{}.{}.w{}'.format(p, i + 1, c)
        return s

    words = text.split(' ')
    word_cnt, spans = 1, []

    for w in words[:-1]:
        spans.extend([word_span(w, parent_id, idx, word_cnt), SPAN(' ')])
        word_cnt += 1

    if not words[-1] == '':
        spans.append(word_span(words[-1], parent_id, idx, word_cnt))

    return spans


def embed_word_span_tags(e, parent_id):
    # get texts and remove
    texts = [e.text]
    e.text = None
    for c in e.getchildren():
        texts.append(c.tail)
        c.tail = None

    spans = [split_words_into_span_tags(t, parent_id, i) if t else None for i, t in enumerate(texts)]

    for i in range(len(spans) - 1, -1, -1):
        if not spans[i] is None:
            for s in reversed(spans[i]):
                e.insert(i, s)


def remove_embed_floats(root, paper_id):
    # remove embed float
    from lxml.html.builder import IMG

    for e in root.xpath('//figure[@class="ltx_figure"]'):
        # remove embed figures
        for c in e:
            if c.tag != 'img' and c.tag != 'figcaption':
                e.remove(c)

        # add <img>
        if [c.tag for c in e] == ['figcaption']:
            img = IMG()
            src = '/static/img/{}/{}.png'.format(paper_id, e.attrib['id'].replace('.', '_'))
            img.attrib['src'] = src
            img.attrib['alt'] = src
            e.insert(0, img)

    for e in root.xpath('//figure[@class="ltx_table"]'):
        # remove embed tables
        for c in e:
            if c.tag != 'figcaption':
                e.remove(c)

        # add <img>
        img = IMG()
        src = '/static/img/{}/{}.png'.format(paper_id, e.attrib['id'].replace('.', '_'))
        img.attrib['src'] = src
        img.attrib['alt'] = src
        e.insert(0, img)


def embed_multiword_spans(e, p):
    # Define a utility function to check if text is meaningful
    def is_meaningful_text(text):
        if text:
            # Check for non-whitespace and strip internal newlines/tabs
            return re.search(r'\S', text) is not None
        return False

    unstructured_text_spans = []

    # Check if there is text within div (directly at the beginning).
    # If so, add it into a span element and remove the original
    if is_meaningful_text(e.text):
        s = SPAN(e.text)
        s.attrib['class'] = 'gd_text'
        s.attrib['id'] = '{}.{}'.format(p, 0)
        unstructured_text_spans.append(s)
        e.text = None
    else:
        unstructured_text_spans.append(None)

    for i, c in enumerate(e.getchildren()):
        # If the child's tail contains text, add it to a span. Then remove original
        if is_meaningful_text(c.tail):
            s = SPAN(c.tail)
            s.attrib['class'] = 'gd_text'
            s.attrib['id'] = '{}.{}'.format(p, i+1)
            unstructured_text_spans.append(s)
            c.tail = None
        else:
            unstructured_text_spans.append(None)

    # Go in reverse and add each new span in the corresponding location.
    for i in range(len(unstructured_text_spans) - 1, -1, -1):
        current_span = unstructured_text_spans[i]
        if not current_span is None:
            e.insert(i, current_span)


def preprocess_html_inner(tree, paper_id, embed_floats = False):
    root = tree.getroot() if hasattr(tree, 'getroot') else tree

    # drop unnecessary annotations
    for e in root.xpath('//annotation|//annotation-xml'):
        e.drop_tree()

    for e in root.xpath('//span[contains(@class,"ltx_text")]'):
        e.drop_tag()

    # tweak images
    for e in root.xpath('//img'):
        if 'ltx_graphics' in e.attrib.get('class', '').split(' '):
            src = '/static/img/{}/'.format(paper_id) + e.attrib['src']
            e.attrib['src'] = src
            e.attrib['alt'] = src
            e.attrib['width'] = None
            e.attrib['height'] = None

    # div containers
    for iteration_number,e in enumerate(root.xpath('//span')):
        parent_id = e.get('id')
        if parent_id is None:
            parent_id_tail = ''
            current_element = e.getparent()
            while current_element is not None:
                parent_id_tail += '_sub'
                # Get the 'id' attribute. Returns None if it doesn't exist.
                ancestor_id = current_element.get('id')
                # Check if an ID exists and is not an empty string.
                if ancestor_id:
                    ancestor_id += parent_id_tail
                    break
                # Move up to the next ancestor (the current element's parent).
                current_element = current_element.getparent()
            parent_id = ancestor_id+parent_id_tail if ancestor_id is not None else 'span_'+str(iteration_number)
        
        embed_multiword_spans(e,parent_id)

    # normal paragraphs
    for e in root.xpath('//p'):
        parent_id = e.attrib['id']

        # In the original method, each individual word is separated into a new span.
        # This seems too overcomplicated to me
        # embed_word_span_tags(e, parent_id)

        # We want to embed entire groups of words. As later we will extract the exact
        # text selection by the starting character index in the span.
        embed_multiword_spans(e,parent_id)

    # div containers
    for e in root.xpath('//div'):
        if "id" in e.attrib.keys():
            parent_id = e.attrib['id']
        else:
            parent_id = None
        embed_multiword_spans(e, parent_id)

    # captions
    for e in root.xpath('//figcaption'):
        parent_id = e.getparent().attrib['id']
        embed_word_span_tags(e, parent_id)

    # footnotes
    for e in root.xpath('//span[contains(@class,"ltx_note_content")]'):
        parent_id = e.getparent().getparent().attrib['id']
        embed_word_span_tags(e, parent_id)

    # paragraphs in inline blocks
    for e in root.xpath('//span[contains(@class,"ltx_inline-block")]//span[contains(@class, "ltx_p")]'):
        parent_id = e.attrib['id']
        embed_word_span_tags(e, parent_id)

    # almost done
    if not embed_floats:
        remove_embed_floats(root, paper_id)


def observe_mi(tree):
    # initialize
    hex_set = set()

    # the process
    mi2hex = get_mi2hex(tree)
    root = tree.getroot() if hasattr(tree, 'getroot') else tree

    for e in root.xpath('//mi'):
        # get mi_id and idf
        mi_id = e.attrib.get('id')
        hex = mi2hex.get(mi_id)

        if mi_id is None or hex is None:
            # wired but to avoid errors
            continue

        hex_set.add(hex)

    return hex_set


def observe_comp_tags(tree):
    comp_tags_dict = dict()
    comp_tag_attribs = set()

    with open('config.json', 'r') as f:
        config = json.load(f)
    
    xpath_selector = " | ".join(['//'+tag for tag in config['COMPOUND_CONCEPT_TAGS']])

    # initialize
    root = tree.getroot() if hasattr(tree, 'getroot') else tree
    for e in root.xpath(xpath_selector):
        comp_tags_dict[e.attrib.get('id')] = e.tag
        comp_tag_attribs.update(e.attrib)

    return comp_tags_dict, comp_tag_attribs


def list_hex_info(hex_set):

    hex_set_sorted = sorted(hex_set)

    # construct a list of primitive symbols
    return {hex: hex2surface(hex) for hex in hex_set_sorted}

def preprocess_html(sample_name, html_tree, data_dir, templates_dir, sources_dir, overwrite = False, embed_floats = False):
    # now prepare for the preprocess
    logger.info('Begin to preprocess Paper "{}"'.format(sample_name))

    data_dir = data_dir / sample_name
    data_dir.mkdir(parents=True, exist_ok=True)
    data_anno_path = data_dir / '{}_anno.json'.format(sample_name)
    data_mcdict_path = data_dir / '{}_mcdict.json'.format(sample_name)
    templates_dir = templates_dir / sample_name
    templates_dir.mkdir(parents=True, exist_ok=True)
    template_anno_path = templates_dir / '{}_anno.json'.format(sample_name)
    template_mcdict_path = templates_dir / '{}_mcdict.json'.format(sample_name)
    sources_dir.mkdir(parents=True, exist_ok=True)
    source_html_path = sources_dir / '{}.html'.format(sample_name)

    # prevent unintentional overwriting
    if overwrite is not True:
        if source_html_path.exists():
            logger.error('Source file %s exists. Use --overwrite to force', source_html_path)
            return

        if data_anno_path.exists() or data_mcdict_path.exists():
            logger.error('Data files exist in %s. Use --overwrite to force', data_dir)
            return

        if template_anno_path.exists() or template_mcdict_path.exists():
            logger.error('Template files exist in %s. Use --overwrite to force', templates_dir)
            return

    add_ids_to_html(html_tree)
    preprocess_html_inner(html_tree, sample_name, embed_floats)

    # extract formulae information
    hex_set = observe_mi(html_tree)
    print('#primitive values: {}'.format(len(hex_set)))

    # write output files
    logger.info('Writing preprocessed HTML to %s', source_html_path)
    if type(html_tree) == lxml.etree._Element:
        html_tree = html_tree.getroottree()
    html_tree.write(str(source_html_path), pretty_print=True, encoding='utf-8')

    logger.info('Writing initialized anno to %s and %s', data_anno_path, template_anno_path)
    anno_json = {
        '_anno_version': '1.0',
        '_annotator': 'YOUR NAME',
        'primitive_symbols': list_hex_info(hex_set),
        'groups': {},
        'next_available_group_id': 0
    }
    with open(data_anno_path, 'w') as f:
        dump_json(anno_json, f)
    with open(template_anno_path, 'w') as f:
        dump_json(anno_json, f)

    logger.info('Writing initialized mcdict template to %s and %s', data_mcdict_path, template_mcdict_path)
    mcdict_json = {
        '_author': 'YOUR NAME',
        '_mcdict_version': '1.0',
        'concepts': {},
        'next_available_mc_id': 0,
        'occurences_dict': {},
        'eoi_dict': {}
    }
    with open(data_mcdict_path, 'w') as f:
        dump_json(mcdict_json,f)
    with open(template_mcdict_path, 'w') as f:
        dump_json(mcdict_json,f)

    

def main():
    # parse options
    args = docopt(HELP, version=VERSION)

    main_logger.set_logger(args['--quiet'], args['--debug'])
    embed_floats = args['--embed-floats']

    # dirs and files
    data_dir = Path(args['--data'])
    templates_dir = Path(args['--templates'])
    sources_dir = Path(args['--sources'])

    html_in = Path(args['HTML'])
    paper_id = html_in.stem

    overwrite = args['--overwrite']

    # load the HTML and modify the DOM tree
    tree = lxml.html.parse(str(html_in))

    preprocess_html(paper_id, tree, data_dir, templates_dir, sources_dir, overwrite, embed_floats)
    

if __name__ == '__main__':
    main()