class ValidationService:
    def __init__(self, mcdict, config):
        self.mcdict = mcdict
        self.config = config

    def get_occurence_properties_options_html(self, comp_tag_id):
        from lib.util import PostRequestError

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

        out_html = build_occurence_properties_options_html(concept.tensor_rank, occurence.options)

        return {
            "status": "success",
            "message": "Occurence properties options HTML generated successfully.",
            "out_html": out_html
        }

    def get_concept_properties_options_html(self, mc_id, tensor_rank):
        from lib.util import PostRequestError

        previous_options = []
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

        out_html = build_concept_properties_options_html(tensor_rank, previous_options)

        return {
            "status": "success",
            "message": "Occurence properties options HTML generated successfully.",
            "out_html": out_html
        }
