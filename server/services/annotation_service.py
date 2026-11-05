from lib.datatypes import SoG, Group, EoI, EnvironmentSetting, MathConcept
from lib.util import check_missing_variables, PostRequestError
from lib.concept_properties import validate_properties


def make_concept(res, taxonomy_config, sog_list=[]):
    """Validate and construct a MathConcept from request data."""
    if not res.get('code_var_name').isidentifier():
        return None, "Variable name must be compliant with Python identifier rules."

    description = res.get('description')
    if len(description) == 0:
        return None, "Description must be filled."

    category = res.get('concept_category')
    fields_config = taxonomy_config[category].get('concept_fields', {})

    properties = res.get('properties')
    is_valid, error_msg = validate_properties(fields_config, properties)
    if not is_valid:
        return None, f"Logic Validation Failed: {error_msg}"

    primitive_symbols = res.get('primitive_symbols')

    return MathConcept(
        res.get('code_var_name'),
        description,
        category,
        properties,
        sog_list,
        primitive_symbols
    ), None


class AnnotationService:
    def __init__(self, mi_anno, mcdict, config, mi_anno_edit_id_getter, mcdict_edit_id_getter,
                 mi_anno_edit_id_incrementer, mcdict_edit_id_incrementer):
        self.mi_anno = mi_anno
        self.mcdict = mcdict
        self.config = config
        self._mi_anno_edit_id_getter = mi_anno_edit_id_getter
        self._mcdict_edit_id_getter = mcdict_edit_id_getter
        self._mi_anno_edit_id_incrementer = mi_anno_edit_id_incrementer
        self._mcdict_edit_id_incrementer = mcdict_edit_id_incrementer

    # ---- Concept assignment ----

    def assign_concept(self, comp_tag_id, mc_id, tag_name):
        self.assign_concept_inner(comp_tag_id, mc_id, tag_name)
        return {
            "status": "success",
            "message": "Concept assigned successfully."
        }

    def assign_concept_inner(self, comp_tag_id, mc_id, tag_name, options=[]):
        from lib.datatypes import Occurence
        self.mcdict.occurences_dict[comp_tag_id] = Occurence(mc_id, tag_name, options)
        self.mcdict.dump()
        self._mcdict_edit_id_incrementer()

    def remove_concept(self, comp_tag_id):
        del self.mcdict.occurences_dict[comp_tag_id]
        self.mcdict.dump()
        self._mcdict_edit_id_incrementer()
        return {
            "status": "success",
            "message": "Concept removed successfully."
        }

    # ---- Concept registration ----

    def register_concept(self, res, mc_id):
        is_successful, data = self.register_concept_inner(res, mc_id)
        if not is_successful:
            raise PostRequestError(
                code="DATA_REGISTRATION_ERROR",
                message="Concept registration was not successful. " + str(data),
                http_status=400
            )
        return {
            "status": "success",
            "message": "Concept registered successfully.",
            "mc_id": data
        }

    def register_concept_inner(self, concept_info, mc_id):
        if mc_id is None:
            if concept_info.get('concept_category') == "symbol-placeholder":
                code_var_name = concept_info["code_var_name"]
                concept_info['description'] = f"Placeholder {code_var_name}"
                concept_info['properties'] = {}
            mc_id = str(self.mcdict.next_available_mc_id)
            self.mcdict.next_available_mc_id += 1
            sog_list = []
        else:
            mc_id = concept_info.get('mc_id')
            sog_list = self.mcdict.concepts[mc_id].sog_list

        taxonomy_config = self.config.get('CONCEPT_TAXONOMY', {})
        concept, error_msg = make_concept(concept_info, taxonomy_config, sog_list=sog_list)
        if error_msg:
            return False, f"Failed to make concept: {error_msg}"

        check_missing_variables(concept=concept, mc_id=mc_id)

        self.mcdict.concepts[mc_id] = concept
        self.mcdict.dump()
        self._mcdict_edit_id_incrementer()

        return True, mc_id

    # ---- SoG operations ----

    def add_sog(self, mc_id, start_id, stop_id):
        self.add_sog_inner(mc_id, start_id, stop_id)
        return {
            "status": "success",
            "message": "SoG added successfully."
        }

    def add_sog_inner(self, mc_id, start_id, stop_id):
        existing_sog_pos = [(s.start_id, s.stop_id) for s in self.mcdict.concepts[mc_id].sog_list]
        if (start_id, stop_id) not in existing_sog_pos:
            self.mcdict.concepts[mc_id].sog_list.append(SoG(start_id, stop_id, 0))
            self.mcdict.dump()
        self._mcdict_edit_id_incrementer()

    def delete_sog(self, mc_id, start_id, stop_id):
        delete_idx = None
        for idx, sog in enumerate(self.mcdict.concepts[mc_id].sog_list):
            if sog.start_id == start_id and sog.stop_id == stop_id:
                delete_idx = idx
                break

        if delete_idx is not None:
            del self.mcdict.concepts[mc_id].sog_list[delete_idx]
            self.mcdict.dump()

        self._mcdict_edit_id_incrementer()
        return {
            "status": "success",
            "message": "SoG deleted successfully."
        }

    def change_sog_type(self, mc_id, start_id, stop_id, sog_type):
        for sog in self.mcdict.concepts[mc_id].sog_list:
            if sog.start_id == start_id and sog.stop_id == stop_id:
                sog.type = sog_type
                self.mcdict.dump()
                break

        self._mcdict_edit_id_incrementer()
        return {
            "status": "success",
            "message": "SoG added successfully."
        }

    # ---- EoI operations ----

    def add_eoi(self, equation_id):
        if equation_id not in self.mcdict.eoi_dict.keys():
            self.mcdict.eoi_dict[equation_id] = EoI(
                symbolic_code="", ast="", ast_variables=[], substitutions_dict=""
            )
            self.mcdict.dump()
            self._mcdict_edit_id_incrementer()
        else:
            return "flash:Equation ID was already in the list of EoI."

    def remove_eoi(self, equation_id):
        if equation_id in self.mcdict.eoi_dict.keys():
            del self.mcdict.eoi_dict[equation_id]
            self.mcdict.dump()
            self._mcdict_edit_id_incrementer()
        else:
            return "flash:Equation ID was not found in the list of EoI."

    # ---- Group operations ----

    def add_group(self, group_info):
        is_successful, data = self.add_group_inner(group_info)
        if not is_successful:
            raise PostRequestError(
                code="DATA_REGISTRATION_ERROR",
                message="Group registration was not successful. " + str(data),
                http_status=400
            )
        new_group_id = data
        return {
            "status": "success",
            "message": "Group created successfully.",
            "group_id": new_group_id,
        }

    def add_group_inner(self, group_info):
        try:
            new_group_id = f"custom-group-{self.mi_anno.next_available_group_id}"
            self.mi_anno.groups[new_group_id] = Group(**group_info)
        except Exception:
            return False, "Failed to cast group information into Group object."

        self.mi_anno.next_available_group_id += 1
        self.mi_anno.dump()
        self._mi_anno_edit_id_incrementer()

        return True, new_group_id

    def remove_group(self, group_id):
        del self.mi_anno.groups[group_id]
        self.mi_anno.dump()
        self._mi_anno_edit_id_incrementer()
        return {
            "status": "success",
            "message": "Group removed successfully.",
            "group_id": group_id,
        }

    # ---- Symbolic code and environment settings ----

    def edit_symbolic_code(self, eoi_id, symbolic_code, ast, ast_variables, substitutions_dict):
        if eoi_id in self.mcdict.eoi_dict.keys():
            self.mcdict.eoi_dict[eoi_id].symbolic_code = symbolic_code
            self.mcdict.eoi_dict[eoi_id].ast = ast
            self.mcdict.eoi_dict[eoi_id].ast_variables = ast_variables.split(", ")
            self.mcdict.eoi_dict[eoi_id].substitutions_dict = substitutions_dict
            self.mcdict.dump()
        else:
            return "flash:Equation ID was not found in the list of EoI."

        self._mcdict_edit_id_incrementer()
        return {
            "status": "success",
            "message": "Symbolic code updated successfully."
        }

    def edit_environment_settings(self, environment_settings):
        self.mcdict.environment_settings_list = [
            EnvironmentSetting(**setting) for setting in environment_settings
        ]
        self.mcdict.dump()
        self._mcdict_edit_id_incrementer()
        return {
            "status": "success",
            "message": "Environment settings updated successfully."
        }

    # ---- Occurrence properties ----

    def edit_occurence_properties(self, comp_tag_id, properties):
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
        self._mcdict_edit_id_incrementer()

        return {
            "status": "success",
            "message": "Occurence properties edited successfully."
        }
