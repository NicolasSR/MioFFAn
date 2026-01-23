import json
import time
import re
import unicodedata

from copy import deepcopy
from collections import OrderedDict

import requests
from lxml import etree
from openai import OpenAI

from lib.llm_utilities import find_first_match_info, find_mathml_occurrences, get_all_ids_as_set, find_relationships_through_contained_ids, get_primitive_hex_set

"""
To run this script, a vllm server needs to be running. Call it via:
vllm serve Qwen/Qwen3-4B-Instruct-2507 --max_model_len 65536
"""

# Get OpenAI's API key and API base to use vLLM's API server.
with open("config.json", "r") as config_file:
    config=json.load(config_file)
    openai_api_key = config["OPENAI_API_KEY"]
    openai_api_base = config["OPENAI_API_BASE"]
    max_context_length_ratio = config["MAX_CONTEXT_LENGTH_RATIO"]

client = OpenAI(
    api_key=openai_api_key,
    base_url=openai_api_base,
)

def get_running_model_name():
    """
    Asks the vLLM server which model it is currently serving.
    Returns: The model ID string (e.g., 'meta-llama/Meta-Llama-3-8B-Instruct')
    """
    try:
        # Standard OpenAI endpoint to list models
        models = client.models.list()
        
        # vLLM usually serves just one model, so we take the first one.
        # If multiple are loaded (rare in vLLM), you might need logic to pick one.
        first_model = models.data[0].id
        return first_model
    except Exception as e:
        print(f"Error fetching model name: {e}")
        return None
    
def check_token_usage(messages):
    """
    Queries the vLLM server to get token count and context limit.
    Returns: (num_tokens, max_model_len)
    """
    # vLLM exposes this at the root /tokenize, not /v1/tokenize
    # If your base_url is http://localhost:8000/v1, strip the /v1
    base_url = str(client.base_url).replace("/v1", "").replace("/v1/", "")
    url = f"{base_url}/tokenize"
    
    model_name = get_running_model_name()
    payload = {
        "model": model_name,
        "messages": messages  # Pass the same messages list you would send to chat.completions
    }

    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        
        # vLLM returns 'count' (tokens) and 'max_model_len' (context limit)
        return data["count"], data["max_model_len"]
        
    except requests.exceptions.RequestException as e:
        print(f"Error checking tokens: {e}")
        return None, None

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


