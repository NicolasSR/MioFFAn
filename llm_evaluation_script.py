import json
from copy import deepcopy
from pathlib import Path
from collections import OrderedDict
import subprocess
import tempfile

from lxml import etree

from lib.datatypes import Group
from lib.util import wrap_custom_group

class LLMEvaluator():

    def __init__(self, htmls_root_dir, annotations_root_dir):
        self.htmls_root_dir = htmls_root_dir
        self.annotatioins_root_dir = annotations_root_dir
        self.sample_ids = [x.name for x in self.annotatioins_root_dir.iterdir() if x.is_dir()]
        print(f"Found data for {len(self.sample_ids)} samples." )

    def wrap_groups_in_html_tree(self, html_tree, anno_dict):
        for group_id, group_info_dict in anno_dict["groups"].items():
            group_info = Group(**group_info_dict)
            if not wrap_custom_group(html_tree, group_id, group_info):
                raise(f"Group {group_id} (LLM case) could not be wrapped")
    
    def get_all_mi_ids_as_set_from_id(self, html_tree, comp_tag_id, ordered=False):
        xpath_condition = 'local-name()="mi"'
        self.get_all_matching_ids_as_set_from_id(html_tree, xpath_condition, comp_tag_id, ordered)

    def get_all_matching_ids_as_set_from_id(self, html_tree, xpath_condition, comp_tag_id, ordered=False):
        elem_list = html_tree.findall(f".//*[@id='{comp_tag_id}']")
        if len(elem_list) != 1:
            raise(f"Problem finding element. id: {comp_tag_id}. elem_list: {elem_list}")
        return self.get_all_matching_ids_as_set_from_element(elem_list[0], xpath_condition, ordered)
    
    def get_all_matching_ids_as_set_from_element(self, root_elem, xpath_condition, ordered=False):
        mi_ids_list = []
        path = f'descendant-or-self::*[{xpath_condition}]'
        mi_elements = root_elem.xpath(path)
        for mi_elem in mi_elements:
            mi_ids_list.append(mi_elem.get("id"))
        if ordered:
            return mi_ids_list
        else:
            return set(mi_ids_list)
    
    def generate_CoNLL_file_structure(self, vocabulary: list, coreferences_dict: dict):
        """
        Transforms the coreference data into a structure that can be evaluated by the Reference Coreference Scorer in https://github.com/conll/reference-coreference-scorers/
        
        :param vocabulary: ordered list of tokens in the vocabulary
        :param coreferences_dict: dictionary with some arbitrary reference name as keys and a list of clusters (lists) of tokens as values. Clusters should contain consecutive tokens, otherwise the format conversion will fail. 
        """

        def check_consecutive(ids_list):
            return sorted(ids_list) == list(range(min(ids_list), max(ids_list) + 1))

        working_dict = OrderedDict()
        for i, token in enumerate(vocabulary):
            working_dict[token] = {"token_id": i, "coreference_column": []}

        for i, (symbol_name, id_clusters_list) in enumerate(coreferences_dict.items()):
            for ids_in_cluster in id_clusters_list:
                if len(ids_in_cluster) == 1:
                    working_dict[ids_in_cluster[0]]["coreference_column"].append(f"({i})")
                else:
                    token_ids_in_cluster = [working_dict[id]["token_id"] for id in ids_in_cluster]
                    if check_consecutive(token_ids_in_cluster):
                        working_dict[ids_in_cluster[0]]["coreference_column"].append(f"({i}")
                        working_dict[ids_in_cluster[-1]]["coreference_column"].append(f"{i})")
                    else:
                        raise(f"Within generate_CoNLL_file_structure(): Non-consecutive token ids in cluster. {symbol_name}: {ids_in_cluster}")

        out_multiline_string = "#begin document (TmpCase);\n"
        for token_value, token_data in working_dict.items():
            coreference_column_string = "|".join(token_data["coreference_column"])
            # line = "\t".join(['0', '0', str(token_data["token_id"]), coreference_column_string])
            line = "\t".join(['0', '0', str(token_data["token_id"]), token_value, coreference_column_string]) # For debuging
            out_multiline_string = out_multiline_string + line + "\n"
        out_multiline_string = out_multiline_string + "#end document"
        
        return out_multiline_string

    def run_conll_scorer(self, key_string, response_string, metric="all"):
        """
        Runs the official CoNLL Perl scorer using python strings as input.
        """
        with open("./config.json", "r") as global_config_file:
            global_config = json.load(global_config_file)
        conll_scorer_dir = Path(global_config["CONLL_SCORER_DIR"])
        
        # Create temporary files (text mode)
        # 1. We use delete=True so they vanish automatically when closed
        # 2. We allow reading by formatting to utf-8 (standard for CoNLL)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=True) as key_file, \
            tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=True) as resp_file:
            
            # Write your strings to the temp files
            key_file.write(key_string)
            resp_file.write(response_string)
            
            # IMPORTANT: Flush the write buffer to disk/OS so the Perl script sees the data
            key_file.flush()
            resp_file.flush()
            
            # Run the Perl script pointing to the temp file paths
            # Replace 'perl' and 'scorer.pl' with your actual paths if necessary
            command = ["perl", str(conll_scorer_dir / "scorer.pl"), metric, key_file.name, resp_file.name]
            
            try:
                result = subprocess.run(
                    command, 
                    capture_output=True, 
                    text=True, 
                    check=True
                )
                return result.stdout
                
            except subprocess.CalledProcessError as e:
                print(f"Error running scorer: {e.stderr}")
                return None
            
    def get_lowest_common_ancestor(self, node1, node2):
        path1 = node1.xpath('ancestor-or-self::*')
        path2 = node2.xpath('ancestor-or-self::*')
        lca = None
        # Iterate through both paths simultaneously
        for n1, n2 in zip(path1, path2):
            if n1 == n2:
                lca = n1  # Keep updating as long as they match
            else:
                break
        return lca
            
    def sog_to_leaf_span_and_eq_ids(self, html_tree, sog_info):
        start_node_id_split = sog_info["start_id"].split('-')
        stop_node_id_split = sog_info["stop_id"].split('-')
        if len(start_node_id_split) > 1:
            start_node_id = "".join(start_node_id_split[:-1])
        else:
            start_node_id = start_node_id_split[0]

        if len(stop_node_id_split) > 1:
            stop_node_id = "".join(stop_node_id_split[:-1])
        else:
            stop_node_id = stop_node_id_split[0]
        
        # Use XPath to find elements and ensure they are either <span> or <div class="formula">
        tag_and_class_requirements = "(local-name()='span' and @class='gd_text') or (local-name()='div' and @class='formula')"
        xpath_query = f"//*[@id=$id and ({tag_and_class_requirements})]"
        start_node_matches = html_tree.xpath(xpath_query, id=start_node_id)
        stop_node_matches = html_tree.xpath(xpath_query, id=stop_node_id)
        if not len(start_node_matches)==1 or not len(stop_node_matches)==1:
            print(f"No unique match found for id: {start_node_id} or {stop_node_id}")
            return None  # One or both elements don't exist or don't match types
        start_node = start_node_matches[0]
        stop_node = stop_node_matches[0]

        lca = self.get_lowest_common_ancestor(start_node, stop_node)
        ordered_span_and_eq_ids = self.get_all_matching_ids_as_set_from_element(lca, tag_and_class_requirements, ordered=True)
        ordered_span_and_eq_ids = ordered_span_and_eq_ids[ordered_span_and_eq_ids.index(start_node_id):ordered_span_and_eq_ids.index(stop_node_id)+1]

        ids_to_remove = set()
        for i, parent_id in enumerate(ordered_span_and_eq_ids):
            # Get the current element
            parent_el = html_tree.xpath(f"//*[@id='{parent_id}']")
            if not parent_el:
                continue
            parent_node = parent_el[0]
            # Get the remaining IDs in the list
            remaining_ids = ordered_span_and_eq_ids[i+1:]
            for child_id in remaining_ids:
                # Check if any descendant has the target ID
                is_descendant = parent_node.xpath(f".//*[@id='{child_id}']")
                if is_descendant:
                    ids_to_remove.add(parent_id)
                    break
        
        if ids_to_remove:
            ordered_leaf_span_and_eq_ids = [x for x in ordered_span_and_eq_ids if x not in ids_to_remove]
        else:
            ordered_leaf_span_and_eq_ids = ordered_span_and_eq_ids

        return ordered_leaf_span_and_eq_ids

    def compute_coverage_of_placeholder_assignment(self, html_tree, placeholders_llm_mcdict, placeholders_llm_anno, placeholders_truth_mcdict, placeholders_truth_anno):
        """
        Compares the amount of <mi> tags with placeholder assinged for both LLM and ground truth.
        It checks the <mi> tags included in groups. It does only considers each <mi> tag once (no repetitions)
        Result is LLM count over ground truth count. Also outputs ground truth count for reference.
        """

        llm_html_tree = deepcopy(html_tree)
        self.wrap_groups_in_html_tree(llm_html_tree, placeholders_llm_anno)
        llm_mi_ids_set = set()
        for comp_tag_id in placeholders_llm_mcdict["occurences_dict"].keys():
            llm_mi_ids_set.update(self.get_all_mi_ids_as_set_from_id(llm_html_tree, comp_tag_id))

        truth_html_tree = deepcopy(html_tree)
        self.wrap_groups_in_html_tree(truth_html_tree, placeholders_truth_anno)
        truth_mi_ids_set = set()
        for comp_tag_id in placeholders_truth_mcdict["occurences_dict"].keys():
            truth_mi_ids_set.update(self.get_all_mi_ids_as_set_from_id(truth_html_tree, comp_tag_id))

        return len(llm_mi_ids_set)/len(truth_mi_ids_set), len(truth_mi_ids_set)
    
    def compute_eoi_accurate_symbols(self, llm_log, eoi_id):
        """
        Compares the amount of proposed symbols (deduplicated) to the amount of symbols that can actually be found within the EoI.
        It does not account for symbol conflict resolution, so some symbols may even be discarded later.
        This gives an idea of how well the LLM matches MathML structures from reference text, and how well it is able to localize
        structures that appear in a specific part of the reference.
        Returns the ratio of accepted symbols / proposed symbols (deduplicated), and the absolute amount of proposed symbols (deduplicated)
        """

        proposed_symbols = llm_log["AUTO_SEGMENT_SYMBOLS"][eoi_id]["deduplicated_list"]

        accepted_symbols_set = set()
        groups_dict = llm_log["AUTO_SEGMENT_SYMBOLS"][eoi_id]["new_groups_dict"]
        occurrences_dict = llm_log["AUTO_SEGMENT_SYMBOLS"][eoi_id]["new_occurences_dict"]
        for symbol_name in groups_dict.keys():
            accepted_symbols_set.add(symbol_name)
        for symbol_name in occurrences_dict.keys():
            accepted_symbols_set.add(symbol_name)

        return len(accepted_symbols_set)/len(proposed_symbols), len(proposed_symbols)
    
    def compute_sets_correspondance(self, html_tree, eoi_ids_list, placeholders_llm_mcdict, placeholders_llm_anno, placeholders_truth_mcdict, placeholders_truth_anno):
        
        for eoi_id in eoi_ids_list:
            # Get sorted (document order) list of all available mi ids within the equations. Order of equations is not important. 
            all_mi_ids_list = self.get_all_mi_ids_as_set_from_id(html_tree, eoi_id, ordered=True)

        llm_html_tree = deepcopy(html_tree)
        self.wrap_groups_in_html_tree(llm_html_tree, placeholders_llm_anno)

        llm_classified_mi_ids_dict = dict()
        for comp_tag_id, occurrence_info in placeholders_llm_mcdict["occurences_dict"].items():
            concept_name = occurrence_info["mc_id"]
            mi_ids_list = self.get_all_mi_ids_as_set_from_id(llm_html_tree, comp_tag_id, ordered=True)
            if concept_name in llm_classified_mi_ids_dict.keys():
                llm_classified_mi_ids_dict[concept_name].append(mi_ids_list)
            else:
                llm_classified_mi_ids_dict[concept_name] = [mi_ids_list]

        response_conll_string = self.generate_CoNLL_file_structure(all_mi_ids_list, llm_classified_mi_ids_dict)

        truth_html_tree = deepcopy(html_tree)
        self.wrap_groups_in_html_tree(truth_html_tree, placeholders_truth_anno)
        
        truth_classified_mi_ids_dict = dict()
        for comp_tag_id, occurrence_info in placeholders_truth_mcdict["occurences_dict"].items():
            concept_name = occurrence_info["mc_id"]
            mi_ids_list = self.get_all_mi_ids_as_set_from_id(truth_html_tree, comp_tag_id, ordered=True)
            if concept_name in truth_classified_mi_ids_dict.keys():
                truth_classified_mi_ids_dict[concept_name].append(mi_ids_list)
            else:
                truth_classified_mi_ids_dict[concept_name] = [mi_ids_list]

        key_conll_string = self.generate_CoNLL_file_structure(all_mi_ids_list, truth_classified_mi_ids_dict)

        scorer_output = self.run_conll_scorer(key_conll_string, response_conll_string)
        print(scorer_output)

    def compute_accepted_sogs_ratio(self):
        print("NEED TO IMPLEMENT compute_accepted_sogs_ratio")

    def compute_sog_sets_comparisons(self, html_tree, llm_mcdict, truth_mcdict):
        """
        Compare sogs for each symbol.
        We assume that the symbol segmentation is the same in both sog prediction and ground truth (with same comp_tag_ids)
        """
        for comp_tag_id in truth_mcdict["occurences_dict"].keys():
            print(comp_tag_id)
            llm_concept_name = llm_mcdict["occurences_dict"][comp_tag_id]["mc_id"]
            truth_concept_name = truth_mcdict["occurences_dict"][comp_tag_id]["mc_id"]
            llm_leaf_sog_ids = set()
            truth_leaf_sog_ids = set()
            for sog_info in llm_mcdict["concepts"][llm_concept_name]["sog_list"]:
                print('LLM', sog_info)
                print(self.sog_to_leaf_span_and_eq_ids(html_tree, sog_info))
                llm_leaf_sog_ids.update(set(self.sog_to_leaf_span_and_eq_ids(html_tree, sog_info)))
            for sog_info in truth_mcdict["concepts"][truth_concept_name]["sog_list"]:
                print('TRUTH', sog_info)
                print(self.sog_to_leaf_span_and_eq_ids(html_tree, sog_info))
                truth_leaf_sog_ids.update(set(self.sog_to_leaf_span_and_eq_ids(html_tree, sog_info)))

            print(llm_leaf_sog_ids)
            print(truth_leaf_sog_ids)
            print()

    def run_placeholders_study_for_first_sample(self):
        first_sample = self.sample_ids[0]
        annotations_dir_path = self.annotatioins_root_dir / first_sample

        llm_log_path =  annotations_dir_path / f"{first_sample}_llm_log.json"
        placeholders_llm_mcdict_path = annotations_dir_path / f"{first_sample}_mcdict_llm_placeholders.json"
        placeholders_llm_anno_path = annotations_dir_path / f"{first_sample}_anno_llm_placeholders.json"
        placeholders_truth_mcdict_path = annotations_dir_path / f"{first_sample}_mcdict_true_placeholders.json"
        placeholders_truth_anno_path = annotations_dir_path / f"{first_sample}_anno_true_placeholders.json"
        with open(llm_log_path, 'r') as llm_log_file:
            llm_log =  json.load(llm_log_file)
        with open(placeholders_llm_mcdict_path, 'r') as placeholders_llm_mcdict_file:
            placeholders_llm_mcdict =  json.load(placeholders_llm_mcdict_file)
        with open(placeholders_llm_anno_path, 'r') as placeholders_llm_anno_file:
            placeholders_llm_anno =  json.load(placeholders_llm_anno_file)
        with open(placeholders_truth_mcdict_path, 'r') as placeholders_truth_mcdict_file:
            placeholders_truth_mcdict =  json.load(placeholders_truth_mcdict_file)
        with open(placeholders_truth_anno_path, 'r') as placeholders_truth_anno_file:
            placeholders_truth_anno =  json.load(placeholders_truth_anno_file)

        html_file_path = self.htmls_root_dir / f'{first_sample}.html'
        with open(html_file_path, 'r') as html_file:
            html_tree = etree.parse(html_file)

        eoi_ids_list = list(placeholders_truth_mcdict["eoi_dict"].keys())

        coverage_ratio, total_mi_elements = self.compute_coverage_of_placeholder_assignment(html_tree, placeholders_llm_mcdict, placeholders_llm_anno, placeholders_truth_mcdict, placeholders_truth_anno)
        print(f"MI coverage: {coverage_ratio*100}% (from {total_mi_elements} <mi> elements)")

        for eoi_id in eoi_ids_list:
            eoi_accurate_symbols_ratio, proposed_symbols_len = self.compute_eoi_accurate_symbols(llm_log, eoi_id)
            print(f"EoI {eoi_id} results:")
            print(f"    EoI-accurate symbols ratio: {eoi_accurate_symbols_ratio*100}% (from {proposed_symbols_len} proposed symbols (deduplicated))")

        self.compute_sets_correspondance(html_tree, eoi_ids_list, placeholders_llm_mcdict, placeholders_llm_anno, placeholders_truth_mcdict, placeholders_truth_anno)
    
    def run_concepts_assignment_study_for_first_sample(self):
        first_sample = self.sample_ids[0]
        annotations_dir_path = self.annotatioins_root_dir / first_sample

        concepts_llm_mcdict_path = annotations_dir_path / f"{first_sample}_mcdict_llm_concepts.json"
        concepts_llm_anno_path = annotations_dir_path / f"{first_sample}_anno_llm_concepts.json"
        concepts_truth_mcdict_path = annotations_dir_path / f"{first_sample}_mcdict_true_final.json"
        concepts_truth_anno_path = annotations_dir_path / f"{first_sample}_anno_true_final.json"
        with open(concepts_llm_mcdict_path, 'r') as concepts_llm_mcdict_file:
            concepts_llm_mcdict =  json.load(concepts_llm_mcdict_file)
        with open(concepts_llm_anno_path, 'r') as concepts_llm_anno_file:
            concepts_llm_anno =  json.load(concepts_llm_anno_file)
        with open(concepts_truth_mcdict_path, 'r') as concepts_truth_mcdict_file:
            concepts_truth_mcdict =  json.load(concepts_truth_mcdict_file)
        with open(concepts_truth_anno_path, 'r') as concepts_truth_anno_file:
            concepts_truth_anno =  json.load(concepts_truth_anno_file)

        html_file_path = self.htmls_root_dir / f'{first_sample}.html'
        with open(html_file_path, 'r') as html_file:
            html_tree = etree.parse(html_file)

        eoi_ids_list = list(concepts_truth_mcdict["eoi_dict"].keys())

        self.compute_sets_correspondance(html_tree, eoi_ids_list, concepts_llm_mcdict, concepts_llm_anno, concepts_truth_mcdict, concepts_truth_anno)
    
    def run_sog_study_for_first_sample(self):

        first_sample = self.sample_ids[0]
        annotations_dir_path = self.annotatioins_root_dir / first_sample

        sogs_llm_mcdict_path = annotations_dir_path / f"{first_sample}_mcdict_llm_sogs.json"
        sogs_truth_mcdict_path = annotations_dir_path / f"{first_sample}_mcdict_true_final.json"
        with open(sogs_llm_mcdict_path, 'r') as sogs_llm_mcdict_file:
            sogs_llm_mcdict =  json.load(sogs_llm_mcdict_file)
        with open(sogs_truth_mcdict_path, 'r') as sogs_truth_mcdict_file:
            sogs_truth_mcdict =  json.load(sogs_truth_mcdict_file)

        html_file_path = self.htmls_root_dir / f'{first_sample}.html'
        with open(html_file_path, 'r') as html_file:
            html_tree = etree.parse(html_file)

        self.compute_sog_sets_comparisons(html_tree, sogs_llm_mcdict, sogs_truth_mcdict)

        self.compute_accepted_sogs_ratio()


if __name__ == "__main__":
    htmls_root_dir = Path("./sources")
    annotations_root_dir = Path("./annotated_samples")
    llm_evaluator = LLMEvaluator(htmls_root_dir, annotations_root_dir)

    # llm_evaluator.run_placeholders_study_for_first_sample()
    # llm_evaluator.run_concepts_assignment_study_for_first_sample()
    llm_evaluator.run_sog_study_for_first_sample()

