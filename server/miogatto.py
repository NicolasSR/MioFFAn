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
from dataclasses import asdict

from lib.version import VERSION
from lib.annotation import MiAnno, McDict
from lib.datatypes import MathConcept, Occurence, SoG, Group
from lib.util import check_missing_variables, check_document_edit_id

# get git revision
try:
    GIT_REVISON = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).strip().decode('ascii')
except OSError:
    GIT_REVISON = 'Unknown'


def make_concept(res) -> Optional[MathConcept]:
    # check tensor rank
    if not res.get('tensor_rank').isdigit():
        flash('Tensor rank must be non-negative integer.')
        return None
    else:
        tensor_rank = int(res.get('tensor_rank'))

    # check description
    description = res.get('description')
    if len(description) == 0:
        flash('Description must be filled.')
        return None

    # get affixes
    affixes = res.get('affixes')

    # Prepare empty list for SoGs
    sog_list = []

    primitive_symbols = res.get('primitive_symbols')

    return MathConcept(description, tensor_rank, affixes, sog_list, primitive_symbols)

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


def preprocess_mcdict(concepts: dict[str, MathConcept]):
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

    for mc_id, mc_obj in concepts.items():
        mcdict[mc_id] = {
            'description': process_desc(mc_obj.description),
            'tensor_rank': mc_obj.tensor_rank,
            'affixes': mc_obj.affixes,
            'primitive_symbols': mc_obj.primitive_symbols,
            'sog_list': [asdict(sog) for sog in mc_obj.sog_list]
        }

    return mcdict