def auto_segment_symbols(html_tree_raw, eoi_ids_list):
    full_html_text_raw = etree.tostring(html_tree_raw, encoding='unicode')
    full_html_text = replace_with_unicode_name(full_html_text_raw)
    full_html_tree = etree.fromstring(full_html_text, etree.HTMLParser())

    multi_eoi_new_groups_dict = dict()
    multi_eoi_new_occurences_dict = dict()

    for eoi_id in eoi_ids_list:
        weak_form = full_html_tree.find(f".//div[@id='{eoi_id}']")
        weak_form_string = etree.tostring(weak_form, encoding='unicode')

        html_text = full_html_text

        fits_in_context = False
        while fits_in_context == False:

            with open("lib/llm_prompt_files/segment_symbols_prompt.txt", "r") as prompt_file:
                system_prompt_segmentation = prompt_file.read()
            messages=[
                    {"role": "system", "content": system_prompt_segmentation},
                    {"role": "user", "content": f"Paper section to study: {html_text}. Weak form appears in ID: {eoi_id}, and is repeated here: {weak_form_string}. Build the objects list."}
                ]
        
            tokens_count, max_model_len = check_token_usage(messages)
            max_model_len = max_context_length_ratio * max_model_len
            print(f"Token count for prompt: {tokens_count}, Model max context length: {max_model_len}")
            print(f"Current html text length: {len(html_text)} characters.")
            if tokens_count >= max_model_len:
                print(f"Error: The prompt exceeds the model's context length. Token count for prompt: {tokens_count}, Model max context length: {max_model_len}")
                excess_ratio = (tokens_count-0.8*max_model_len)/tokens_count
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

        deduplicated_objects_list = []
        seen_variable_names = set()
        for obj in objects_list:
            if obj["obj_name"] not in seen_variable_names:
                deduplicated_objects_list.append(obj)
                seen_variable_names.add(obj["obj_name"])
        objects_list = deduplicated_objects_list

        print(objects_list)

        new_occurences_dict = dict()
        new_groups_dict = dict()
        all_id_sets = []

        for obj in objects_list:
            variable_name = obj["obj_name"]
            print(variable_name)

            matches = find_mathml_occurrences(weak_form_string, obj['mathml_representation'])
            for match in matches:
                match_str = ''
                match_ids_set = set()
                primitive_hex_set = set()
                for element in match:
                    match_str += etree.tostring(element, encoding='unicode')
                    match_ids_set.update(get_all_ids_as_set(element))
                    primitive_hex_set.update(get_primitive_hex_set(element, html_tree_raw))
                print(match_str)
                identifier_info_first = find_first_match_info(match[0])
                start_id = identifier_info_first['id']
                tag_name = identifier_info_first['tag_name']
                ancestry_level_start = identifier_info_first['depth']
                all_id_sets.append({
                    "variable_name": variable_name,
                    "representative_id": start_id,
                    "ids_set": match_ids_set,
                    "ids_count": len(match_ids_set),
                    "mathml": match_str
                })
                if len(match) == 1:
                    occurrence_info = {
                            "comp_tag_id": start_id,
                            "tag_name": tag_name,
                            "primitive_symbols": deepcopy(primitive_hex_set)
                        }
                    if variable_name in new_occurences_dict:
                        new_occurences_dict[variable_name].append(occurrence_info)
                    else:
                        new_occurences_dict[variable_name]=[occurrence_info]
                else:
                    identifier_info_last = find_first_match_info(match[-1])
                    stop_id = identifier_info_last['id']
                    ancestry_level_stop = identifier_info_last['depth']
                    group_info = {
                        "ancestry_level_start": ancestry_level_start,
                        "ancestry_level_stop": ancestry_level_stop,
                        "start_id": start_id,
                        "stop_id": stop_id,
                        "primitive_symbols": deepcopy(primitive_hex_set)
                    }
                    if variable_name in new_groups_dict:
                        new_groups_dict[variable_name].append(group_info)
                    else:
                        new_groups_dict[variable_name]=[group_info]

        # Check for conflicts in symbol segmentation
        conflicts_list_raw = find_relationships_through_contained_ids(all_id_sets)
        print(conflicts_list_raw)
        if conflicts_list_raw:
            print("Conflicts detected in symbol segmentation:")
            new_groups_dict, new_occurences_dict = disambiguate_symbol_segmentation(html_text, eoi_id, weak_form_string, conflicts_list_raw, new_groups_dict, new_occurences_dict)

        multi_eoi_new_groups_dict[eoi_id] = new_groups_dict
        multi_eoi_new_occurences_dict[eoi_id] = new_occurences_dict

    # Merge all results from different EOIs into a single dictionary
    final_new_occurences_dict = dict()
    final_new_groups_dict = dict()
    
    for eoi_id_iter, new_occurences_dict_iter in multi_eoi_new_occurences_dict.items():
        for variable_name, occurences_list in new_occurences_dict_iter.items():
            if variable_name in final_new_occurences_dict:
                final_new_occurences_dict[variable_name].extend(occurences_list)
            else:
                final_new_occurences_dict[variable_name] = occurences_list

    for eoi_id_iter, new_groups_dict_iter in multi_eoi_new_groups_dict.items():
        for variable_name, groups_list in new_groups_dict_iter.items():
            if variable_name in final_new_groups_dict:
                final_new_groups_dict[variable_name].extend(groups_list)
            else:
                final_new_groups_dict[variable_name] = groups_list

    return final_new_occurences_dict, final_new_groups_dict
    

def disambiguate_symbol_segmentation(html_text, eoi_id, weak_form_string, conflicts_list_raw, new_groups_dict, new_occurences_dict):
    conflicts_dict = OrderedDict()
    for i, conflict_raw in enumerate(conflicts_list_raw):
        case_name = f"case_{i+1}"
        conflicts_dict[case_name] = {
            "parent": conflict_raw["parent_mathml"],
            "child": conflict_raw["child_mathml"]
        }

    print(conflicts_dict)

    with open("lib/llm_prompt_files/disambiguate_coinciding_symbols.txt", "r") as prompt_file:
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
    disambiguation_results_json = json.loads(chat_response_string)

    for case_name, result in disambiguation_results_json.items():
        i = int(case_name.split("_")[1]) - 1
        if result == "REMOVE":
            child_var_name = conflicts_list_raw[i]["child_variable_name"]
            child_representative_id = conflicts_list_raw[i]["child_representative_id"]
            if child_var_name in new_groups_dict.keys():
                new_groups_list = new_groups_dict[child_var_name]
                new_groups_list_filtered = [group_info for group_info in new_groups_list if not (group_info["start_id"] == child_representative_id)]
                new_groups_dict[child_var_name] = new_groups_list_filtered
            new_occurences_list = new_occurences_dict[child_var_name]
            new_occurences_list_filtered = [occurrence_info for occurrence_info in new_occurences_list if not (occurrence_info["comp_tag_id"] == child_representative_id)]
            new_occurences_dict[child_var_name] = new_occurences_list_filtered

    return new_groups_dict, new_occurences_dict