import io
from flask import request, send_file

from lib.util import check_missing_variables, PostRequestError
from lib.cas_plugins_interface import CASPluginInterface


class CASService:
    def __init__(self, kratos_templates, kratos_output_files, mcdict, paper_id):
        self.kratos_templates = kratos_templates
        self.kratos_output_files = kratos_output_files
        self.mcdict = mcdict
        self.paper_id = paper_id

    def submit_template_file(self):
        try:
            type = request.form.get('type')
            check_missing_variables(type=type)

            if 'file' not in request.files:
                raise PostRequestError(
                    code="MISSING_FILE",
                    message="No file was obtained",
                    http_status=400
                )
            file = request.files['file']

            self.kratos_templates[type] = io.BytesIO(file.read()).getvalue().decode('utf-8')

            return {
                "status": "success",
                "message": "Template file successfully obtained.",
            }

        except PostRequestError:
            raise
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise PostRequestError(
                code="UNKNOWN",
                message="Error during Template File Input",
                http_status=400
            )

    def download_output_file(self, type):
        check_missing_variables(type=type)

        file_text = self.kratos_output_files[type]

        in_memory_file = io.BytesIO(file_text.encode('utf-8'))
        in_memory_file.seek(0)

        return send_file(
            in_memory_file,
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=f"{type}.cpp"
        )

    def run_cas(self, eoi_id):
        if not ("element" in self.kratos_templates.keys() and "condition" in self.kratos_templates):
            raise PostRequestError(
                code="INALID_DATA",
                message="Kratos template for either element or condition not available.",
                http_status=404
            )

        cas_interface = CASPluginInterface.create(self.paper_id, eoi_id)
        fe_definition_dict = self._generate_fe_definition_dict(eoi_id, cas_interface)
        compiler_execute_input = {
            "fe_definition_dict": fe_definition_dict,
            "template_files_content": self.kratos_templates
        }
        self.kratos_output_files = cas_interface.execute(compiler_execute_input)

        return {
            "status": "success",
            "message": "Environment settings updated successfully."
        }

    def _generate_fe_definition_dict(self, eoi_id, cas_interface):
        if eoi_id not in self.mcdict.eoi_dict:
            raise PostRequestError(
                code="INVALID_IDENTIFIER",
                message=f"Identifier eoi_id: {eoi_id} missing in internal EOI dictionary.",
                http_status=404
            )
        eoi = self.mcdict.eoi_dict.get(eoi_id, None)
        if eoi is None:
            raise PostRequestError(
                code="INVALID_IDENTIFIER",
                message=f"Identifier eoi_id: {eoi_id} did not yield a valid eoi object.",
                http_status=404
            )
        ast = eoi.ast

        ast_mc_ids = eoi.ast_variables
        ast_mc_dict = {mc_id: self.mcdict.concepts[mc_id] for mc_id in ast_mc_ids}

        out = cas_interface.generate_fe_definition_dict(
            ast, ast_mc_dict, self.mcdict.environment_settings_list, eoi.substitutions_dict
        )

        return out