class MioGattoServer:

    def __init__(self, paper_id: str, tree, mi_anno: MiAnno, mcdict: McDict,
                 logger: Logger, data_dir: str, sources_dir: str, available_ids: list):
        self.paper_id = paper_id
        self.tree = tree
        self.mi_anno = mi_anno
        self.mcdict = mcdict
        self.logger = logger
        self.data_dir = data_dir
        self.sources_dir = sources_dir
        self.available_ids = available_ids

        with open('config.json', 'r') as f:
            self.config = json.load(f)

        # Start with 0 (can be considered as the number of times the mcdict is edited)
        self.mi_anno_edit_id = 0
        self.mcdict_edit_id = 0

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
        source_html = self.sources_dir / '{}.html'.format(new_id)

        # load the data
        self.mi_anno = MiAnno(anno_json)
        self.mcdict = McDict(mcdict_json)
        self.tree = lxml.html.parse(str(source_html))

        # Start with 0 (can be considered as the number of times the mcdict is edited)
        ####### PROBABLY WRONG #################
        self.mi_anno_edit_id = 0
        self.mcdict_edit_id = 0

        return redirect('/')
    
    def annotate_file(self, filename):
        samples_source_folder = self.config["SAMPLE_SOURCE_FOLDER"]
        file_path = os.path.join(samples_source_folder, filename)
        
        # 1. Load the specific file content
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 2. Pass content to the annotation template
        return render_template('annotation_page.html', file_content=content, current_file=filename)

    def add_data_math_concept(self, root):
        for comp_tag_id, annotation_obj in self.mcdict.occurences.items():
            mc_id = annotation_obj.mc_id
            if mc_id is not None:
                xpath_expression = "//{}[@id='{}']".format(annotation_obj.tag_name, comp_tag_id)
                matches = root.xpath(xpath_expression)
                if len(matches)!=1:
                    flash('Either no element matching {} found, or too many'.format(xpath_expression))
                    continue

                matches[0].attrib['data-math-concept'] = str(mc_id)

    def wrap_custom_group(self, root, group_id, group_info: Group):

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

        # add data-math-concept for each annotated comp_tag element
        self.add_data_math_concept(root)
        
        # progress info
        nof_sog = 0
        for concept in self.mcdict.concepts.values():
            for sog in concept.sog_list:
                nof_sog += 1
        progress_dict = {
            'nof_eois': len(self.mi_anno.eoi_list),
            'nof_concepts': len(self.mcdict.concepts),
            'nof_occ': len(self.mcdict.occurences),
            'nof_sog': nof_sog
        }

        return progress_dict

    def index(self):
        # avoid destroying the original tree
        copied_tree = deepcopy(self.tree)
        root = copied_tree.getroot()

        progress_data = self.initialize_main_pages(root)

        # construction
        # title = root.xpath('//head/title')[0].text
        title = f"MioKrattos: {self.paper_id}"
        body = root.xpath('body')[0]
        main_content = etree.tostring(body, method='html', encoding=str)

        return render_template(
            'index.html',
            title=title,
            version=VERSION,
            git_revision=GIT_REVISON,
            paper_id=self.paper_id,
            annotator=self.mi_anno.annotator,
            progress_data=progress_data,
            affixes=Markup(affixes_pulldowns()),
            main_content=Markup(main_content),
            compound_concept_tags=self.config['COMPOUND_CONCEPT_TAGS']
        )

    def equations_of_interest_selector(self):
        # avoid destroying the original tree
        copied_tree = deepcopy(self.tree)
        root = copied_tree.getroot()

        progress_data = self.initialize_main_pages(root)

        # construction
        body = root.xpath('body')[0]
        main_content = etree.tostring(body, method='html', encoding=str)
        return render_template(
            'equations_of_interest_selector.html',
            version=VERSION,
            git_revision=GIT_REVISON,
            paper_id=self.paper_id,
            annotator=self.mi_anno.annotator,
            progress_data=progress_data,
            main_content=Markup(main_content),
            compound_concept_tags=self.config['COMPOUND_CONCEPT_TAGS']
        )
    

    def group_creator(self):
        # avoid destroying the original tree
        copied_tree = deepcopy(self.tree)
        root = copied_tree.getroot()

        _ = self.initialize_main_pages(root)

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
        res = request.json

        check_document_edit_id(self.mi_anno_edit_id, res.get('mi_anno_edit_id'))

        comp_tag_id = res.get('comp_tag_id')
        mc_id = res.get('mc_id')
        tag_name = res.get('tag_name')

        check_missing_variables([comp_tag_id,mc_id,tag_name])

        # register
        self.mcdict.occurences[comp_tag_id] = Occurence(mc_id, tag_name)
        self.mcdict.dump()

        self.update_mcdict_edit_id()

        success_message = {
            "status": "success",
            "message": "Concept assigned successfully."
        }

        return json.dumps(success_message), 200

    def remove_concept(self):
        res = request.json

        check_document_edit_id(self.mi_anno_edit_id, res.get('mi_anno_edit_id'))

        comp_tag_id = res.get('comp_tag_id')
        check_missing_variables([comp_tag_id])

        del self.mcdict.occurences[comp_tag_id]
        self.mcdict.dump()

        self.update_mcdict_edit_id()

        success_message = {
            "status": "success",
            "message": "Concept removed successfully."
        }

        return json.dumps(success_message), 200

    def new_concept(self):
        res = request.json

        check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))

        # make concept with checking
        concept = make_concept(res)
        check_missing_variables([concept])
        
        mc_id = str(self.mcdict.next_available_mc_id)

        # register
        self.mcdict.concepts[mc_id] = concept
        self.mcdict.next_available_mc_id += 1
        self.mcdict.dump()

        self.update_mcdict_edit_id()

        success_message = {
            "status": "success",
            "message": "Concept created successfully.",
            "mc_id": mc_id
        }

        return json.dumps(success_message), 200
    

    def update_concept(self):
        res = request.json

        check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))

        # make concept with checking
        concept = make_concept(res)
        check_missing_variables([concept])
        
        mc_id = res.get('mc_id')

        # register
        self.mcdict.concepts[mc_id] = concept
        self.mcdict.dump()

        self.update_mcdict_edit_id()

        success_message = {
            "status": "success",
            "message": "Concept updated successfully."
        }

        return json.dumps(success_message), 200

    def add_sog(self):
        res = request.json

        check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))
        
        mc_id = res['mc_id']
        start_id, stop_id = res['start_id'], res['stop_id']

        check_missing_variables([mc_id,start_id,stop_id])

        # TODO: validate the span range
        existing_sog_pos = [(s.start_id, s.stop_id) for s in self.mcdict.concepts[mc_id].sog_list]
        if (start_id, stop_id) not in existing_sog_pos:
            self.mcdict.concepts[mc_id].sog_list.append(SoG(start_id, stop_id, 0))
            self.mcdict.dump()

        self.update_mcdict_edit_id()
        
        success_message = {
            "status": "success",
            "message": "SoG added successfully."
        }

        return json.dumps(success_message), 200

    def delete_sog(self):
        res = request.json

        check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))

        mc_id = res['mc_id']
        start_id, stop_id = res['start_id'], res['stop_id']

        check_missing_variables([mc_id,start_id,stop_id])

        delete_idx = None
        for idx, sog in enumerate(self.mcdict.concepts[mc_id].sog_list):
            if sog.start_id == start_id and sog.stop_id == stop_id:
                delete_idx = idx
                break

        if delete_idx is not None:
            del self.mcdict.concepts[mc_id].sog_list[delete_idx]
            self.mcdict.dump()
        
        self.update_mcdict_edit_id()
        
        success_message = {
            "status": "success",
            "message": "SoG deleted successfully."
        }

        return json.dumps(success_message), 200

    def change_sog_type(self):
        res = request.json

        check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))

        mc_id = res['mc_id']
        start_id, stop_id = res['start_id'], res['stop_id']
        sog_type = res['sog_type']

        check_missing_variables([mc_id,start_id,stop_id,sog_type])

        for sog in self.mcdict.concepts[mc_id].sog_list:
            if sog.start_id == start_id and sog.stop_id == stop_id:
                sog.type = sog_type
                self.mcdict.dump()
                break

        self.update_mcdict_edit_id()
        
        success_message = {
            "status": "success",
            "message": "SoG added successfully."
        }

        return json.dumps(success_message), 200

    def gen_mcdict_json(self):
        data = preprocess_mcdict(self.mcdict.concepts)
        extended_data = [str(self.mcdict_edit_id), data]
        return json.dumps(extended_data, ensure_ascii=False, indent=4, sort_keys=True, separators=(',', ': '))
    
    def gen_mi_anno_json(self):
        data = {'eoi_list': []}
        for eoi_id in self.mi_anno.eoi_list:
            data['eoi_list'].append(eoi_id)
        extended_data = [str(self.mi_anno_edit_id), data]
        return json.dumps(extended_data, ensure_ascii=False, indent=4, sort_keys=True, separators=(',', ': '))

    def add_eoi(self):
        res = request.form

        equation_id = res['equation_id']
        if not equation_id in self.mi_anno.eoi_list:
            self.mi_anno.eoi_list.append(equation_id)
        else:
            flash('Equation ID was already in the list of EoI.')
        self.mi_anno.dump()

        self.update_mi_anno_edit_id()

        return redirect('/equations_of_interest_selector')
    
    def remove_eoi(self):
        res = request.form

        equation_id = res['equation_id']
        if equation_id in self.mi_anno.eoi_list:
            self.mi_anno.eoi_list.remove(equation_id)
        else:
            flash('Equation ID was not found in the list of EoI.')
        self.mi_anno.dump()

        self.update_mi_anno_edit_id()

        return redirect('/equations_of_interest_selector')
    
    def add_group(self):
        res = request.json

        # Generate a unique ID for the new group, then increment the ID counter
        new_group_id = f"custom-group-{self.mi_anno.next_available_group_id}"
        self.mi_anno.next_available_group_id += 1

        # Register the new group in mi_anno.json file within the groups section
        group_info = {
            "start_id": res.get('start_id'),
            "stop_id": res.get('stop_id'),
            "ancestry_level_start": res.get('ancestry_level_start'),
            "ancestry_level_stop": res.get('ancestry_level_stop'),
        }
        self.mi_anno.groups[new_group_id] = Group(**group_info)

        # Save the updated annotations
        self.mi_anno.dump()

        self.update_mi_anno_edit_id()

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

        # Save the updated annotations
        self.mi_anno.dump()

        self.update_mi_anno_edit_id()

        success_message = {
            "status": "success",
            "message": "Group removed successfully.",
            "group_id": group_id, 
        }

        return json.dumps(success_message), 200
    
    def gen_hex_to_mc_map(self):
        data = {}
        for mc_id, mc_obj in self.mcdict.concepts.items():
            for hex_value in mc_obj.primitive_symbols:
                if hex_value in data.keys():
                    data[hex_value].append(mc_id)
                else:
                    data[hex_value] = [mc_id]
        return json.dumps(data, ensure_ascii=False, indent=4, sort_keys=True, separators=(',', ': '))

    def edit_mcdict(self):
        # Copy and paste of index.
        # Need to add main_content to calculate statistics for identifiers and concepts.

        # avoid destroying the original tree
        copied_tree = deepcopy(self.tree)
        root = copied_tree.getroot()

        _ = self.initialize_main_pages(root)

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
            compound_concept_tags=self.config['COMPOUND_CONCEPT_TAGS']
        )

    def update_mi_anno_edit_id(self):
        self.mi_anno_edit_id += 1

    def update_mcdict_edit_id(self):
        self.mcdict_edit_id += 1