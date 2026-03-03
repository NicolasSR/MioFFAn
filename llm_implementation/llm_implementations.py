import json
import time
import re
import unicodedata

from copy import deepcopy
from collections import OrderedDict

from lxml import etree

from lib.util import PostRequestError, wrap_custom_group
from lib.llm_utilities import client, get_running_model_name, check_token_usage, max_context_length
from lib.llm_utilities import find_first_match_info, find_mathml_occurrences, get_all_ids_as_set, find_relationships_through_contained_ids
from lib.llm_utilities import get_primitive_hex_set, check_if_tag_with_id_in_tree

"""
To run this script, a vllm server needs to be running. Call it via:
vllm serve Qwen/Qwen3-4B-Instruct-2507 --max_model_len 65536
"""

def replace_with_unicode_name(html_snippet):
    # Regex finds text content between > and <
    pattern = r'(>)([^<]+)(<)'
    
    def process_content(match):
        prefix = match.group(1) # The '>'
        content = match.group(2) # The text inside
        suffix = match.group(3) # The '<'
        
        new_content = ""
        for char in content:
            if ord(char) > 127:
                try:
                    # Get formal name: e.g., "GREEK SMALL LETTER RHO"
                    full_name = unicodedata.name(char)
                    # # Clean it up to get the last word (rho, omega, integral, etc.)
                    # # and make it lowercase
                    # clean_name = full_name.split()[-1].lower()
                    # new_content += clean_name
                    new_content += full_name
                except ValueError:
                    # Fallback if character name isn't found
                    new_content += char
            else:
                new_content += char
        
        return f"{prefix}{new_content}{suffix}"

    return re.sub(pattern, process_content, html_snippet)

class SetEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, set):
            return list(obj)
        return json.JSONEncoder.default(self, obj)

