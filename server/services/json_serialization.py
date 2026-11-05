import json
from dataclasses import asdict


def gen_mcdict_json(mcdict, mcdict_edit_id):
    data = dict()
    data['mcdict'] = preprocess_mcdict(mcdict.concepts)
    data['eoi_dict'] = {eoi_id: asdict(eoi_obj) for eoi_id, eoi_obj in mcdict.eoi_dict.items()}
    data['occurences_dict'] = {comp_tag_id: asdict(occ_obj) for comp_tag_id, occ_obj in mcdict.occurences_dict.items()}
    data['environment_settings_list'] = [asdict(setting) for setting in mcdict.environment_settings_list]
    extended_data = [str(mcdict_edit_id), data]
    return json.dumps(extended_data, ensure_ascii=False, indent=4, sort_keys=True, separators=(',', ': '))


def gen_mi_anno_json(mi_anno_edit_id):
    data = {}
    extended_data = [str(mi_anno_edit_id), data]
    return json.dumps(extended_data, ensure_ascii=False, indent=4, sort_keys=True, separators=(',', ': '))


def get_sample_info(paper_id):
    data = {"sample_name": paper_id}
    return json.dumps(data, ensure_ascii=False, indent=4, sort_keys=True, separators=(',', ': '))


def gen_hex_to_mc_map(mcdict):
    data = {}
    for mc_id, mc_obj in mcdict.concepts.items():
        for hex_value in mc_obj.primitive_symbols:
            if hex_value in data.keys():
                data[hex_value].append(mc_id)
            else:
                data[hex_value] = [mc_id]
    return json.dumps(data, ensure_ascii=False, indent=4, sort_keys=True, separators=(',', ': '))


def preprocess_mcdict(concepts):
    import re

    def process_math(math):
        def construct_mi(idf_text, idf_var, concept_id):
            mi = '<mi data-mc-id="{}"'.format(concept_id)

            if idf_var == 'roman':
                mi += ' mathvariant="normal">'
            else:
                mi += '>'

            mi += idf_text + '</mi>'

            return mi

        math = re.sub(r'(@\d+)', r'<mi>\1</mi>', math)

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

        it = desc.split('$')
        desc_new = ''.join([a + process_math(b) for a, b in zip(it[::2], it[1::2])])
        if len(it) % 2 != 0:
            desc_new += it[-1]

        return desc_new

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
