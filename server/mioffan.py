import json
import re
import os
from typing import Optional, List, Dict
from logging import Logger
from copy import deepcopy
import traceback
import shutil
from pathlib import Path

# The server implementation for MioGatto
from flask import request, redirect, flash, render_template, jsonify, Markup
import lxml
from lxml import etree
import subprocess
from dataclasses import asdict

from pydantic import BaseModel

from lib.version import VERSION
from lib.annotation import MiAnno, McDict
from lib.datatypes import MathConcept, Occurence, SoG, Group, EoI
from lib.util import wrap_custom_group, check_missing_variables, check_document_edit_id, PostRequestError
from lib.concept_properties import validate_properties
from llm_implementation.llm_implementations import auto_segment_symbols, auto_define_and_assign_concepts, auto_highlight_sources
from lib.llm_utilities import validate_llm_output_schema, get_or_create_llm_log_file, process_auto_segment_symbol_data

# get git revision
try:
    GIT_REVISON = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).strip().decode('ascii')
except OSError:
    GIT_REVISON = 'Unknown'
    
def make_concept(res,taxonomy_config,sog_list = []) -> Optional[MathConcept]:
    if not res.get('code_var_name').isidentifier():
        return None, f"Variable name must be compliant with Python identifier rules."

    code_var_name = res.get('code_var_name')

    # check description
    description = res.get('description')
    if len(description) == 0:
        return None, f"Description must be filled."
    
    category = res.get('concept_category')
    if category == "symbol-placeholder" and not category in taxonomy_config.keys():
        fields_config = {}
    else:
        fields_config = taxonomy_config[category].get('concept_fields', {})

    properties = res.get('properties')
    is_valid, error_msg = validate_properties(fields_config, properties)
    if not is_valid:
        return None, f"Logic Validation Failed: {error_msg}"

    primitive_symbols = res.get('primitive_symbols')

    return MathConcept(code_var_name, description, category, properties, sog_list, primitive_symbols), None


def preprocess_mcdict(concepts: dict[str, MathConcept]):
    # description processor
    def process_math(math):
        def construct_mi(idf_text, idf_var, concept_id):
            mi = '<mi data-mc-id="{}"'.format(concept_id)

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
            'code_var_name': mc_obj.code_var_name,
            'description': process_desc(mc_obj.description),
            'concept_category': mc_obj.concept_category,
            'properties': mc_obj.properties,
            'primitive_symbols': mc_obj.primitive_symbols,
            'sog_list': [asdict(sog) for sog in mc_obj.sog_list]
        }

    return mcdict

