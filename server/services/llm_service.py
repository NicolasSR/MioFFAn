import json
from copy import deepcopy
from pathlib import Path
from pydantic import BaseModel

from lib.util import PostRequestError
from lib.llm_utilities import validate_llm_output_schema, get_or_create_llm_log_file, process_auto_segment_symbol_data
from llm_implementation.llm_implementations import (
    auto_segment_symbols, auto_define_and_assign_concepts, auto_highlight_sources
)


class LLMService:
    def __init__(self, mi_anno, mcdict, tree, config, paper_id, annotation_service):
        self.mi_anno = mi_anno
        self.mcdict = mcdict
        self.tree = tree
        self.config = config
        self.paper_id = paper_id
        self.annotation_service = annotation_service

    def auto_segment_symbols(self, mcdict_edit_id, mi_anno_edit_id):
        class NewGroupDefinitionSchema(BaseModel):
            symbol_name: str
            included_mi_ids: list

        class NewOccurrenceDefinitionSchema(BaseModel):
            symbol_name: str
            comp_tag_id: str

        class ExpectedOutputSchema(BaseModel):
            new_groups: list
            new_occurrences: list

        schema_json = ExpectedOutputSchema.model_json_schema()
        with open('llm_implementation/documentation/auto_segment_symbols_schema.json', 'w') as f:
            json.dump(schema_json, f, indent=4, sort_keys=True, separators=(',', ': '))

        log_file = get_or_create_llm_log_file(self.paper_id)

        dom_tree_copy = deepcopy(self.tree.xpath("//body")[0])
        mcdict_copy = deepcopy(self.mcdict)
        mi_anno_copy = deepcopy(self.mi_anno)

        result_dict = auto_segment_symbols(dom_tree_copy, mcdict_copy, mi_anno_copy, llm_log_file=log_file)

        is_valid, validation_res = validate_llm_output_schema(result_dict, ExpectedOutputSchema)
        if not is_valid:
            raise PostRequestError(
                code="OUTPUT_VALIDATION_ERROR",
                message="Automation output does not match the required schema." + str(validation_res),
                http_status=400
            )

        new_concepts_dict, new_groups_dict, new_occurrences_dict = process_auto_segment_symbol_data(
            dom_tree_copy, validation_res
        )

        mc_ids_map = dict()
        for symbol_name, concept_info in new_concepts_dict.items():
            is_successful, data = self.annotation_service.register_concept_inner(concept_info, None)
            if not is_successful:
                raise PostRequestError(
                    code="DATA_REGISTRATION_ERROR",
                    message="Concept registration was not successful. " + str(data),
                    http_status=400
                )
            mc_ids_map[symbol_name] = data

        for symbol_name, group_info_list in new_groups_dict.items():
            for group_info in group_info_list:
                is_successful, data = self.annotation_service.add_group_inner(group_info)
                if not is_successful:
                    raise PostRequestError(
                        code="DATA_REGISTRATION_ERROR",
                        message="Group registration was not successful. " + str(data),
                        http_status=400
                    )
                self.annotation_service.assign_concept_inner(data, mc_ids_map[symbol_name], "mstyle")

        for symbol_name, occurrence_info_list in new_occurrences_dict.items():
            for occurrence_info in occurrence_info_list:
                comp_tag_id = occurrence_info["comp_tag_id"]
                tag_name = occurrence_info["tag_name"]
                self.annotation_service.assign_concept_inner(comp_tag_id, mc_ids_map[symbol_name], tag_name)

        return {
            "status": "success",
            "message": "Automatic symbol segmentation successful.",
        }

    def auto_assign_concepts(self, mcdict_edit_id, mi_anno_edit_id):
        class NewConceptsDefinitionSchema(BaseModel):
            code_var_name: str
            description: str
            concept_category: str
            properties: dict

        class NewConceptsMapSchema(BaseModel):
            original_mc_ids: list
            new_concept_info: NewConceptsDefinitionSchema

        class ExpectedOutputSchema(BaseModel):
            concepts_info_list: list

        schema_json = ExpectedOutputSchema.model_json_schema()
        with open('llm_implementation/documentation/auto_assign_concepts_schema.json', 'w') as f:
            json.dump(schema_json, f, indent=4, sort_keys=True, separators=(',', ': '))

        log_file = get_or_create_llm_log_file(self.paper_id)

        dom_tree_copy = deepcopy(self.tree.xpath("//body")[0])
        mcdict_copy = deepcopy(self.mcdict)
        mi_anno_copy = deepcopy(self.mi_anno)

        result_dict = auto_define_and_assign_concepts(
            dom_tree_copy, mcdict_copy, mi_anno_copy, llm_log_file=log_file
        )

        is_valid, validation_res = validate_llm_output_schema(result_dict, ExpectedOutputSchema)
        if not is_valid:
            raise PostRequestError(
                code="OUTPUT_VALIDATION_ERROR",
                message="Automation output does not match the required schema." + str(validation_res),
                http_status=400
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
            is_successful, data = self.annotation_service.register_concept_inner(new_concept_info, None)
            if not is_successful:
                raise PostRequestError(
                    code="DATA_REGISTRATION_ERROR",
                    message="Concept registration was not successful. " + str(data),
                    http_status=400
                )
            new_mc_id = data
            for original_mc_id in original_mc_ids:
                for occurrence_id, occurence_info in self.mcdict.occurences_dict.items():
                    if occurence_info.mc_id == original_mc_id:
                        comp_tag_id = occurrence_id
                        tag_name = occurence_info.tag_name
                        self.annotation_service.assign_concept_inner(comp_tag_id, new_mc_id, tag_name)

        return {
            "status": "success",
            "message": "Automatic assignment of concepts successful.",
        }

    def auto_highlight_sources(self, mcdict_edit_id, mi_anno_edit_id):
        class NewSoGsInfoSchema(BaseModel):
            mc_id: str
            start_id: str
            stop_id: str

        class ExpectedOutputSchema(BaseModel):
            sogs_info_list: list

        schema_json = ExpectedOutputSchema.model_json_schema()
        with open('llm_implementation/documentation/auto_highlight_sources_schema.json', 'w') as f:
            json.dump(schema_json, f, indent=4, sort_keys=True, separators=(',', ': '))

        log_file = get_or_create_llm_log_file(self.paper_id)

        dom_tree_copy = deepcopy(self.tree.xpath("//body")[0])
        mcdict_copy = deepcopy(self.mcdict)
        mi_anno_copy = deepcopy(self.mi_anno)

        result_dict = auto_highlight_sources(
            dom_tree_copy, mcdict_copy, mi_anno_copy, llm_log_file=log_file
        )

        is_valid, validation_res = validate_llm_output_schema(result_dict, ExpectedOutputSchema)
        if not is_valid:
            raise PostRequestError(
                code="OUTPUT_VALIDATION_ERROR",
                message="Automation output does not match the required schema." + str(validation_res),
                http_status=400
            )

        for new_sog in validation_res["sogs_info_list"]:
            self.annotation_service.add_sog_inner(
                new_sog["mc_id"], new_sog["start_id"], new_sog["stop_id"]
            )

        return {
            "status": "success",
            "message": "Automatic assignment of concepts successful.",
        }
