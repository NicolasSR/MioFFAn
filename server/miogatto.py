# The server implementation for MioGatto
from flask import request, redirect, flash, render_template, jsonify, Markup
from typing import Optional
from logging import Logger
from copy import deepcopy
import lxml
from lxml import etree
import subprocess
import json
import re
import os

from lib.version import VERSION
from lib.annotation import MiAnno, McDict, CmcDict
from lib.datatypes import MathConcept, CompoundMathConcept, Occurence

# get git revision
try:
    GIT_REVISON = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).strip().decode('ascii')
except OSError:
    GIT_REVISON = 'Unknown'


def make_concept(res) -> Optional[MathConcept]:
    # check arity
    if not res.get('arity').isdigit():
        flash('Arity must be non-negative integer.')
        return None
    else:
        arity = int(res.get('arity'))

    # check description
    description = res.get('description')
    if len(description) == 0:
        flash('Description must be filled.')
        return None

    # get affixes
    affixes = []
    for i in range(10):
        t_i = res.get('affixes{}'.format(i))
        if t_i != '':
            affixes.append(t_i)

    return MathConcept(description, arity, affixes)

def make_compound_concept(res) -> Optional[CompoundMathConcept]:
    # check arity
    if not res.get('arity').isdigit():
        flash('Arity must be non-negative integer.')
        return None
    else:
        arity = int(res.get('arity'))

    # check description
    description = res.get('description')
    if len(description) == 0:
        flash('Description must be filled.')
        return None

    # get primitive concepts
    primitive_concepts = res.get('hex_primitives_string').split(',')
    
    return CompoundMathConcept(description, arity, primitive_concepts)

def affixes_pulldowns():
    select_tag = '''<li><select name="affixes{}">
<option value="">-----</option>
<option value="subscript">Subscript</option>
<option value="superscript">Superscript</option>
<option value="comma">Comma</option>
<option value="semicolon">Semicolon</option>
<option value="colon">Colon</option>
<option value="prime">Prime</option>
<option value="asterisk">Asterisk</option>
<option value="circle">Circle</option>
<option value="hat">Hat</option>
<option value="tilde">Tilde</option>
<option value="bar">Bar</option>
<option value="over">Over</option>
<option value="over right arrow">Over right arrow</option>
<option value="over left arrow">Over left arrow</option>
<option value="dot">Dot</option>
<option value="double dot">Double dot</option>
<option value="dagger">Dagger</option>
<option value="double dagger">Double dagger</option>
<option value="open parenthesis">Open parenthesis</option>
<option value="close parenthesis">Close parenthesis</option>
<option value="open bracket">Open bracket</option>
<option value="close bracket">Close bracket</option>
<option value="open brace">Open brace</option>
<option value="close brace">Close brace</option>
<option value="vertical bar">Vertical bar</option>
<option value="leftside argument">Leftside argument</option>
<option value="rightside argument">Rightside argument</option>
<option value="leftside base">Leftside base</option>
</select></li>'''
    items = '\n'.join([select_tag.format(i) for i in range(10)])

    return '<ol>{}</ol>'.format(items)


def preprocess_mcdict(concepts):
    # description processor
    def process_math(math):
        def construct_mi(idf_text, idf_var, concept_id):
            mi = '<mi data-math-concept="{}"'.format(concept_id)

            if idf_var == 'roman':
                mi += ' mathvariant="normal">'
            else:
                mi += '>'

            mi += idf_text + '</mi>'

            return mi

        # protect references (@x)
        math = re.sub(r'(@\d+)', r'<mi>\1</mi>', math)

        # expand \gf
        rls = [
            (construct_mi(m.group(1), m.group(2), int(m.group(3))), m.span())
            for m in re.finditer(r'\\gf{(.*?)}{(.*?)}{(\d*?)}', math)
        ]
        for r in reversed(rls):
            s, e = r[1]
            math = math[:s] + r[0] + math[e:]

        return '<math>' + math + '</math>'

    def process_desc(desc):
        if not desc or '$' not in desc:
            return desc

        # process maths
        it = desc.split('$')
        desc_new = ''.join([a + process_math(b) for a, b in zip(it[::2], it[1::2])])
        if len(it) % 2 != 0:
            desc_new += it[-1]

        return desc_new

    # initialize
    mcdict = dict()

    for idf_hex, idf in concepts.items():
        mcdict[idf_hex] = dict()
        for idf_var, cls in idf.items():
            mcdict[idf_hex][idf_var] = [
                {'description': process_desc(c.description), 'arity': c.arity, 'affixes': c.affixes} for c in cls
            ]

    return mcdict


