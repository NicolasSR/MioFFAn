import json
import os
import traceback
import io
from typing import Optional, List, Dict
from logging import Logger
from copy import deepcopy
from pathlib import Path

from flask import request, redirect, flash, render_template, jsonify, Markup, send_file
import lxml

from lib.version import VERSION
from lib.annotation import MiAnno, McDict
from lib.datatypes import MathConcept, Occurence, SoG, Group, EoI, EnvironmentSetting
from lib.util import wrap_custom_group, check_missing_variables, check_document_edit_id, PostRequestError

from server.services import (
    AnnotationService,
    LLMService,
    CASService,
    CheckpointService,
    RenderService,
    ValidationService,
    gen_mcdict_json,
    gen_mi_anno_json,
    gen_hex_to_mc_map,
    get_sample_info,
)
from server.services.annotation_service import make_concept
import server.services.render_service as render_service_module

# get git revision
try:
    import subprocess
    GIT_REVISON = subprocess.check_output(['git', 'rev-parse', '--short', 'HEAD']).strip().decode('ascii')
except OSError:
    GIT_REVISON = 'Unknown'

render_service_module.GIT_REVISON = GIT_REVISON


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

        self.mi_anno_edit_id = 0
        self.mcdict_edit_id = 0

        self.kratos_templates = dict()
        self.kratos_output_files = dict()

        # Instantiate services
        self.annotation_svc = AnnotationService(
            mi_anno=mi_anno,
            mcdict=mcdict,
            config=self.config,
            mi_anno_edit_id_getter=lambda: self.mi_anno_edit_id,
            mcdict_edit_id_getter=lambda: self.mcdict_edit_id,
            mi_anno_edit_id_incrementer=self.update_mi_anno_edit_id,
            mcdict_edit_id_incrementer=self.update_mcdict_edit_id,
        )

        self.llm_svc = LLMService(
            mi_anno=mi_anno,
            mcdict=mcdict,
            tree=tree,
            config=self.config,
            paper_id=paper_id,
            annotation_service=self.annotation_svc,
        )

        self.cas_svc = CASService(
            kratos_templates=self.kratos_templates,
            kratos_output_files=self.kratos_output_files,
            mcdict=mcdict,
            paper_id=paper_id,
        )

        self.checkpoint_svc = CheckpointService(
            mi_anno=mi_anno,
            mcdict=mcdict,
        )

        self.render_svc = RenderService(
            tree=tree,
            mi_anno=mi_anno,
            mcdict=mcdict,
            config=self.config,
            paper_id=paper_id,
        )

        self.validation_svc = ValidationService(
            mcdict=mcdict,
            config=self.config,
        )

    # ---- Sample switching ----

    def list_sample_ids(self):
        data = {'available_ids': self.available_ids}
        return json.dumps(data, ensure_ascii=False, indent=4, sort_keys=True, separators=(',', ': '))

    def switch_to_sample(self, new_id):
        if new_id not in self.available_ids:
            flash(f'Sample ID {new_id} not found.')
            return redirect('/')

        self.paper_id = new_id

        anno_json = self.data_dir / new_id / '{}_anno.json'.format(new_id)
        mcdict_json = self.data_dir / new_id / '{}_mcdict.json'.format(new_id)
        source_html = self.sources_dir / '{}.html'.format(new_id)

        self.mi_anno = MiAnno(anno_json)
        self.mcdict = McDict(mcdict_json)
        self.tree = lxml.html.parse(str(source_html))

        self.mi_anno_edit_id = 0
        self.mcdict_edit_id = 0

        # Re-instantiate services with new state
        self._reinit_services()

        return redirect('/')

    def _reinit_services(self):
        self.annotation_svc = AnnotationService(
            mi_anno=self.mi_anno,
            mcdict=self.mcdict,
            config=self.config,
            mi_anno_edit_id_getter=lambda: self.mi_anno_edit_id,
            mcdict_edit_id_getter=lambda: self.mcdict_edit_id,
            mi_anno_edit_id_incrementer=self.update_mi_anno_edit_id,
            mcdict_edit_id_incrementer=self.update_mcdict_edit_id,
        )
        self.llm_svc = LLMService(
            mi_anno=self.mi_anno,
            mcdict=self.mcdict,
            tree=self.tree,
            config=self.config,
            paper_id=self.paper_id,
            annotation_service=self.annotation_svc,
        )
        self.cas_svc = CASService(
            kratos_templates=self.kratos_templates,
            kratos_output_files=self.kratos_output_files,
            mcdict=self.mcdict,
            paper_id=self.paper_id,
        )
        self.checkpoint_svc = CheckpointService(
            mi_anno=self.mi_anno,
            mcdict=self.mcdict,
        )
        self.render_svc = RenderService(
            tree=self.tree,
            mi_anno=self.mi_anno,
            mcdict=self.mcdict,
            config=self.config,
            paper_id=self.paper_id,
        )
        self.validation_svc = ValidationService(
            mcdict=self.mcdict,
            config=self.config,
        )

    def annotate_file(self, filename):
        samples_source_folder = self.config["SAMPLE_SOURCE_FOLDER"]
        file_path = os.path.join(samples_source_folder, filename)

        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        return render_template('annotation_page.html', file_content=content, current_file=filename)

    # ---- Page rendering (delegated) ----

    def index(self):
        return self.render_svc.index()

    def equations_of_interest_selector(self):
        return self.render_svc.equations_of_interest_selector()

    def group_creator(self):
        return self.render_svc.group_creator()

    def symbolic_code_assigner(self):
        return self.render_svc.symbolic_code_assigner()

    def nav(self):
        return self.render_svc.nav()

    def sample_nav(self):
        return self.render_svc.sample_nav()

    def edit_mcdict(self):
        return self.render_svc.edit_mcdict()

    # ---- Annotation CRUD (delegated) ----

    def assign_concept(self):
        try:
            res = request.json
            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))

            comp_tag_id = res.get('comp_tag_id')
            mc_id = res.get('mc_id')
            tag_name = res.get('tag_name')

            check_missing_variables(comp_tag_id=comp_tag_id, mc_id=mc_id, tag_name=tag_name)

            result = self.annotation_svc.assign_concept(comp_tag_id, mc_id, tag_name)

            return json.dumps(result), 200

        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status

    def remove_concept(self):
        try:
            res = request.json
            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))

            comp_tag_id = res.get('comp_tag_id')
            check_missing_variables(comp_tag_id=comp_tag_id)

            result = self.annotation_svc.remove_concept(comp_tag_id)

            return json.dumps(result), 200

        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status

    def register_concept(self):
        try:
            res = request.json
            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))

            result = self.annotation_svc.register_concept(res, res.get('mc_id'))

            return json.dumps(result), 200

        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status

    def add_sog(self):
        try:
            res = request.json
            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))

            mc_id = res['mc_id']
            start_id, stop_id = res['start_id'], res['stop_id']

            check_missing_variables(mc_id=mc_id, start_id=start_id, stop_id=stop_id)

            result = self.annotation_svc.add_sog(mc_id, start_id, stop_id)

            return json.dumps(result), 200

        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status

    def delete_sog(self):
        try:
            res = request.json
            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))

            mc_id = res['mc_id']
            start_id, stop_id = res['start_id'], res['stop_id']

            check_missing_variables(mc_id=mc_id, start_id=start_id, stop_id=stop_id)

            result = self.annotation_svc.delete_sog(mc_id, start_id, stop_id)

            return json.dumps(result), 200

        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status

    def change_sog_type(self):
        try:
            res = request.json
            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))

            mc_id = res['mc_id']
            start_id, stop_id = res['start_id'], res['stop_id']
            sog_type = res['sog_type']

            check_missing_variables(mc_id=mc_id, start_id=start_id, stop_id=stop_id, sog_type=sog_type)

            result = self.annotation_svc.change_sog_type(mc_id, start_id, stop_id, sog_type)

            return json.dumps(result), 200

        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status

    # ---- EoI operations ----

    def add_eoi(self):
        res = request.form
        equation_id = res['equation_id']
        result = self.annotation_svc.add_eoi(equation_id)
        if result and str(result).startswith("flash:"):
            flash(result[6:])
        return redirect('/equations_of_interest_selector')

    def remove_eoi(self):
        res = request.form
        equation_id = res['equation_id']
        result = self.annotation_svc.remove_eoi(equation_id)
        if result and str(result).startswith("flash:"):
            flash(result[6:])
        return redirect('/equations_of_interest_selector')

    # ---- Group operations ----

    def add_group(self):
        try:
            res = request.json
            check_document_edit_id(self.mi_anno_edit_id, res.get('mi_anno_edit_id'))

            group_info = {
                "start_id": res.get('start_id'),
                "stop_id": res.get('stop_id'),
                "ancestry_level_start": res.get('ancestry_level_start'),
                "ancestry_level_stop": res.get('ancestry_level_stop'),
            }

            result = self.annotation_svc.add_group(group_info)

            return json.dumps(result), 200

        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status

    def remove_group(self):
        try:
            res = request.json
            check_document_edit_id(self.mi_anno_edit_id, res.get('mi_anno_edit_id'))

            group_id = res.get('group_id')
            check_missing_variables(group_id=group_id)

            result = self.annotation_svc.remove_group(group_id)

            return json.dumps(result), 200

        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status

    # ---- Symbolic code and environment settings ----

    def edit_symbolic_code(self):
        try:
            res = request.json
            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))

            eoi_id = res.get('eoi_id')
            symbolic_code = res.get('symbolic_code')
            ast = res.get('ast')
            ast_variables = res.get('ast_variables')
            substitutions_dict = res.get('substitutions_dict')

            check_missing_variables(
                eoi_id=eoi_id,
                symbolic_code=symbolic_code,
                ast=ast,
                ast_variables=ast_variables,
                substitutions_dict=substitutions_dict
            )

            result = self.annotation_svc.edit_symbolic_code(
                eoi_id, symbolic_code, ast, ast_variables, substitutions_dict
            )
            if result and str(result).startswith("flash:"):
                flash(result[6:])
                result = {
                    "status": "error",
                    "message": result[6:]
                }
            else:
                return json.dumps(result), 200

            return json.dumps(result), 200

        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status

    def edit_environment_settings(self):
        try:
            res = request.json
            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))

            environment_settings = res.get('environment_settings')
            check_missing_variables(environment_settings=environment_settings)

            result = self.annotation_svc.edit_environment_settings(environment_settings)

            return json.dumps(result), 200

        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status

    # ---- Occurrence properties ----

    def get_occurence_properties_options_html(self):
        try:
            comp_tag_id = request.args.get('comp_tag_id', '')

            result = self.validation_svc.get_occurence_properties_options_html(comp_tag_id)

            return json.dumps(result), 200

        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status

    def edit_occurence_properties(self):
        try:
            res = request.json
            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))

            comp_tag_id = res.get('comp_tag_id')
            properties = res.get('properties')

            check_missing_variables(comp_tag_id=comp_tag_id, properties=properties)

            result = self.annotation_svc.edit_occurence_properties(comp_tag_id, properties)

            return json.dumps(result), 200

        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status

    def get_concept_properties_options_html(self):
        try:
            mc_id = request.args.get('mc_id', '')
            tensor_rank = request.args.get('tensor_rank', '')

            result = self.validation_svc.get_concept_properties_options_html(mc_id, tensor_rank)

            return json.dumps(result), 200

        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status

    # ---- JSON serialization (delegated) ----

    def gen_mcdict_json(self):
        return gen_mcdict_json(self.mcdict, self.mcdict_edit_id)

    def gen_mi_anno_json(self):
        return gen_mi_anno_json(self.mi_anno_edit_id)

    def get_sample_info(self):
        return get_sample_info(self.paper_id)

    def gen_hex_to_mc_map(self):
        return gen_hex_to_mc_map(self.mcdict)

    # ---- LLM automation (delegated) ----

    def auto_segment_symbols(self):
        try:
            res = request.json
            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))
            check_document_edit_id(self.mi_anno_edit_id, res.get('mi_anno_edit_id'))

            result = self.llm_svc.auto_segment_symbols(
                self.mcdict_edit_id, self.mi_anno_edit_id
            )

            return json.dumps(result), 200

        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status
        except Exception as e:
            traceback.print_exc()
            error = PostRequestError(
                code="UNKNOWN",
                message="Error during Automatic Symbols Segmentation",
                http_status=400
            )
            return json.dumps(error.to_dict()), error.http_status

    def auto_assign_concepts(self):
        try:
            res = request.json
            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))
            check_document_edit_id(self.mi_anno_edit_id, res.get('mi_anno_edit_id'))

            result = self.llm_svc.auto_assign_concepts(
                self.mcdict_edit_id, self.mi_anno_edit_id
            )

            return json.dumps(result), 200

        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status

    def auto_highlight_sources(self):
        try:
            res = request.json
            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))
            check_document_edit_id(self.mi_anno_edit_id, res.get('mi_anno_edit_id'))

            result = self.llm_svc.auto_highlight_sources(
                self.mcdict_edit_id, self.mi_anno_edit_id
            )

            return json.dumps(result), 200

        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status

    # ---- CAS operations (delegated) ----

    def submit_template_file(self):
        try:
            result = self.cas_svc.submit_template_file()
            return json.dumps(result), 200
        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status

    def download_output_file(self):
        try:
            type = request.args.get('type')
            check_missing_variables(type=type)
            return self.cas_svc.download_output_file(type)
        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status

    def run_cas(self):
        try:
            res = request.json
            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))

            eoi_id = res.get('eoi_id')
            check_missing_variables(eoi_id=eoi_id)

            result = self.cas_svc.run_cas(eoi_id)

            return json.dumps(result), 200

        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status

    # ---- Checkpoint operations (delegated) ----

    def create_data_checkpoint(self):
        try:
            res = request.json
            check_document_edit_id(self.mcdict_edit_id, res.get('mcdict_edit_id'))
            check_document_edit_id(self.mi_anno_edit_id, res.get('mi_anno_edit_id'))

            checkpoint_tag = res.get('checkpoint_tag')
            check_missing_variables(checkpoint_tag=checkpoint_tag)
            if checkpoint_tag == "":
                raise PostRequestError(
                    code="VALUE_ERROR",
                    message="Checkpoint tag is empty",
                    http_status=400
                )

            self.checkpoint_svc.create_checkpoint(checkpoint_tag)

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

            checkpoint_tag = res.get("checkpoint_tag")

            if checkpoint_tag is not None and not any(char.isalnum() for char in checkpoint_tag):
                raise PostRequestError(
                    code="VALUE_ERROR",
                    message="Checkpoint tag is not valid",
                    http_status=400
                )

            self.checkpoint_svc.clear_annotation_data(checkpoint_tag)

            success_message = {
                "status": "success",
                "message": "Annotations clearing successful.",
            }

            return json.dumps(success_message), 200

        except PostRequestError as e:
            return json.dumps(e.to_dict()), e.http_status

    # ---- Edit ID updaters ----

    def update_mi_anno_edit_id(self):
        self.mi_anno_edit_id += 1

    def update_mcdict_edit_id(self):
        self.mcdict_edit_id += 1