def auto_segment_symbols(dom_tree_copy, mcdict_copy, mi_anno_copy, llm_log_file = None):

    eoi_ids_list = list(mcdict_copy.eoi_dict.keys())

    full_html_text_raw = etree.tostring(dom_tree_copy, encoding='unicode')
    full_html_text = replace_with_unicode_name(full_html_text_raw)
    full_html_tree = etree.fromstring(full_html_text, etree.HTMLParser())

    multi_eoi_new_groups_dict = dict()
    multi_eoi_new_occurences_dict = dict()

    log_json = dict()

    if not eoi_ids_list:
        raise PostRequestError(
            code = "MISSING_DATA",
            message = "No EoI was indicated",
            http_status = 400
        )

    for eoi_id in eoi_ids_list:
        log_json[eoi_id] = dict()

        weak_form = full_html_tree.find(f".//div[@id='{eoi_id}']")
        weak_form_string = etree.tostring(weak_form, encoding='unicode')

        html_text = full_html_text

        fits_in_context = False
        while fits_in_context == False:

            with open("llm_implementation/llm_prompt_files/segment_symbols_prompt.txt", "r") as prompt_file:
                system_prompt_segmentation = prompt_file.read()
            messages=[
                    {"role": "system", "content": system_prompt_segmentation},
                    {"role": "user", "content": f"Paper section to study: {html_text}. Weak form appears in ID: {eoi_id}, and is repeated here: {weak_form_string}. Build the objects list."}
                ]
        
            tokens_count, max_model_len = check_token_usage(messages)
            max_token_len = min(max_context_length,max_model_len)
            print(f"Token count for prompt: {tokens_count}, Max token count: {max_context_length}, Model's max context length: {max_model_len}")
            print(f"Current html text length: {len(html_text)} characters.")
            if tokens_count >= max_token_len:
                print(f"Error: The prompt exceeds the model's context length. Token count for prompt: {tokens_count}, Model max context length: {max_model_len}")
                excess_ratio = (tokens_count-max_token_len)/tokens_count
                reduction_length_total = int(len(html_text) * excess_ratio)
                print(f"Reducing context length by approximately {reduction_length_total} characters.")
                html_text_divided = html_text.split(weak_form_string)
                if len(html_text_divided) == 2:
                    len_html_text_back = len(html_text_divided[1])
                    kept_chars_in_back = max(1000, len_html_text_back - reduction_length_total)
                    html_text_back_reduced = html_text_divided[1][:kept_chars_in_back]
                    print(f"Reducing from the back by approximately {len_html_text_back - kept_chars_in_back} characters.")
                    reduction_length_front = max(0,reduction_length_total - (len_html_text_back - kept_chars_in_back))
                    if len(html_text_divided[0]) - reduction_length_front < 1000:
                        print("Error: Unable to remove enough context to fit in the LLM's max context length.")
                        messages = None
                        break
                    print(f"Reducing from the front by approximately {reduction_length_front} characters.")
                    html_text_front_reduced = html_text_divided[0][reduction_length_front:]
                    html_text_reduced = html_text_front_reduced + weak_form_string + html_text_back_reduced
                else:
                    print("Error: Unable to split HTML text properly for context length reduction.")
                    messages = None
                    break
                html_text = html_text_reduced
            else:
                fits_in_context = True

        if messages is None:
            continue

        chat_response = client.chat.completions.create(
            # model="Qwen/Qwen3-4B-Instruct-2507",
            model=get_running_model_name(),
            messages=messages
        )

        time.sleep(5)
        chat_response_string = chat_response.choices[0].message.content
        objects_list = json.loads(chat_response_string)

        log_json[eoi_id]["initial_output"] = objects_list

        deduplicated_objects_list = []
        seen_variable_names = set()
        for obj in objects_list:
            if obj["obj_name"] not in seen_variable_names:
                deduplicated_objects_list.append(obj)
                seen_variable_names.add(obj["obj_name"])
        objects_list = deduplicated_objects_list

        print(objects_list)
        log_json[eoi_id]["deduplicated_list"] = objects_list

        new_occurences_dict = dict()
        new_groups_dict = dict()
        all_id_sets = []

        for obj in objects_list:
            symbol_name = obj["obj_name"]
            print(symbol_name)

            matches = find_mathml_occurrences(weak_form_string, obj['mathml_representation'])
            for match in matches:
                match_str = ''
                match_ids_set = set()
                primitive_hex_set = set()
                for element in match:
                    match_str += etree.tostring(element, encoding='unicode')
                    match_ids_set.update(get_all_ids_as_set(element))
                    primitive_hex_set.update(get_primitive_hex_set(element, dom_tree_copy))
                print(match_str)
                identifier_info_first = find_first_match_info(match[0])
                if identifier_info_first is None:
                    continue
                start_id = identifier_info_first['id']
                tag_name = identifier_info_first['tag_name']
                ancestry_level_start = identifier_info_first['depth']
                if len(match) == 1:
                    all_id_sets.append({
                        "variable_name": symbol_name,
                        "representative_id": start_id,
                        "ids_set": match_ids_set,
                        "ids_count": len(match_ids_set),
                        "mathml": match_str
                    })
                    occurrence_info = {
                            "comp_tag_id": start_id,
                            "tag_name": tag_name,
                            "primitive_symbols": deepcopy(primitive_hex_set),
                            "ids_set": match_ids_set
                        }
                    if symbol_name in new_occurences_dict:
                        new_occurences_dict[symbol_name].append(occurrence_info)
                    else:
                        new_occurences_dict[symbol_name]=[occurrence_info]
                else:
                    identifier_info_last = find_first_match_info(match[-1])
                    if identifier_info_last is None:
                        continue
                    stop_id = identifier_info_last['id']
                    ancestry_level_stop = identifier_info_last['depth']
                    all_id_sets.append({
                        "variable_name": symbol_name,
                        "representative_id": start_id,
                        "ids_set": match_ids_set,
                        "ids_count": len(match_ids_set),
                        "mathml": match_str
                    })
                    group_info = {
                        "ancestry_level_start": ancestry_level_start,
                        "ancestry_level_stop": ancestry_level_stop,
                        "start_id": start_id,
                        "stop_id": stop_id,
                        "primitive_symbols": deepcopy(primitive_hex_set),
                        "ids_set": match_ids_set
                    }
                    if symbol_name in new_groups_dict:
                        new_groups_dict[symbol_name].append(group_info)
                    else:
                        new_groups_dict[symbol_name]=[group_info]

        log_json[eoi_id]["new_groups_dict"] = new_groups_dict
        log_json[eoi_id]["new_occurences_dict"] = new_occurences_dict
        log_json[eoi_id]["all_id_sets"] = all_id_sets

        # Check for conflicts in symbol segmentation
        conflicts_list_raw = find_relationships_through_contained_ids(all_id_sets)
        print(conflicts_list_raw)
        log_json[eoi_id]["conflicts_list"] = conflicts_list_raw
        if conflicts_list_raw:
            print("Conflicts detected in symbol segmentation:")
            new_groups_dict, new_occurences_dict, log_json = disambiguate_symbol_segmentation(html_text, eoi_id, weak_form_string, conflicts_list_raw, new_groups_dict, new_occurences_dict, log_json)
            log_json[eoi_id]["disambiguated_new_groups_dict"] = new_groups_dict
            log_json[eoi_id]["disambiguated_new_occurences_dict"] = new_occurences_dict
        multi_eoi_new_groups_dict[eoi_id] = new_groups_dict
        multi_eoi_new_occurences_dict[eoi_id] = new_occurences_dict

    # Merge all results from different EOIs into a single dictionary
    final_new_occurences_dict = dict()
    final_new_groups_dict = dict()
    for eoi_id_iter, new_occurences_dict_iter in multi_eoi_new_occurences_dict.items():
        for symbol_name, occurences_list in new_occurences_dict_iter.items():
            if symbol_name in final_new_occurences_dict:
                final_new_occurences_dict[symbol_name].extend(occurences_list)
            else:
                final_new_occurences_dict[symbol_name] = occurences_list
    for eoi_id_iter, new_groups_dict_iter in multi_eoi_new_groups_dict.items():
        for symbol_name, groups_list in new_groups_dict_iter.items():
            if symbol_name in final_new_groups_dict:
                final_new_groups_dict[symbol_name].extend(groups_list)
            else:
                final_new_groups_dict[symbol_name] = groups_list

    final_output_dict = {
        "new_groups": [],
        "new_occurrences": []
    }

    for symbol_name, occurences_list in final_new_occurences_dict.items():
        for occurrence_info in occurences_list:
            final_output_dict["new_occurrences"].append({
                "symbol_name": symbol_name,
                "comp_tag_id": occurrence_info["comp_tag_id"]
            })
    
    for symbol_name, groups_list in final_new_groups_dict.items():
        for group_info in groups_list:
            final_output_dict["new_groups"].append({
                "symbol_name": symbol_name,
                "included_mi_ids": [group_info["start_id"],group_info["stop_id"]]
            })

    log_json["total"] = {
        "final_new_groups_dict": final_new_groups_dict,
        "final_new_occurences_dict": final_new_occurences_dict
    }

    print(log_json)

    with open(llm_log_file, 'r') as log_file:
        llm_log = json.load(log_file)
    llm_log["AUTO_SEGMENT_SYMBOLS"] = log_json
    with open(llm_log_file, 'w') as log_file:
        json.dump(llm_log,log_file, indent=4, cls=SetEncoder)

    return final_output_dict
    