def preprocess_cmcdict(compound_concepts):
    # description processor
    def process_math(math):

        def construct_mi(idf_text, idf_var, concept_id):
            mi = '<mi data-math-concept="{}"'.format(concept_id)

            if idf_var == 'roman':
                mi += ' mathvariant="normal">'
            else:
                mi += '>'

            mi += idf_text + '</mi>'

            return mi

        # protect references (@x)
        math = re.sub(r'(@\d+)', r'<mi>\1</mi>', math)

        # expand \gf
        rls = [
            (construct_mi(m.group(1), m.group(2), int(m.group(3))), m.span())
            for m in re.finditer(r'\\gf{(.*?)}{(.*?)}{(\d*?)}', math)
        ]
        for r in reversed(rls):
            s, e = r[1]
            math = math[:s] + r[0] + math[e:]

        return '<math>' + math + '</math>'

    def process_desc(desc):
        if not desc or '$' not in desc:
            return desc

        # process maths
        it = desc.split('$')
        desc_new = ''.join([a + process_math(b) for a, b in zip(it[::2], it[1::2])])
        if len(it) % 2 != 0:
            desc_new += it[-1]

        return desc_new

    # initialize
    cmcdict = dict()

    for cmc_id, cmc_obj in compound_concepts.items():
        cmcdict[cmc_id] = {
            'description': process_desc(cmc_obj.description),
            'arity': cmc_obj.arity,
            'primitive_concepts': cmc_obj.primitive_concepts}

    return cmcdict