class MioFFAnServer:

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
        anno_json = self.data_dir / new_id / '{}_anno.json'.format(new_id)
        mcdict_json = self.data_dir / new_id / '{}_mcdict.json'.format(new_id)
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
        for comp_tag_id, annotation_obj in self.mcdict.occurences_dict.items():
            mc_id = annotation_obj.mc_id
            if mc_id is not None:
                xpath_expression = "//{}[@id='{}']".format(annotation_obj.tag_name, comp_tag_id)
                matches = root.xpath(xpath_expression)
                if len(matches)!=1:
                    flash('Either no element matching {} found, or too many'.format(xpath_expression))
                    continue

                matches[0].attrib['data-mc-id'] = str(mc_id)

                
    def initialize_main_pages(self, root):

        # Wrap specified custom groups in span tags
        for group_id, group_info in self.mi_anno.groups.items():
            if not wrap_custom_group(root, group_id, group_info):
                continue

        # add data-mc-id for each annotated comp_tag element
        self.add_data_math_concept(root)
        
        # progress info
        nof_sog = 0
        for concept in self.mcdict.concepts.values():
            for sog in concept.sog_list:
                nof_sog += 1
        progress_dict = {
            'nof_eois': len(self.mcdict.eoi_dict),
            'nof_concepts': len(self.mcdict.concepts),
            'nof_occ': len(self.mcdict.occurences_dict),
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
        style = root.xpath('head/style')[0]
        main_content_style = etree.tostring(style, method='html', encoding=str)

        return render_template(
            'index.html',
            title=title,
            version=VERSION,
            git_revision=GIT_REVISON,
            paper_id=self.paper_id,
            annotator=self.mi_anno.annotator,
            progress_data=progress_data,
            main_content=Markup(main_content),
            main_content_style=Markup(main_content_style),
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
        style = root.xpath('head/style')[0]
        main_content_style = etree.tostring(style, method='html', encoding=str)

        return render_template(
            'equations_of_interest_selector.html',
            version=VERSION,
            git_revision=GIT_REVISON,
            paper_id=self.paper_id,
            annotator=self.mi_anno.annotator,
            progress_data=progress_data,
            main_content=Markup(main_content),
            main_content_style=Markup(main_content_style),
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
        style = root.xpath('head/style')[0]
        main_content_style = etree.tostring(style, method='html', encoding=str)

        return render_template(
            'group_creator.html',
            version=VERSION,
            git_revision=GIT_REVISON,
            paper_id=self.paper_id,
            annotator=self.mi_anno.annotator,
            main_content=Markup(main_content),
            main_content_style=Markup(main_content_style),
            compound_concept_tags=self.config['COMPOUND_CONCEPT_TAGS']
        )
    
    def symbolic_code_assigner(self):
        # avoid destroying the original tree
        copied_tree = deepcopy(self.tree)
        root = copied_tree.getroot()

        progress_data = self.initialize_main_pages(root)

        # construction
        body = root.xpath('body')[0]
        main_content = etree.tostring(body, method='html', encoding=str)
        style = root.xpath('head/style')[0]
        main_content_style = etree.tostring(style, method='html', encoding=str)

        return render_template(
            'symbolic_code_assigner.html',
            version=VERSION,
            git_revision=GIT_REVISON,
            paper_id=self.paper_id,
            annotator=self.mi_anno.annotator,
            progress_data=progress_data,
            main_content=Markup(main_content),
            main_content_style=Markup(main_content_style),
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
        try:
            res = request.json

            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))

            comp_tag_id = res.get('comp_tag_id')
            mc_id = res.get('mc_id')
            tag_name = res.get('tag_name')

            check_missing_variables(comp_tag_id=comp_tag_id,mc_id=mc_id,tag_name=tag_name)

            self.assign_concept_inner(comp_tag_id, mc_id, tag_name)

            success_message = {
                "status": "success",
                "message": "Concept assigned successfully."
            }

            return json.dumps(success_message), 200
        
        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status
        
    def assign_concept_inner(self, comp_tag_id, mc_id, tag_name, options = []):
        # register
        self.mcdict.occurences_dict[comp_tag_id] = Occurence(mc_id, tag_name, options)
        self.mcdict.dump()
        self.update_mcdict_edit_id()

    def remove_concept(self):
        try:
            res = request.json

            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))

            comp_tag_id = res.get('comp_tag_id')
            check_missing_variables(comp_tag_id=comp_tag_id)

            del self.mcdict.occurences_dict[comp_tag_id]
            self.mcdict.dump()

            self.update_mcdict_edit_id()

            success_message = {
                "status": "success",
                "message": "Concept removed successfully."
            }

            return json.dumps(success_message), 200
        
        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status
    

    def register_concept(self):
        try:
            res = request.json

            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))

            is_successful, data = self.register_concept_inner(res, res.get('mc_id'))
            if not is_successful:
                raise PostRequestError(
                    code = "DATA_REGISTRATION_ERROR",
                    message = "Concept registration was not successful. "+str(data),
                    http_status = 400
                )
            
            mc_id = data

            success_message = {
                "status": "success",
                "message": "Concept registered successfully.",
                "mc_id": mc_id
            }

            return json.dumps(success_message), 200
        
        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status
        
    def register_concept_inner(self, concept_info, mc_id: str):
        if mc_id is None: # new concept
            if concept_info.get('concept_category')=="symbol-placeholder":
                code_var_name = concept_info["code_var_name"]
                concept_info['description']=f"Placeholder {code_var_name}"
                concept_info['properties']={}
            mc_id = str(self.mcdict.next_available_mc_id)
            self.mcdict.next_available_mc_id += 1
            sog_list = []
        else:
            mc_id = concept_info.get('mc_id')
            sog_list = self.mcdict.concepts[mc_id].sog_list

        # make concept with checking
        taxonomy_config = self.config.get('CONCEPT_TAXONOMY', {})
        concept, error_msg = make_concept(concept_info, taxonomy_config,sog_list=sog_list)
        if error_msg:
            return False, f"Failed to make concept: {error_msg}"

        check_missing_variables(concept=concept,mc_id=mc_id)

        # register
        self.mcdict.concepts[mc_id] = concept
        self.mcdict.dump()    

        self.update_mcdict_edit_id()

        return True, mc_id


    def add_sog(self):
        try:
            res = request.json

            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))
            
            mc_id = res['mc_id']
            start_id, stop_id = res['start_id'], res['stop_id']

            check_missing_variables(mc_id=mc_id,start_id=start_id,stop_id=stop_id)

            self.add_sog_inner(mc_id, start_id, stop_id)
            
            success_message = {
                "status": "success",
                "message": "SoG added successfully."
            }

            return json.dumps(success_message), 200
        
        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status
        
    def add_sog_inner(self, mc_id, start_id, stop_id):
            
        # TODO: validate the span range
        existing_sog_pos = [(s.start_id, s.stop_id) for s in self.mcdict.concepts[mc_id].sog_list]
        if (start_id, stop_id) not in existing_sog_pos:
            self.mcdict.concepts[mc_id].sog_list.append(SoG(start_id, stop_id, 0))
            self.mcdict.dump()

        self.update_mcdict_edit_id()
    

    def delete_sog(self):
        try:
            res = request.json

            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))

            mc_id = res['mc_id']
            start_id, stop_id = res['start_id'], res['stop_id']

            check_missing_variables(mc_id=mc_id,start_id=start_id,stop_id=stop_id)

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
        
        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status

    def change_sog_type(self):
        try:
            res = request.json

            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))

            mc_id = res['mc_id']
            start_id, stop_id = res['start_id'], res['stop_id']
            sog_type = res['sog_type']

            check_missing_variables(mc_id=mc_id,start_id=start_id,stop_id=stop_id,sog_type=sog_type)

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
        
        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status

    def gen_mcdict_json(self):
        data = dict()
        data['mcdict'] = preprocess_mcdict(self.mcdict.concepts)
        data['eoi_dict'] = {eoi_id: asdict(eoi_obj) for eoi_id, eoi_obj in self.mcdict.eoi_dict.items()}
        data['occurences_dict'] = {comp_tag_id: asdict(occ_obj) for comp_tag_id, occ_obj in self.mcdict.occurences_dict.items()}
        extended_data = [str(self.mcdict_edit_id), data]
        return json.dumps(extended_data, ensure_ascii=False, indent=4, sort_keys=True, separators=(',', ': '))
    
    def gen_mi_anno_json(self):
        data = {}
        extended_data = [str(self.mi_anno_edit_id), data]
        return json.dumps(extended_data, ensure_ascii=False, indent=4, sort_keys=True, separators=(',', ': '))
    
    def get_sample_info(self):
        data = {"sample_name": self.paper_id}
        return json.dumps(data, ensure_ascii=False, indent=4, sort_keys=True, separators=(',', ': '))

    def add_eoi(self):
        res = request.form

        equation_id = res['equation_id']
        if not equation_id in self.mcdict.eoi_dict.keys():
            self.mcdict.eoi_dict[equation_id] = EoI(symbolic_code="")
        else:
            flash('Equation ID was already in the list of EoI.')
        self.mcdict.dump()

        self.update_mcdict_edit_id()

        return redirect('/equations_of_interest_selector')
    
    def remove_eoi(self):
        res = request.form

        equation_id = res['equation_id']
        if equation_id in self.mcdict.eoi_dict.keys():
            del self.mcdict.eoi_dict[equation_id]
        else:
            flash('Equation ID was not found in the list of EoI.')
        self.mcdict.dump()

        self.update_mcdict_edit_id()

        return redirect('/equations_of_interest_selector')
    
    def add_group(self):
        try:
            res = request.json

            check_document_edit_id(self.mi_anno_edit_id, res.get('mi_anno_edit_id'))

            # Register the new group in mi_anno.json file within the groups section
            # The processing from set of ids to group info should be handled by the server.
            group_info = {
                "start_id": res.get('start_id'),
                "stop_id": res.get('stop_id'),
                "ancestry_level_start": res.get('ancestry_level_start'),
                "ancestry_level_stop": res.get('ancestry_level_stop'),
            }

            is_successful, data = self.add_group_inner(group_info)
            if not is_successful:
                raise PostRequestError(
                    code = "DATA_REGISTRATION_ERROR",
                    message = "Group registration was not successful. "+str(data),
                    http_status = 400
                )
            new_group_id = data

            success_message = {
                "status": "success",
                "message": "Group created successfully.",
                "group_id": new_group_id, 
            }

            return json.dumps(success_message), 200
        
        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status
        
    def add_group_inner(self, group_info):
        # Generate a unique ID for the new group, then increment the ID counter
        try:
            new_group_id = f"custom-group-{self.mi_anno.next_available_group_id}"
            self.mi_anno.groups[new_group_id] = Group(**group_info)
        except:
            return False, f"Failed to cast group information into Group object."

        self.mi_anno.next_available_group_id += 1

        # Save the updated annotations
        self.mi_anno.dump()

        self.update_mi_anno_edit_id()

        return True, new_group_id
    
    def remove_group(self):
        try:
            res = request.json

            check_document_edit_id(self.mi_anno_edit_id, res.get('mi_anno_edit_id'))

            group_id = res.get('group_id')

            check_missing_variables(group_id=group_id)

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
        
        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status
    
    def edit_symbolic_code(self):
        try:
            res = request.json

            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))

            eoi_id = res.get('eoi_id')
            symbolic_code = res.get('symbolic_code')

            check_missing_variables(eoi_id=eoi_id,symbolic_code=symbolic_code)
            
            if eoi_id in self.mcdict.eoi_dict.keys():
                self.mcdict.eoi_dict[eoi_id].symbolic_code = symbolic_code
                self.mcdict.dump()
            else:
                flash('Equation ID was not found in the list of EoI.')

            self.update_mcdict_edit_id()

            success_message = {
                "status": "success",
                "message": "Symbolic code updated successfully."
            }
            return json.dumps(success_message), 200
        
        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status
    
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
            main_content=Markup(main_content),
            compound_concept_tags=self.config['COMPOUND_CONCEPT_TAGS']
        )

    def get_occurence_properties_options_html(self):
        try:
            comp_tag_id = request.args.get('comp_tag_id', '')

            if comp_tag_id not in self.mcdict.occurences_dict:
                raise PostRequestError(
                    code="INVALID_IDENTIFIER",
                    message=f"Identifier comp_tag_id: {comp_tag_id} missing in internal occurences dictionary.",
                    http_status=404
                )
            
            occurence = self.mcdict.occurences_dict[comp_tag_id]
            concept = self.mcdict.concepts.get(occurence.mc_id, None)
            if concept is None:
                raise PostRequestError(
                    code="INVALID_IDENTIFIER",
                    message=f"Identifier mc_id: {occurence.mc_id} did not yield a valid concept object.",
                    http_status=404
                )
            
            out_html = build_occurence_properties_options_html(concept.tensor_rank,occurence.options)
            
            success_message = {
                    "status": "success",
                    "message": "Occurence properties options HTML generated successfully.",
                    "out_html": out_html
                }
            
            return json.dumps(success_message), 200
        
        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status
        
    def edit_occurence_properties(self):
        try:
            res = request.json

            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))

            comp_tag_id = res.get('comp_tag_id')
            properties = res.get('properties')

            check_missing_variables(comp_tag_id=comp_tag_id,properties=properties)


            concept = self.mcdict.concepts[self.mcdict.occurences_dict[comp_tag_id].mc_id]
            concept_category = concept.concept_category
            concept_properties = concept.properties
            taxonomy_config = self.config.get('CONCEPT_TAXONOMY', {})
            fields_config = taxonomy_config[concept_category].get('occurrence_fields', {})

            total_properties = properties.copy()
            total_properties.update(concept_properties)
            is_valid, error_msg = validate_properties(fields_config, total_properties)
            if not is_valid:
                raise PostRequestError(
                        code="INVALID_PROPERTY",
                        message=error_msg,
                        http_status=404
                    )
            
            self.mcdict.occurences_dict[comp_tag_id].properties = properties
            self.mcdict.dump()

            self.update_mcdict_edit_id()

            success_message = {
                "status": "success",
                "message": "Occurence properties edited successfully."
            }
            return json.dumps(success_message), 200
        
        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status
        

    def get_concept_properties_options_html(self):
        try:
            mc_id = request.args.get('mc_id', '')
            tensor_rank = request.args.get('tensor_rank', '')

            if mc_id != '':
                if mc_id not in self.mcdict.concepts:
                    raise PostRequestError(
                        code="INVALID_IDENTIFIER",
                        message=f"Identifier mc_id: {mc_id} missing in internal concepts dictionary.",
                        http_status=404
                    )
            
                concept = self.mcdict.concepts.get(mc_id, None)
                if concept is None:
                    raise PostRequestError(
                        code="INVALID_IDENTIFIER",
                        message=f"Identifier mc_id: {mc_id} did not yield a valid concept object.",
                        http_status=404
                    )
                
                previous_options = concept.options
            else:
                previous_options = []
            
            out_html = build_concept_properties_options_html(tensor_rank, previous_options)
            
            success_message = {
                    "status": "success",
                    "message": "Occurence properties options HTML generated successfully.",
                    "out_html": out_html
                }
            
            return json.dumps(success_message), 200
        
        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status
    
    
    #############################
    # LLM UTILITIES
    #############################

    def auto_segment_symbols(self):
        """
        This method acts only as an interface, providing proper input and validating output structure (as
        in output_schema variable and integrating output onto MioFFAn annotations.
        Then, the developer is supposed to implement functionality within the function with the same name
        in llm_implementation
        A JSON log file is generated here so that the user may save intermediate results.
        """

        class NewGroupDefinitionSchema(BaseModel):
            symbol_name:str
            included_mi_ids: List[str]
        
        class NewOccurrenceDefinitionSchema(BaseModel):
            symbol_name: str
            comp_tag_id: str

        class ExpectedOutputSchema(BaseModel):
            new_groups: List[NewGroupDefinitionSchema]
            new_occurrences: List[NewOccurrenceDefinitionSchema]

        schema_json = ExpectedOutputSchema.model_json_schema()
        with open('llm_implementation/documentation/auto_segment_symbols_schema.json', 'w') as f:
            json.dump(schema_json, f, indent=4, sort_keys=True, separators=(',', ': '))

        log_file = get_or_create_llm_log_file(self.paper_id)
        
        try:
            res = request.json
            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))
            check_document_edit_id(self.mi_anno_edit_id, res.get('mi_anno_edit_id'))

            dom_tree_copy = deepcopy(self.tree.xpath("//body")[0])
            mcdict_copy = deepcopy(self.mcdict)
            mi_anno_copy = deepcopy(self.mi_anno)

            result_dict = auto_segment_symbols(dom_tree_copy, mcdict_copy, mi_anno_copy, llm_log_file=log_file)

            # Validate structure of output from external implementation
            is_valid, validation_res = validate_llm_output_schema(result_dict, ExpectedOutputSchema)
            if not is_valid:
                raise PostRequestError(
                    code = "OUTPUT_VALIDATION_ERROR",
                    message = "Automation output does not match the required schema."+str(validation_res),
                    http_status = 400
                )
            
            new_concepts_dict, new_groups_dict, new_occurrences_dict = process_auto_segment_symbol_data(dom_tree_copy, validation_res)
            
            mc_ids_map = dict()
            for symbol_name, concept_info in new_concepts_dict.items():
                is_successful, data = self.register_concept_inner(concept_info, None)
                if not is_successful:
                    raise PostRequestError(
                        code = "DATA_REGISTRATION_ERROR",
                        message = "Concept registration was not successful. "+str(data),
                        http_status = 400
                    )
                mc_ids_map[symbol_name] = data

            for symbol_name, group_info_list in new_groups_dict.items():
                for group_info in group_info_list:
                    is_successful, data = self.add_group_inner(group_info)
                    if not is_successful:
                        raise PostRequestError(
                            code = "DATA_REGISTRATION_ERROR",
                            message = "Group registration was not successful. "+str(data),
                            http_status = 400
                        )
                    self.assign_concept_inner(data, mc_ids_map[symbol_name], "mstyle")
                
            for symbol_name, occurrence_info_list in new_occurrences_dict.items():
                for occurrence_info in occurrence_info_list:
                    comp_tag_id = occurrence_info["comp_tag_id"]
                    tag_name = occurrence_info["tag_name"]
                    self.assign_concept_inner(comp_tag_id, mc_ids_map[symbol_name], tag_name)
            
            success_message = {
                    "status": "success",
                    "message": "Automatic symbol segmentation successful.",
                }
                
            return json.dumps(success_message), 200

        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status
        except Exception as e:
            traceback.print_exc()
            error = PostRequestError(
                code="UNKNOWN",
                message=f"Error during Automatic Symbols Segmentation",
                http_status=400)
            return json.dumps(error.to_dict()), error.http_status
    
    def auto_assign_concepts(self):
        """
        This method acts only as an interface, providing proper input and validating output structure (as
        in output_schema variable and integrating output onto MioFFAn annotations.
        Then, the developer is supposed to implement functionality within the function with the same name
        in llm_implementation
        A JSON log file is generated here so that the user may save intermediate results.
        """

        class NewConceptsDefinitionSchema(BaseModel):
            code_var_name: str
            description: str
            concept_category: str
            properties: Dict[str, str]

        class NewConceptsMapSchema(BaseModel):
            original_mc_ids: List[str]
            new_concept_info: NewConceptsDefinitionSchema
        
        class ExpectedOutputSchema(BaseModel):
            concepts_info_list: List[NewConceptsMapSchema]

        schema_json = ExpectedOutputSchema.model_json_schema()
        with open('llm_implementation/documentation/auto_assign_concepts_schema.json', 'w') as f:
            json.dump(schema_json, f, indent=4, sort_keys=True, separators=(',', ': '))

        log_file = get_or_create_llm_log_file(self.paper_id)

        try:
            res = request.json
            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))
            check_document_edit_id(self.mi_anno_edit_id, res.get('mi_anno_edit_id'))
            
            dom_tree_copy = deepcopy(self.tree.xpath("//body")[0])
            mcdict_copy = deepcopy(self.mcdict)
            mi_anno_copy = deepcopy(self.mi_anno)

            result_dict = auto_define_and_assign_concepts(dom_tree_copy, mcdict_copy, mi_anno_copy, llm_log_file=log_file)

            # Validate structure of output from external implementation
            is_valid, validation_res = validate_llm_output_schema(result_dict, ExpectedOutputSchema)
            if not is_valid:
                raise PostRequestError(
                    code = "OUTPUT_VALIDATION_ERROR",
                    message = "Automation output does not match the required schema."+str(validation_res),
                    http_status = 400
                )

            concepts_and_assignments_list = validation_res["concepts_info_list"]
            for concepts_and_assignment in concepts_and_assignments_list:
                original_mc_ids = concepts_and_assignment["original_mc_ids"]
                new_primitive_symbols_set = set()
                for mc_id in original_mc_ids:
                    new_primitive_symbols_set.update(set(self.mcdict.concepts[mc_id].primitive_symbols))
                new_concept_info = concepts_and_assignment["new_concept_info"]
                new_concept_info["primitive_symbols"] = list(new_primitive_symbols_set)
                new_concept_info["sog_list"] = []
                is_successful, data = self.register_concept_inner(new_concept_info, None)
                if not is_successful:
                    raise PostRequestError(
                        code = "DATA_REGISTRATION_ERROR",
                        message = "Concept registration was not successful. "+str(data),
                        http_status = 400
                    )
                new_mc_id = data
                for original_mc_id in original_mc_ids:
                    for occurrence_id, occurence_info in self.mcdict.occurences_dict.items():
                        if occurence_info.mc_id==original_mc_id:
                            comp_tag_id = occurrence_id
                            tag_name = occurence_info.tag_name
                            self.assign_concept_inner(comp_tag_id, new_mc_id, tag_name)

            success_message = {
                    "status": "success",
                    "message": "Automatic assignment of concepts successful.",
                }
                
            return json.dumps(success_message), 200
        
        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status
        

    def auto_highlight_sources(self):
        """
        This method acts only as an interface, providing proper input and validating output structure (as
        in output_schema variable and integrating output onto MioFFAn annotations.
        Then, the developer is supposed to implement functionality within the function with the same name
        in llm_implementation
        A JSON log file is generated here so that the user may save intermediate results.
        """
        class NewSoGsInfoSchema(BaseModel):
            mc_id: str
            start_id: str
            stop_id: str
        
        class ExpectedOutputSchema(BaseModel):
            sogs_info_list: List[NewSoGsInfoSchema]

        schema_json = ExpectedOutputSchema.model_json_schema()
        with open('llm_implementation/documentation/auto_highlight_sources_schema.json', 'w') as f:
            json.dump(schema_json, f, indent=4, sort_keys=True, separators=(',', ': '))
        
        log_file = get_or_create_llm_log_file(self.paper_id)
        try:
            res = request.json
            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))
            check_document_edit_id(self.mi_anno_edit_id, res.get('mi_anno_edit_id'))

            dom_tree_copy = deepcopy(self.tree.xpath("//body")[0])
            mcdict_copy = deepcopy(self.mcdict)
            mi_anno_copy = deepcopy(self.mi_anno)

            result_dict = auto_highlight_sources(dom_tree_copy, mcdict_copy, mi_anno_copy, llm_log_file=log_file)

            # Validate structure of output from external implementation
            is_valid, validation_res = validate_llm_output_schema(result_dict, ExpectedOutputSchema)
            if not is_valid:
                raise PostRequestError(
                    code = "OUTPUT_VALIDATION_ERROR",
                    message = "Automation output does not match the required schema."+str(validation_res),
                    http_status = 400
                )

            for new_sog in validation_res["sogs_info_list"]:
                self.add_sog_inner(new_sog["mc_id"],new_sog["start_id"],new_sog["stop_id"])

            success_message = {
                    "status": "success",
                    "message": "Automatic assignment of concepts successful.",
                }
            
            return json.dumps(success_message), 200
        
        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status


    #############################
    # CHECKPOINT HANDLING
    #############################

    def create_data_checkpoint(self):
        try:
            res = request.json
            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))
            check_document_edit_id(self.mi_anno_edit_id, res.get('mi_anno_edit_id'))

            checkpoint_tag = res.get('checkpoint_tag')
            check_missing_variables(checkpoint_tag=checkpoint_tag)
            if checkpoint_tag == "":
                raise PostRequestError(
                    code = "VALUE_ERROR",
                    message = "Checkpoint tag is empty",
                    http_status = 400
                )
            
            self.mcdict.dump(checkpoint_tag)
            self.mi_anno.dump(checkpoint_tag)
            
            llm_log_path = self.mcdict.file.with_stem(re.sub("_mcdict", "_llm_log", self.mcdict.file.stem))
            if llm_log_path.is_file():
                target_llm_log_path = llm_log_path.with_stem(llm_log_path.stem + "_" + checkpoint_tag)
                shutil.copyfile(llm_log_path, target_llm_log_path)

            success_message = {
                    "status": "success",
                    "message": "Checkpointing of current annotations successful.",
                }
            
            return json.dumps(success_message), 200

        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status
        

    def clear_annotation_data(self):
        try:
            res = request.json
            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))
            check_document_edit_id(self.mi_anno_edit_id, res.get('mi_anno_edit_id'))

            data_mcdict_path = self.mcdict.file
            data_anno_path = self.mi_anno.file
            data_llm_log_path = self.mcdict.file.with_stem(re.sub("_mcdict", "_llm_log", self.mcdict.file.stem))

            checkpoint_tag = res.get("checkpoint_tag")

            if checkpoint_tag is None:
                target_mc_dict_path = Path("templates", data_mcdict_path.parts[-2], data_mcdict_path.name)
                target_anno_path = Path("templates", data_mcdict_path.parts[-2], data_anno_path.name)
            elif any(char.isalnum() for char in checkpoint_tag): # Check if there are alphanumeric values in the tag
                target_mc_dict_path = data_mcdict_path.with_stem(data_mcdict_path.stem + "_" + checkpoint_tag)
                target_anno_path = data_anno_path.with_stem(data_anno_path.stem + "_" + checkpoint_tag)
                subst_string = f"_llm_log_{checkpoint_tag}"
                target_llm_log_path = self.mcdict.file.with_stem(re.sub("_mcdict", subst_string, self.mcdict.file.stem))
            else:
                raise PostRequestError(
                    code = "VALUE_ERROR",
                    message = "Checkpoint tag is not valid",
                    http_status = 400
                )

            shutil.copyfile(target_mc_dict_path,data_mcdict_path)
            shutil.copyfile(target_anno_path,data_anno_path)

            if data_llm_log_path.is_file():
                data_llm_log_path.unlink()
            if checkpoint_tag is not None and target_llm_log_path.is_file():
                shutil.copyfile(target_llm_log_path, data_llm_log_path)

            success_message = {
                    "status": "success",
                    "message": "Annotations clearing successful.",
                }
            
            return json.dumps(success_message), 200

        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status


    #############################
    # EDIT ID UPDATERS
    #############################

    def update_mi_anno_edit_id(self):
        self.mi_anno_edit_id += 1

    def update_mcdict_edit_id(self):
        self.mcdict_edit_id += 1