def disambiguate_symbol_segmentation(html_text, eoi_id, weak_form_string, conflicts_list_raw, new_groups_dict, new_occurences_dict, log_json):
    conflicts_dict = OrderedDict()
    for i, conflict_raw in enumerate(conflicts_list_raw):
        case_name = f"case_{i+1}"
        conflicts_dict[case_name] = {
            "parent": conflict_raw["parent_mathml"],
            "child": conflict_raw["child_mathml"]
        }

    print(conflicts_dict)

    with open("llm_implementation/llm_prompt_files/disambiguate_coinciding_symbols.txt", "r") as prompt_file:
        system_prompt_disambiguation = prompt_file.read()
    messages=[
        {"role": "system", "content": system_prompt_disambiguation},
        {"role": "user", "content": f"Paper section to study: {html_text}. Weak form appears in ID: {eoi_id}, and is repeated here: {weak_form_string}. The conflict cases are: {conflicts_dict}. Build the conflict results next."}
    ]

    chat_response = client.chat.completions.create(
        model=get_running_model_name(),
        messages=messages
    )

    time.sleep(5)

    chat_response_string = chat_response.choices[0].message.content
    print(chat_response_string)
    try:
        disambiguation_results_json = json.loads(chat_response_string)
    except:
        raise f"Conflict disambiguation: LLM output could not be casted to JSON"
    log_json[eoi_id]["conflicts_resolution"] = disambiguation_results_json

    for case_name, result in disambiguation_results_json.items():
        i = int(case_name.split("_")[1]) - 1
        if result == "REMOVE":
            try:
                child_var_name = conflicts_list_raw[i]["child_variable_name"]
                child_representative_id = conflicts_list_raw[i]["child_representative_id"]
            except:
                raise f"Conflicts_list_raw has no entry in index {i}, or some field is missing within it"
            if child_var_name in new_groups_dict.keys():
                new_groups_list = new_groups_dict[child_var_name]
                new_groups_list_filtered = [group_info for group_info in new_groups_list if not (group_info["start_id"] == child_representative_id)]
                new_groups_dict[child_var_name] = new_groups_list_filtered
            else:
                new_occurences_list = new_occurences_dict[child_var_name]
                new_occurences_list_filtered = [occurrence_info for occurrence_info in new_occurences_list if not (occurrence_info["comp_tag_id"] == child_representative_id)]
                new_occurences_dict[child_var_name] = new_occurences_list_filtered
    
    empty_entries = []
    for var_name, new_groups_list in new_groups_dict.items():
        if not new_groups_list:
            empty_entries.append(var_name)
    for entry in empty_entries:
        del new_groups_dict[entry]

    empty_entries = []
    for var_name, new_occurrences_list in new_occurences_dict.items():
        if not new_occurrences_list:
            empty_entries.append(var_name)
    for entry in empty_entries:
        del new_occurences_dict[entry]
            
    return new_groups_dict, new_occurences_dict, log_json