class MioGattoServer:

    def __init__(self, paper_id: str, tree, mi_anno: MiAnno, mcdict: McDict, cmcdict: CmcDict,
                 logger: Logger, data_dir: str, sources_dir: str, available_ids: list):
        self.paper_id = paper_id
        self.tree = tree
        self.mi_anno = mi_anno
        self.mcdict = mcdict
        self.cmcdict = cmcdict
        self.logger = logger
        self.data_dir = data_dir
        self.sources_dir = sources_dir
        self.available_ids = available_ids

        with open('config.json', 'r') as f:
            self.config = json.load(f)

        # Start with 0 (can be considered as the number of times the mcdict is edited)
        self.mcdict_edit_id = 0
        self.cmcdict_edit_id = 0

    def list_sample_ids(self):
        data = {'available_ids': self.available_ids}
        return json.dumps(data, ensure_ascii=False, indent=4, sort_keys=True, separators=(',', ': '))
    
    def switch_to_sample(self, new_id):
        # Update internal state to switch to the new sample
        if new_id not in self.available_ids:
            flash(f'Sample ID {new_id} not found.')
            return redirect('/')

        # Update paper_id
        self.paper_id = new_id

        # Load new data
        anno_json = self.data_dir / '{}_anno.json'.format(new_id)
        mcdict_json = self.data_dir / '{}_mcdict.json'.format(new_id)
        cmcdict_json = self.data_dir / '{}_cmcdict.json'.format(new_id)
        source_html = self.sources_dir / '{}.html'.format(new_id)

        # load the data
        self.mi_anno = MiAnno(anno_json)
        self.mcdict = McDict(mcdict_json)
        self.cmcdict = CmcDict(cmcdict_json)
        self.tree = lxml.html.parse(str(source_html))

        # Start with 0 (can be considered as the number of times the mcdict is edited)
        ####### PROBABLY WRONG #################
        self.mcdict_edit_id = 0
        self.cmcdict_edit_id = 0

        return redirect('/')
    
    def annotate_file(self, filename):
        samples_source_folder = self.config["SAMPLE_SOURCE_FOLDER"]
        file_path = os.path.join(samples_source_folder, filename)
        
        # 1. Load the specific file content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 2. Pass content to the annotation template
        return render_template('annotation_page.html', file_content=content, current_file=filename)

    def add_data_compound_math_concept(self, root):
        for anno_tag_id, anno_obj in self.mi_anno.compound_occr.items():
            cmc_id = anno_obj.compound_concept_id
            if cmc_id is not None:
                xpath_expression = "//{}[@id='{}']".format(anno_obj.tag_name, anno_tag_id)
                matches = root.xpath(xpath_expression)
                if len(matches)!=1:
                    flash('Either no element matching {} found, or too many'.format(xpath_expression))
                    continue

                matches[0].attrib['data-compound-math-concept'] = str(cmc_id)

    def wrap_custom_group(self, root, group_id, group_info):

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
        
        start_id = group_info['start_id']
        stop_id = group_info['stop_id']
        ancestry_level_start = group_info.get('ancestry_level_start')
        ancestry_level_end = group_info.get('ancestry_level_end')

        parent_start_path_part = "/parent::*"*ancestry_level_start if ancestry_level_start is not None else ""
        parent_stop_path_part = "/parent::*"*ancestry_level_end if ancestry_level_end is not None else ""

        start_element_list = root.xpath("//*[@id='{}']{}".format(start_id, parent_start_path_part))
        start_element = start_element_list[0] if len(start_element_list)==1 else None
        stop_element_list = root.xpath("//*[@id='{}']{}".format(stop_id, parent_stop_path_part))
        stop_element = stop_element_list[0] if len(stop_element_list)==1 else None

        # # Find all elements between start_id and stop_id (inclusive)
        # xpath_expression = "//*[@id='{}']{}/following::*[preceding::*[@id='{}']{}]".format(
        #     start_id, parent_start_path_part, stop_id, parent_stop_path_part)
        # elements_in_group = root.xpath(xpath_expression)

        if start_element is None or stop_element is None:
            self.logger.warning('No elements found for group %s (%s to %s)', group_id, start_id, stop_id)
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

                
    def initialize_main_pages(self, root):

        # Wrap specified custom groups in span tags
        for group_id, group_info in self.mi_anno.groups.items():
            if not self.wrap_custom_group(root, group_id, group_info):
                continue

        # add data-math-concept for each mi element
        for mi in root.xpath('//mi'):
            mi_id = mi.get('id', None)
            if mi_id is None:
                continue

            concept_id = self.mi_anno.occr.get(mi_id, dict()).get('concept_id', None)
            if concept_id is None:
                continue

            mi.attrib['data-math-concept'] = str(concept_id)

        # add data-compound-math-concept for each compound concept element
        self.add_data_compound_math_concept(root)

        # progress info
        nof_anno = len(self.mi_anno.occr)
        nof_comp_anno = len(self.mi_anno.compound_occr)
        nof_done = sum(1 for v in self.mi_anno.occr.values() if not v['concept_id'] is None)
        nof_comp_done = sum(1 for v in self.mi_anno.compound_occr.values() if not v.compound_concept_id is None)
        p_concept = '{}/{} ({:.2f}%)'.format(nof_done, nof_anno, nof_done / nof_anno * 100)
        p_comp_concept = '{}/{} ({:.2f}%)'.format(nof_comp_done, nof_comp_anno, nof_comp_done / nof_comp_anno * 100)

        nof_sog = 0
        for anno in self.mi_anno.occr.values():
            for sog in anno['sog']:
                nof_sog += 1

        nof_comp_sog = 0
        for comp_anno in self.mi_anno.compound_occr.values():
            for comp_sog in comp_anno.sog:
                nof_comp_sog += 1

        return p_concept, p_comp_concept, nof_sog, nof_comp_sog

    def index(self):
        # avoid destroying the original tree
        copied_tree = deepcopy(self.tree)
        root = copied_tree.getroot()

        p_concept, p_comp_concept, nof_sog, nof_comp_sog = self.initialize_main_pages(root)

        # construction
        # title = root.xpath('//head/title')[0].text
        title = "deault title"
        body = root.xpath('body')[0]
        main_content = etree.tostring(body, method='html', encoding=str)

        return render_template(
            'index.html',
            title=title,
            version=VERSION,
            git_revision=GIT_REVISON,
            paper_id=self.paper_id,
            annotator=self.mi_anno.annotator,
            p_concept=p_concept,
            nof_sog=nof_sog,
            p_comp_concept=p_comp_concept,
            nof_comp_sog=nof_comp_sog,
            affixes=Markup(affixes_pulldowns()),
            main_content=Markup(main_content),
            compound_concept_tags=self.config['COMPOUND_CONCEPT_TAGS']
        )
    
    def edit_compound_concepts(self):
        # avoid destroying the original tree
        copied_tree = deepcopy(self.tree)
        root = copied_tree.getroot()

        p_concept, p_comp_concept, nof_sog, nof_comp_sog = self.initialize_main_pages(root)

        # construction
        body = root.xpath('body')[0]
        main_content = etree.tostring(body, method='html', encoding=str)
        return render_template(
            'compound_concepts_editor.html',
            version=VERSION,
            git_revision=GIT_REVISON,
            paper_id=self.paper_id,
            annotator=self.mi_anno.annotator,
            p_concept=p_concept,
            nof_sog=nof_sog,
            p_comp_concept=p_comp_concept,
            nof_comp_sog=nof_comp_sog,
            main_content=Markup(main_content),
            compound_concept_tags=self.config['COMPOUND_CONCEPT_TAGS']
        )

    def equations_of_interest_selector(self):
        # avoid destroying the original tree
        copied_tree = deepcopy(self.tree)
        root = copied_tree.getroot()

        p_concept, p_comp_concept, nof_sog, nof_comp_sog = self.initialize_main_pages(root)

        # construction
        body = root.xpath('body')[0]
        main_content = etree.tostring(body, method='html', encoding=str)
        return render_template(
            'equations_of_interest_selector.html',
            version=VERSION,
            git_revision=GIT_REVISON,
            paper_id=self.paper_id,
            annotator=self.mi_anno.annotator,
            p_concept=p_concept,
            nof_sog=nof_sog,
            p_comp_concept=p_comp_concept,
            nof_comp_sog=nof_comp_sog,
            main_content=Markup(main_content),
            compound_concept_tags=self.config['COMPOUND_CONCEPT_TAGS']
        )
    

    def group_creator(self):
        # avoid destroying the original tree
        copied_tree = deepcopy(self.tree)
        root = copied_tree.getroot()

        p_concept, p_comp_concept, nof_sog, nof_comp_sog = self.initialize_main_pages(root)

        # construction
        body = root.xpath('body')[0]
        main_content = etree.tostring(body, method='html', encoding=str)
        return render_template(
            'group_creator.html',
            version=VERSION,
            git_revision=GIT_REVISON,
            paper_id=self.paper_id,
            annotator=self.mi_anno.annotator,
            main_content=Markup(main_content),
            compound_concept_tags=self.config['COMPOUND_CONCEPT_TAGS']
        )
    
    def nav(self):
        return render_template(
            'nav.html',
        )
    
    def sample_nav(self):
        return render_template(
            'sample_nav.html',
        )

    def assign_concept(self):
        res = request.form

        # If the mcdict used in the request differs from the latest, then redirect (i.e., reload the page).
        edit_id_in_request = res.get('mcdict_edit_id')
        if edit_id_in_request is None or str(self.mcdict_edit_id) != edit_id_in_request:
            flash('Invalid Action!!! Reloading the page since the mcdict has been modified.')
            return redirect('/')

        mi_id = res['mi_id']
        concept_id = int(res['concept'])

        if res.get('concept'):
            # register
            self.mi_anno.occr[mi_id]['concept_id'] = concept_id
            self.mi_anno.dump()

        return redirect('/')

    def remove_concept(self):
        res = request.form

        # If the mcdict used in the request differs from the latest, then redirect (i.e., reload the page).
        edit_id_in_request = res.get('mcdict_edit_id')
        if edit_id_in_request is None or str(self.mcdict_edit_id) != edit_id_in_request:
            flash('Invalid Action!!! Reloading the page since the mcdict has been modified.')
            return redirect('/')

        mi_id = res['mi_id']
        self.mi_anno.occr[mi_id]['concept_id'] = None
        self.mi_anno.dump()

        return redirect('/')

    def new_concept(self):
        res = request.form

        # If the mcdict used in the request differs from the latest, then redirect (i.e., reload the page).
        edit_id_in_request = res.get('mcdict_edit_id')
        if edit_id_in_request is None or str(self.mcdict_edit_id) != edit_id_in_request:
            flash('Invalid Action!!! Reloading the page since the mcdict has been modified.')
            return redirect('/')

        idf_hex = res.get('idf_hex')
        idf_var = res.get('idf_var')

        # make concept with checking
        concept = make_concept(res)
        if concept is None:
            return redirect('/')

        # register
        self.mcdict.concepts[idf_hex][idf_var].append(concept)
        self.mcdict.dump()

        self.update_mcdict_edit_id()

        return redirect('/')

    def update_concept(self):
        # register and save data_anno
        res = request.form

        # If the mcdict used in the request differs from the latest, then redirect (i.e., reload the page).
        edit_id_in_request = res.get('mcdict_edit_id')
        if edit_id_in_request is None or str(self.mcdict_edit_id) != edit_id_in_request:
            flash('Invalid Action!!! Reloading the page since the mcdict has been modified.')
            return redirect('/')

        idf_hex = res.get('idf_hex')
        idf_var = res.get('idf_var')
        concept_id = int(res.get('concept_id'))

        # make concept with checking
        concept = make_concept(res)
        if concept is None:
            return redirect('/')

        self.mcdict.concepts[idf_hex][idf_var][concept_id] = concept
        self.mcdict.dump()

        self.update_mcdict_edit_id()

        return redirect('/')

    # Naive.
    def update_concept_for_edit_mcdict(self):
        # register and save data_anno
        res = request.form

        # If the mcdict used in the request differs from the latest, then redirect (i.e., reload the page).
        edit_id_in_request = res.get('mcdict_edit_id')
        if edit_id_in_request is None or str(self.mcdict_edit_id) != edit_id_in_request:
            flash('Invalid Action!!! Reloading the page since the mcdict has been modified.')
            return redirect('/edit_mcdict')

        idf_hex = res.get('idf_hex')
        idf_var = res.get('idf_var')
        concept_id = int(res.get('concept_id'))

        # make concept with checking
        concept = make_concept(res)
        if concept is None:
            return redirect('/edit_mcdict')

        self.mcdict.concepts[idf_hex][idf_var][concept_id] = concept
        self.mcdict.dump()

        self.update_mcdict_edit_id()

        return redirect('/edit_mcdict')

    def add_sog(self):
        res = request.form

        # If the mcdict used in the request differs from the latest, then redirect (i.e., reload the page).
        edit_id_in_request = res.get('mcdict_edit_id')
        if edit_id_in_request is None or str(self.mcdict_edit_id) != edit_id_in_request:
            flash('Invalid Action!!! Reloading the page since the mcdict has been modified.')
            return redirect('/')

        mi_id = res['mi_id']
        start_id, stop_id = res['start_id'], res['stop_id']

        # TODO: validate the span range
        existing_sog_pos = [(s['start'], s['stop']) for s in self.mi_anno.occr[mi_id]['sog']]
        if (start_id, stop_id) not in existing_sog_pos:
            self.mi_anno.occr[mi_id]['sog'].append({'start': start_id, 'stop': stop_id, 'type': 0})
            self.mi_anno.dump()

        return redirect('/')

    def delete_sog(self):
        res = request.form

        # If the mcdict used in the request differs from the latest, then redirect (i.e., reload the page).
        edit_id_in_request = res.get('mcdict_edit_id')
        if edit_id_in_request is None or str(self.mcdict_edit_id) != edit_id_in_request:
            flash('Invalid Action!!! Reloading the page since the mcdict has been modified.')
            return redirect('/')

        mi_id = res['mi_id']
        start_id, stop_id = res['start_id'], res['stop_id']

        delete_idx = None
        for idx, sog in enumerate(self.mi_anno.occr[mi_id]['sog']):
            if sog['start'] == start_id and sog['stop'] == stop_id:
                delete_idx = idx
                break

        if delete_idx is not None:
            del self.mi_anno.occr[mi_id]['sog'][delete_idx]
            self.mi_anno.dump()

        return redirect('/')

    def change_sog_type(self):
        res = request.form

        # If the mcdict used in the request differs from the latest, then redirect (i.e., reload the page).
        edit_id_in_request = res.get('mcdict_edit_id')
        if edit_id_in_request is None or str(self.mcdict_edit_id) != edit_id_in_request:
            flash('Invalid Action!!! Reloading the page since the mcdict has been modified.')
            return redirect('/')

        mi_id = res['mi_id']
        start_id, stop_id = res['start_id'], res['stop_id']
        sog_type = res['sog_type']

        for sog in self.mi_anno.occr[mi_id]['sog']:
            if sog['start'] == start_id and sog['stop'] == stop_id:
                sog['type'] = sog_type
                self.mi_anno.dump()
                break

        return redirect('/')

    def gen_mcdict_json(self):
        data = preprocess_mcdict(self.mcdict.concepts)

        extended_data = [str(self.mcdict_edit_id), data]

        return json.dumps(extended_data, ensure_ascii=False, indent=4, sort_keys=True, separators=(',', ': '))
    
    def assign_comp_concept(self):
        res = request.form

        # If the cmcdict used in the request differs from the latest, then redirect (i.e., reload the page).
        edit_id_in_request = res.get('cmcdict_edit_id')
        if edit_id_in_request is None or str(self.cmcdict_edit_id) != edit_id_in_request:
            flash('Invalid Action!!! Reloading the page since the cmcdict has been modified.')
            return redirect('/edit_compound_concepts')

        comp_tag_id = res['comp_tag_id']
        # cmc_id = int(res['cmc_id'])
        cmc_id = res['cmc_id']

        if res.get('cmc_id'):
            if comp_tag_id in self.mi_anno.compound_occr.keys():
                # Simply change concept ID
                self.mi_anno.compound_occr[comp_tag_id].compound_concept_id = cmc_id
            else:
                # Register new accurence entry
                tag_name = res['tag_name']
                self.mi_anno.compound_occr[comp_tag_id] = Occurence(cmc_id, [], tag_name)
            
            self.mi_anno.dump()

        return redirect('/edit_compound_concepts')
    
    def remove_comp_concept(self):
        res = request.form

        # If the cmcdict used in the request differs from the latest, then redirect (i.e., reload the page).
        edit_id_in_request = res.get('cmcdict_edit_id')
        if edit_id_in_request is None or str(self.cmcdict_edit_id) != edit_id_in_request:
            flash('Invalid Action!!! Reloading the page since the cmcdict has been modified.')
            return redirect('/edit_compound_concepts')

        comp_tag_id = res['comp_tag_id']
        self.mi_anno.compound_occr[comp_tag_id]['compound_concept_id'] = None
        self.mi_anno.dump()

        return redirect('/edit_compound_concepts')
    
    def new_comp_concept(self):
        res = request.form

        # If the cmcdict used in the request differs from the latest, then redirect (i.e., reload the page).
        edit_id_in_request = res.get('cmcdict_edit_id')
        if edit_id_in_request is None or str(self.cmcdict_edit_id) != edit_id_in_request:
            flash('Invalid Action!!! Reloading the page since the cmcdict has been modified.')
            return redirect('/edit_compound_concepts')

        # cmc_id = str(len(self.cmcdict.compound_concepts))
        cmc_id = str(self.cmcdict.next_available_cmc_id)

        # make compound concept with checking
        comp_concept = make_compound_concept(res)
        if comp_concept is None:
            return redirect('/edit_compound_concepts')

        # register
        self.cmcdict.compound_concepts[cmc_id] = comp_concept
        self.cmcdict.next_available_cmc_id += 1
        self.cmcdict.dump()

        self.update_cmcdict_edit_id()

        return redirect('/edit_compound_concepts')
    
    def update_comp_concept(self):
        # register and save data_anno
        res = request.form

        # If the cmcdict used in the request differs from the latest, then redirect (i.e., reload the page).
        edit_id_in_request = res.get('cmcdict_edit_id')
        if edit_id_in_request is None or str(self.cmcdict_edit_id) != edit_id_in_request:
            flash('Invalid Action!!! Reloading the page since the cmcdict has been modified.')
            return redirect('/edit_compound_concepts')

        cmc_id = res.get('cmc_id')

        # check arity
        if not res.get('arity').isdigit():
            flash('Arity must be non-negative integer.')
            return None
        else:
            arity = int(res.get('arity'))

        # check description
        description = res.get('description')
        if len(description) == 0:
            flash('Description must be filled.')
            return None

        self.cmcdict.compound_concepts[cmc_id].description = description
        self.cmcdict.compound_concepts[cmc_id].arity = arity
        self.cmcdict.dump()

        self.update_cmcdict_edit_id()

        return redirect('/edit_compound_concepts')
    
    def add_comp_sog(self):
        res = request.form

        # If the cmcdict used in the request differs from the latest, then redirect (i.e., reload the page).
        edit_id_in_request = res.get('cmcdict_edit_id')
        if edit_id_in_request is None or str(self.cmcdict_edit_id) != edit_id_in_request:
            flash('Invalid Action!!! Reloading the page since the cmcdict has been modified.')
            return redirect('/edit_compound_concepts')

        comp_tag_id = res['comp_tag_id']
        start_id, stop_id = res['start_id'], res['stop_id']

        # TODO: validate the span range
        existing_comp_sog_pos = [(s['start'], s['stop']) for s in self.mi_anno.compound_occr[comp_tag_id]['sog']]
        if (start_id, stop_id) not in existing_comp_sog_pos:
            self.mi_anno.compound_occr[comp_tag_id]['sog'].append({'start': start_id, 'stop': stop_id, 'type': 0})
            self.mi_anno.dump()

        return redirect('/edit_compound_concepts')
    
    def delete_comp_sog(self):
        res = request.form

        # If the cmcdict used in the request differs from the latest, then redirect (i.e., reload the page).
        edit_id_in_request = res.get('cmcdict_edit_id')
        if edit_id_in_request is None or str(self.cmcdict_edit_id) != edit_id_in_request:
            flash('Invalid Action!!! Reloading the page since the cmcdict has been modified.')
            return redirect('/edit_compound_concepts')

        comp_tag_id = res['comp_tag_id']
        start_id, stop_id = res['start_id'], res['stop_id']

        delete_idx = None
        for idx, sog in enumerate(self.mi_anno.compound_occr[comp_tag_id]['sog']):
            if sog['start'] == start_id and sog['stop'] == stop_id:
                delete_idx = idx
                break

        if delete_idx is not None:
            del self.mi_anno.compound_occr[comp_tag_id]['sog'][delete_idx]
            self.mi_anno.dump()

        return redirect('/edit_compound_concepts')
    
    def change_comp_sog_type(self):
        res = request.form

        # If the cmcdict used in the request differs from the latest, then redirect (i.e., reload the page).
        edit_id_in_request = res.get('cmcdict_edit_id')
        if edit_id_in_request is None or str(self.cmcdict_edit_id) != edit_id_in_request:
            flash('Invalid Action!!! Reloading the page since the cmcdict has been modified.')
            return redirect('/edit_compound_concepts')

        comp_tag_id = res['comp_tag_id']
        start_id, stop_id = res['start_id'], res['stop_id']
        sog_type = res['sog_type']

        for sog in self.mi_anno.compound_occr[comp_tag_id]['sog']:
            if sog['start'] == start_id and sog['stop'] == stop_id:
                sog['type'] = sog_type
                self.mi_anno.dump()
                break

        return redirect('/edit_compound_concepts')

    def add_eoi(self):
        res = request.form

        equation_id = res['equation_id']
        if not equation_id in self.mi_anno.eoi_list:
            self.mi_anno.eoi_list.append(equation_id)
        else:
            flash('Equation ID was already in the list of EoI.')
        self.mi_anno.dump()

        return redirect('/equations_of_interest_selector')
    
    def remove_eoi(self):
        res = request.form

        equation_id = res['equation_id']
        if equation_id in self.mi_anno.eoi_list:
            self.mi_anno.eoi_list.remove(equation_id)
        else:
            flash('Equation ID was not found in the list of EoI.')
        self.mi_anno.dump()

        return redirect('/equations_of_interest_selector')
    
    # def add_group(self):
    #     res = request.json

    #     element_ids = res.get('element_ids', '').split(',')
    #     if len(element_ids) < 2:
    #         return json.dumps({'status': 'error', 'message': 'Not enough elements to form a group.'}), 400

    #     # Generate a unique ID for the new group
    #     new_group_id = f"custom-group-{self.mi_anno.next_available_group_id}"

    #     # Register the new group in mi_anno.json file, then increment the ID counter
    #     self.mi_anno.groups[new_group_id] = {
    #         "element_ids": element_ids
    #     }
    #     self.mi_anno.next_available_group_id += 1

    #     self.mi_anno.compound_occr[new_group_id] = {
    #         "compound_concept_id": None,
    #         "sog": [],
    #         "tag_name": "span"
    #     }

    #     # Save the updated annotations
    #     self.mi_anno.dump()

    #     return redirect('/group_creator')
    
    def add_group(self):
        res = request.json

        # Generate a unique ID for the new group, then increment the ID counter
        new_group_id = f"custom-group-{self.mi_anno.next_available_group_id}"
        self.mi_anno.next_available_group_id += 1

        # Register the new group in mi_anno.json file within the groups section
        self.mi_anno.groups[new_group_id] = {
            "start_id": res.get('start_id'),
            "stop_id": res.get('stop_id'),
            "ancestry_level_start": res.get('ancestry_level_start'),
            "ancestry_level_stop": res.get('ancestry_level_stop'),
        }

        # Register in compound_occr as well
        self.mi_anno.compound_occr[new_group_id] = {
            "compound_concept_id": None,
            "sog": [],
            "tag_name": "mstyle"
        }

        # Save the updated annotations
        self.mi_anno.dump()

        success_message = {
            "status": "success",
            "message": "Group created successfully.",
            "group_id": new_group_id, 
        }

        return json.dumps(success_message), 200
    
    def remove_group(self):
        res = request.json

        group_id = res.get('group_id')

        # Delete the group from mi_anno.json file within the groups section
        del self.mi_anno.groups[group_id]

        # Delete from compound_occr as well
        del self.mi_anno.compound_occr[group_id]

        # Save the updated annotations
        self.mi_anno.dump()

        success_message = {
            "status": "success",
            "message": "Group removed successfully.",
            "group_id": group_id, 
        }

        return json.dumps(success_message), 200

    def gen_cmcdict_json(self):
        data = preprocess_cmcdict(self.cmcdict.compound_concepts)
        extended_data = [str(self.cmcdict_edit_id), data]
        return json.dumps(extended_data, ensure_ascii=False, indent=4, sort_keys=True, separators=(',', ': '))

    def gen_sog_json(self):
        data = {'sog': []}

        for mi_id, anno in self.mi_anno.occr.items():
            for sog in anno['sog']:
                data['sog'].append(
                    {'mi_id': mi_id, 'start_id': sog['start'], 'stop_id': sog['stop'], 'type': sog['type']}
                )

        return json.dumps(data, ensure_ascii=False, indent=4, sort_keys=True, separators=(',', ': '))
    
    def gen_comp_sog_json(self):
        data = {'sog': []}

        for comp_tag_id, anno in self.mi_anno.compound_occr.items():
            for sog in anno.sog:
                data['sog'].append(
                    {'comp_tag_id': comp_tag_id, 'start_id': sog['start'], 'stop_id': sog['stop'], 'type': sog['type']}
                )

        return json.dumps(data, ensure_ascii=False, indent=4, sort_keys=True, separators=(',', ': '))
    
    def gen_hex_to_cmc_map(self):
        data = {}
        for hex_value in self.mcdict.concepts.keys():
            data[hex_value] = []
        for cmc_id, cmc_obj in self.cmcdict.compound_concepts.items():
            for hex_value in cmc_obj.primitive_concepts:
                data[hex_value].append(cmc_id)
        return json.dumps(data, ensure_ascii=False, indent=4, sort_keys=True, separators=(',', ': '))
    
    def gen_eoi_json(self):
        data = {'eoi_list': []}
        for eoi_id in self.mi_anno.eoi_list:
            data['eoi_list'].append(eoi_id)
        return json.dumps(data, ensure_ascii=False, indent=4, sort_keys=True, separators=(',', ': '))
    
    def gen_groups_list_json(self):
        data = {'groups_list': []}
        for group_id, group_data in self.mi_anno.groups.items():
            data['groups_list'].append({
                "group_id": group_id,
                "element_ids": group_data.get("element_ids", [])
            })
        return json.dumps(data, ensure_ascii=False, indent=4, sort_keys=True, separators=(',', ': '))

    def edit_mcdict(self):
        # Copy and paste of index.
        # Need to add main_content to calculate statistics for identifiers and concepts.

        # avoid destroying the original tree
        copied_tree = deepcopy(self.tree)
        root = copied_tree.getroot()

        # add data-math-concept for each mi element
        for mi in root.xpath('//mi'):
            mi_id = mi.get('id', None)
            if mi_id is None:
                continue

            concept_id = self.mi_anno.occr.get(mi_id, dict()).get('concept_id', None)
            if concept_id is None:
                continue

            mi.attrib['data-math-concept'] = str(concept_id)

        # construction
        body = root.xpath('body')[0]
        main_content = etree.tostring(body, method='html', encoding=str)
        return render_template(
            'edit_mcdict.html',
            version=VERSION,
            git_revision=GIT_REVISON,
            paper_id=self.paper_id,
            annotator=self.mi_anno.annotator,
            affixes=Markup(affixes_pulldowns()),
            main_content=Markup(main_content),
        )
    
    def edit_cmcdict(self):
        pass

    def update_mcdict_edit_id(self):
        self.mcdict_edit_id += 1

    def update_cmcdict_edit_id(self):
        self.cmcdict_edit_id += 1