def auto_define_and_assign_concepts(dom_tree_copy, mcdict_copy, mi_anno_copy, llm_log_file = None):
    log_json = dict()

    mcdict_occurences_dict = mcdict_copy.occurences_dict
    mcdict_concepts_dict = mcdict_copy.concepts
    mi_anno_groups_dict = mi_anno_copy.groups

    eoi_ids_list = list(mcdict_copy.eoi_dict.keys())

    # Wrap specified custom groups in span tags
    for group_id, group_info in mi_anno_groups_dict.items():
        if not wrap_custom_group(dom_tree_copy, group_id, group_info):
            continue

    raw_segmented_symbols_dict = dict()
    for occurence_name, occurence_info in mcdict_occurences_dict.items():
        occurrence_mc_id = occurence_info.mc_id
        concept_info = mcdict_concepts_dict[occurrence_mc_id]
        if concept_info.concept_category=="symbol_placeholder":
            tag_id = occurence_name
            symbol_subtree = dom_tree_copy.xpath(f".//*[@id='{tag_id}']")[0]
            symbol_mathml_string = etree.tostring(symbol_subtree, encoding='unicode')
            if occurrence_mc_id in raw_segmented_symbols_dict.keys():
                raw_segmented_symbols_dict[occurrence_mc_id]["mathml_representations_list"].append(symbol_mathml_string) 
            else:
                raw_segmented_symbols_dict[occurrence_mc_id] = {
                    "obj_name": concept_info.code_var_name,
                    "mathml_representations_list": [symbol_mathml_string]
                }

    concepts_list, log_json = auto_define_concepts(dom_tree_copy, raw_segmented_symbols_dict, eoi_ids_list, log_json)

    segmented_symbols_list = []
    segmented_symbols_dict = dict()
    var_name_to_mc_id_map = dict()
    for segmented_symbol_mcid, segmented_symbol_info in raw_segmented_symbols_dict.items():
        ## FOR NOW WE ARE ONLY USING THE FIRST INSTANCE OF THE MATHML REPRESENTATION. THIS MAY BE CHANGED IN THE FUTURE
        mathml_representation_example = segmented_symbol_info["mathml_representations_list"][0]
        segmented_symbols_list.append({
            "obj_name": segmented_symbol_info["obj_name"],
            "mathml_representation": mathml_representation_example
        })
        var_name_to_mc_id_map[segmented_symbol_info["obj_name"]] = segmented_symbol_mcid
        segmented_symbols_dict[segmented_symbol_info["obj_name"]] = mathml_representation_example

    concept_assignments, log_json = auto_assign_concepts(dom_tree_copy, segmented_symbols_list, concepts_list, eoi_ids_list, log_json)

    # Remove concepts that didn't get any assigned symbol:
    concepts_list = [c for c in concepts_list if c["name"] in concept_assignments.values()]
    
    # Get properties for concepts marked as "VARIABLE":
    variable_concepts_list = [deepcopy(concept) for concept in concepts_list if concept["type"]=="VARIABLE"]
    for variable in variable_concepts_list:
        corresponding_symbols = [symbol for symbol, concept in concept_assignments.items() if concept==variable["name"]]
        del variable["type"]
        variable["representative_mathml"] = segmented_symbols_dict[corresponding_symbols[0]]
    
    variable_concepts_with_properties, log_json = auto_assign_variable_properties(dom_tree_copy, variable_concepts_list, eoi_ids_list, log_json)

    final_output_dict = {
        "concepts_info_list": []
    }

    assignments_inverse_map = dict()
    for placeholder_symbol, concept_name in concept_assignments.items():
        placeholder_mc_id = var_name_to_mc_id_map[placeholder_symbol]
        if concept_name in assignments_inverse_map.keys():
            assignments_inverse_map[concept_name].append(placeholder_mc_id)
        else:
            assignments_inverse_map[concept_name] = [placeholder_mc_id]

    for concept_info in concepts_list:
        concept_name = concept_info["name"]
        if concept_name in variable_concepts_with_properties.keys():
            concept_category = "variable"
            variable_concept = variable_concepts_with_properties[concept_name]
            concept_properties = {
                "tensor-rank": variable_concept["tensor_rank"],
                "variable-type": variable_concept["type"]
            }
        else:
            type_dict = {
                "OPERATOR": "operator",
                "DOMAIN": "domain",
                "INTEGRATION_VAR": "integration-var",
                "OTHER": "other"
            }
            concept_category = type_dict.get(concept_info["type"],"OTHER")
            concept_properties = {}

        final_output_dict["concepts_info_list"].append({
            "original_mc_ids": assignments_inverse_map[concept_name],
            "new_concept_info": {
                "code_var_name": concept_info["name"],
                "description": concept_info["description"] + "\nJUSTIFICATION:\n" + concept_info["justification"],
                "concept_category": concept_category,
                "properties": concept_properties
            }
        })

    log_json["final_output_dict"] = final_output_dict

    with open(llm_log_file, 'r') as log_file:
        llm_log = json.load(log_file)
    llm_log["AUTO_DEFINE_AND_ASSIGN_CONCEPTS"] = log_json
    with open(llm_log_file, 'w') as log_file:
        json.dump(llm_log,log_file, indent=4, cls=SetEncoder)

    return final_output_dict

def auto_define_concepts(html_tree_raw, segmented_symbols_list, eoi_ids_list, log_json):
    full_html_text_raw = etree.tostring(html_tree_raw, encoding='unicode')
    full_html_text = replace_with_unicode_name(full_html_text_raw)
    full_html_tree = etree.fromstring(full_html_text, etree.HTMLParser())

    ## FOR NOW WE ARE ONLY USING THE FIRST EoI AS REFERENCE TO SHORTEN CONTEXT. THIS SHOULD BE CHANGED TO A BETTER STRATEGY
    eoi_id = eoi_ids_list[0]
    weak_form = full_html_tree.find(f".//div[@id='{eoi_id}']")
    weak_form_string = etree.tostring(weak_form, encoding='unicode')

    html_text = full_html_text
    
    fits_in_context = False
    while fits_in_context == False:

        with open("llm_implementation/llm_prompt_files/define_concepts_prompt.txt", "r") as prompt_file:
            system_prompt_define_concepts = prompt_file.read()
        messages=[
                {"role": "system", "content": system_prompt_define_concepts},
                {"role": "user", "content": f"Paper section to study: {html_text}. Segmented symbols are: {segmented_symbols_list}. Build the concepts list."}
            ]
    
        tokens_count, max_model_len = check_token_usage(messages)
        max_token_len = min(max_context_length,max_model_len)
        print(f"Token count for prompt: {tokens_count}, Max token count: {max_context_length}, Model's max context length: {max_model_len}")
        print(f"Current html text length: {len(html_text)} characters.")
        if tokens_count >= max_token_len:
            print(f"Error: The prompt exceeds the model's context length. Token count for prompt: {tokens_count}, Model max context length: {max_model_len}")
            excess_ratio = (tokens_count-max_token_len)/tokens_count
            reduction_length_total = int(len(html_text) * excess_ratio)
            print(f"Reducing context length by approximately {reduction_length_total} characters.")
            html_text_divided = html_text.split(weak_form_string)
            if len(html_text_divided) == 2:
                len_html_text_back = len(html_text_divided[1])
                kept_chars_in_back = max(1000, len_html_text_back - reduction_length_total)
                html_text_back_reduced = html_text_divided[1][:kept_chars_in_back]
                print(f"Reducing from the back by approximately {len_html_text_back - kept_chars_in_back} characters.")
                reduction_length_front = max(0,reduction_length_total - (len_html_text_back - kept_chars_in_back))
                if len(html_text_divided[0]) - reduction_length_front < 1000:
                    print("Error: Unable to remove enough context to fit in the LLM's max context length.")
                    messages = None
                    break
                print(f"Reducing from the front by approximately {reduction_length_front} characters.")
                html_text_front_reduced = html_text_divided[0][reduction_length_front:]
                html_text_reduced = html_text_front_reduced + weak_form_string + html_text_back_reduced
            else:
                print("Error: Unable to split HTML text properly for context length reduction.")
                messages = None
                break
            html_text = html_text_reduced
        else:
            fits_in_context = True

    if messages is None:
        raise("Got None as message")
    
    chat_response = client.chat.completions.create(
        # model="Qwen/Qwen3-4B-Instruct-2507",
        model=get_running_model_name(),
        messages=messages
    )

    time.sleep(5)
    chat_response_string = chat_response.choices[0].message.content
    concepts_list = json.loads(chat_response_string)

    print(concepts_list)

    log_json["segmented_symbols_list"] = segmented_symbols_list
    log_json["concepts_list"] = concepts_list

    return concepts_list, log_json


def auto_assign_concepts(html_tree_raw, segmented_symbols_list, concepts_list, eoi_ids_list, log_json):    
    full_html_text_raw = etree.tostring(html_tree_raw, encoding='unicode')
    full_html_text = replace_with_unicode_name(full_html_text_raw)
    full_html_tree = etree.fromstring(full_html_text, etree.HTMLParser())

    ## FOR NOW WE ARE ONLY USING THE FIRST EoI AS REFERENCE TO SHORTEN CONTEXT. THIS SHOULD BE CHANGED TO A BETTER STRATEGY
    eoi_id = eoi_ids_list[0]
    weak_form = full_html_tree.find(f".//div[@id='{eoi_id}']")
    weak_form_string = etree.tostring(weak_form, encoding='unicode')

    html_text = full_html_text
    
    fits_in_context = False
    while fits_in_context == False:

        with open("llm_implementation/llm_prompt_files/assign_concepts_prompt.txt", "r") as prompt_file:
            system_prompt_assign_concepts = prompt_file.read()
        messages=[
                {"role": "system", "content": system_prompt_assign_concepts},
                {"role": "user", "content": f"Paper section to study: {html_text}. Segmented symbols are: {segmented_symbols_list}. Defined concepts are: {concepts_list}. Build the concept assignment dictionary."}
            ]

        tokens_count, max_model_len = check_token_usage(messages)
        max_token_len = min(max_context_length,max_model_len)
        print(f"Token count for prompt: {tokens_count}, Max token count: {max_context_length}, Model's max context length: {max_model_len}")
        print(f"Current html text length: {len(html_text)} characters.")
        if tokens_count >= max_token_len:
            print(f"Error: The prompt exceeds the model's context length. Token count for prompt: {tokens_count}, Model max context length: {max_model_len}")
            excess_ratio = (tokens_count-max_token_len)/tokens_count
            reduction_length_total = int(len(html_text) * excess_ratio)
            print(f"Reducing context length by approximately {reduction_length_total} characters.")
            html_text_divided = html_text.split(weak_form_string)
            if len(html_text_divided) == 2:
                len_html_text_back = len(html_text_divided[1])
                kept_chars_in_back = max(1000, len_html_text_back - reduction_length_total)
                html_text_back_reduced = html_text_divided[1][:kept_chars_in_back]
                print(f"Reducing from the back by approximately {len_html_text_back - kept_chars_in_back} characters.")
                reduction_length_front = max(0,reduction_length_total - (len_html_text_back - kept_chars_in_back))
                if len(html_text_divided[0]) - reduction_length_front < 1000:
                    print("Error: Unable to remove enough context to fit in the LLM's max context length.")
                    messages = None
                    break
                print(f"Reducing from the front by approximately {reduction_length_front} characters.")
                html_text_front_reduced = html_text_divided[0][reduction_length_front:]
                html_text_reduced = html_text_front_reduced + weak_form_string + html_text_back_reduced
            else:
                print("Error: Unable to split HTML text properly for context length reduction.")
                messages = None
                break
            html_text = html_text_reduced
        else:
            fits_in_context = True

    if messages is None:
        raise("Got None as message")
    
    chat_response = client.chat.completions.create(
        # model="Qwen/Qwen3-4B-Instruct-2507",
        model=get_running_model_name(),
        messages=messages
    )

    time.sleep(5)
    chat_response_string = chat_response.choices[0].message.content
    concept_assignment_dict = json.loads(chat_response_string)

    print(concept_assignment_dict)
    log_json["concept_assignments"] = concept_assignment_dict

    return concept_assignment_dict, log_json


def auto_assign_variable_properties(html_tree_raw, variable_concepts_list, eoi_ids_list, log_json):
    full_html_text_raw = etree.tostring(html_tree_raw, encoding='unicode')
    full_html_text = replace_with_unicode_name(full_html_text_raw)
    full_html_tree = etree.fromstring(full_html_text, etree.HTMLParser())

    ## FOR NOW WE ARE ONLY USING THE FIRST EoI AS REFERENCE TO SHORTEN CONTEXT. THIS SHOULD BE CHANGED TO A BETTER STRATEGY
    eoi_id = eoi_ids_list[0]
    weak_form = full_html_tree.find(f".//div[@id='{eoi_id}']")
    weak_form_string = etree.tostring(weak_form, encoding='unicode')

    html_text = full_html_text
    
    fits_in_context = False
    while fits_in_context == False:

        with open("llm_implementation/llm_prompt_files/assign_variable_properties.txt", "r") as prompt_file:
            system_prompt_assign_variable_properties = prompt_file.read()
        messages=[
                {"role": "system", "content": system_prompt_assign_variable_properties},
                {"role": "user", "content": f"Paper section to study: {html_text}. List of variables is: {variable_concepts_list}. Build variable properties dictionary."}
            ]

        tokens_count, max_model_len = check_token_usage(messages)
        max_token_len = min(max_context_length,max_model_len)
        print(f"Token count for prompt: {tokens_count}, Max token count: {max_context_length}, Model's max context length: {max_model_len}")
        print(f"Current html text length: {len(html_text)} characters.")
        if tokens_count >= max_token_len:
            print(f"Error: The prompt exceeds the model's context length. Token count for prompt: {tokens_count}, Model max context length: {max_model_len}")
            excess_ratio = (tokens_count-max_token_len)/tokens_count
            reduction_length_total = int(len(html_text) * excess_ratio)
            print(f"Reducing context length by approximately {reduction_length_total} characters.")
            html_text_divided = html_text.split(weak_form_string)
            if len(html_text_divided) == 2:
                len_html_text_back = len(html_text_divided[1])
                kept_chars_in_back = max(1000, len_html_text_back - reduction_length_total)
                html_text_back_reduced = html_text_divided[1][:kept_chars_in_back]
                print(f"Reducing from the back by approximately {len_html_text_back - kept_chars_in_back} characters.")
                reduction_length_front = max(0,reduction_length_total - (len_html_text_back - kept_chars_in_back))
                if len(html_text_divided[0]) - reduction_length_front < 1000:
                    print("Error: Unable to remove enough context to fit in the LLM's max context length.")
                    messages = None
                    break
                print(f"Reducing from the front by approximately {reduction_length_front} characters.")
                html_text_front_reduced = html_text_divided[0][reduction_length_front:]
                html_text_reduced = html_text_front_reduced + weak_form_string + html_text_back_reduced
            else:
                print("Error: Unable to split HTML text properly for context length reduction.")
                messages = None
                break
            html_text = html_text_reduced
        else:
            fits_in_context = True

    if messages is None:
        raise("Got None as message")
    
    chat_response = client.chat.completions.create(
        # model="Qwen/Qwen3-4B-Instruct-2507",
        model=get_running_model_name(),
        messages=messages
    )

    time.sleep(5)
    chat_response_string = chat_response.choices[0].message.content
    properties_assignment = json.loads(chat_response_string)

    print(properties_assignment)

    log_json["properties_assignment"] = properties_assignment

    return properties_assignment, log_json


def auto_highlight_sources(dom_tree_copy, mcdict_copy, mi_anno_copy, llm_log_file=None):
    log_json = dict()

    full_html_text_raw = etree.tostring(dom_tree_copy, encoding='unicode')
    full_html_text = replace_with_unicode_name(full_html_text_raw)
    full_html_tree = etree.fromstring(full_html_text, etree.HTMLParser())

    ## FOR NOW WE ARE ONLY USING THE FIRST EoI AS REFERENCE TO SHORTEN CONTEXT. THIS SHOULD BE CHANGED TO A BETTER STRATEGY
    eoi_ids_list = list(mcdict_copy.eoi_dict.keys())
    eoi_id = eoi_ids_list[0]
    weak_form = full_html_tree.find(f".//div[@id='{eoi_id}']")
    weak_form_string = etree.tostring(weak_form, encoding='unicode')

    html_text = full_html_text

    with open("llm_implementation/llm_prompt_files/identify_text_sources.txt", "r") as prompt_file:
            system_prompt_identify_text_sources = prompt_file.read()
    def get_messsages(system_prompt, context, justifications_list):
        messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Paper section to study: {context}.The concept and justifications to ground are: {justifications_list}. Build the specific passages list."}
            ]
        return messages
    
    fits_in_context = False
    while fits_in_context == False:
        messages = get_messsages(system_prompt_identify_text_sources, html_text, "")
        tokens_count, max_model_len = check_token_usage(messages)
        max_token_len = min(max_context_length,max_model_len)
        print(f"Token count for prompt: {tokens_count}, Max token count: {max_context_length}, Model's max context length: {max_model_len}")
        print(f"Current html text length: {len(html_text)} characters.")
        if tokens_count >= max_token_len:
            print(f"Error: The prompt exceeds the model's context length. Token count for prompt: {tokens_count}, Model max context length: {max_model_len}")
            excess_ratio = (tokens_count-max_token_len)/tokens_count
            reduction_length_total = int(len(html_text) * excess_ratio)
            print(f"Reducing context length by approximately {reduction_length_total} characters.")
            html_text_divided = html_text.split(weak_form_string)
            if len(html_text_divided) == 2:
                len_html_text_back = len(html_text_divided[1])
                kept_chars_in_back = max(1000, len_html_text_back - reduction_length_total)
                html_text_back_reduced = html_text_divided[1][:kept_chars_in_back]
                print(f"Reducing from the back by approximately {len_html_text_back - kept_chars_in_back} characters.")
                reduction_length_front = max(0,reduction_length_total - (len_html_text_back - kept_chars_in_back))
                if len(html_text_divided[0]) - reduction_length_front < 1000:
                    print("Error: Unable to remove enough context to fit in the LLM's max context length.")
                    messages = None
                    break
                print(f"Reducing from the front by approximately {reduction_length_front} characters.")
                html_text_front_reduced = html_text_divided[0][reduction_length_front:]
                html_text_reduced = html_text_front_reduced + weak_form_string + html_text_back_reduced
            else:
                print("Error: Unable to split HTML text properly for context length reduction.")
                messages = None
                break
            html_text = html_text_reduced
        else:
            fits_in_context = True

    if messages is None:
        raise("Got None as message")
    
    grounding_ids_dict = dict()
    matched_grounding_ids_dict = dict()
    for concept_id, concept_info in mcdict_copy.concepts.items():
        justifications_splitting = concept_info.description.split("JUSTIFICATION")
        if len(justifications_splitting) > 1:
            log_json[concept_id] = dict()

            justifications_dict = {
                "concept_name": concept_info.code_var_name,
                "description": justifications_splitting[0],
                "justifications": "\n".join(justifications_splitting[1:])
            }
            messages = get_messsages(system_prompt_identify_text_sources, html_text, justifications_dict)
    
            chat_response = client.chat.completions.create(
                # model="Qwen/Qwen3-4B-Instruct-2507",
                model=get_running_model_name(),
                messages=messages
            )

            time.sleep(5)
            chat_response_string = chat_response.choices[0].message.content
            grounding_ids_raw = json.loads(chat_response_string)

            log_json[concept_id]["justifications"] = justifications_dict
            log_json[concept_id]["grounding_ids_raw"] = grounding_ids_raw

            grounding_ids_dict[concept_id] = grounding_ids_raw
            matched_grounding_ids_dict[concept_id] = {
                'spans': set(),
                'divs': set()
            }
            for id in grounding_ids_raw:
                matching_paras_flag = check_if_tag_with_id_in_tree(dom_tree_copy, 'p', id)
                matching_spans_flag = check_if_tag_with_id_in_tree(dom_tree_copy, 'span', id)
                matching_eqns_flag = check_if_tag_with_id_in_tree(dom_tree_copy, 'div', id)
                if matching_paras_flag:
                    gd_text_spans_in_div = dom_tree_copy.xpath(f"//*[local-name()='p' and @id='{id}']//*[local-name()='span' and @class='gd_text']")
                    for gd_text in gd_text_spans_in_div:
                        matched_grounding_ids_dict[concept_id]["spans"].add(gd_text.get('id'))
                elif matching_spans_flag:
                    span_element = dom_tree_copy.xpath(f"//*[local-name()='span' and @id='{id}']")[0]
                    if span_element.get('class') == 'gd_text':
                        matched_grounding_ids_dict[concept_id]["spans"].add(id)
                elif matching_eqns_flag:
                    div_element = dom_tree_copy.xpath(f"//*[local-name()='div' and @id='{id}']")[0]
                    if div_element.get('class') == 'formula':
                        matched_grounding_ids_dict[concept_id]["divs"].add(id)
                else:
                    continue
            matched_grounding_ids_dict[concept_id]['spans'] = list(matched_grounding_ids_dict[concept_id]['spans'])
            matched_grounding_ids_dict[concept_id]['divs'] = list(matched_grounding_ids_dict[concept_id]['divs'])

    print(matched_grounding_ids_dict)
    log_json["total"] = {
        "matched_grounding_ids": matched_grounding_ids_dict
    }

    formal_sogs_list = []
    for concept_id, sog_ids_div in matched_grounding_ids_dict.items():
        for sog_id in sog_ids_div["spans"]:
            formal_sogs_list.append({
                "mc_id": concept_id,
                "start_id": sog_id+'-start',
                "stop_id": sog_id+'-end'
            })
        for sog_id in sog_ids_div["divs"]:
            formal_sogs_list.append({
                "mc_id": concept_id,
                "start_id": sog_id,
                "stop_id": sog_id
            })

    final_output_dict = {
        "sogs_info_list": formal_sogs_list
        }

    log_json["total"]["final_output_dict"] = final_output_dict
    with open(llm_log_file, 'r') as log_file:
        llm_log = json.load(log_file)
    llm_log["AUTO_HIGHLIGHT_SOURCES"] = log_json
    with open(llm_log_file, 'w') as log_file:
        json.dump(llm_log,log_file, indent=4, cls=SetEncoder)


    return final_output_dict