import json
from copy import deepcopy
from pathlib import Path
from collections import OrderedDict
import subprocess
import tempfile
from docopt import docopt

from lxml import etree

from lib.datatypes import Group
from lib.util import wrap_custom_group
from lib.version import VERSION
from lib.logger import main_logger

EVALUATION_SCHEMA = {
    "segmentation": {
        "truth":    "true_placeholders",
        "llm":      "llm_placeholders",
        "llm_log":      None
    },
    # "segmentation_custom": {
    #     "truth":    "true_placeholders",
    #     "llm":      "llm_placeholders",
    #     "llm_log":  "llm_placeholders"
    # },
    "concepts_assignment": {
        "truth":    "true_final",
        "llm":      "llm_final",
        "llm_log":      None
    },
    "highlight": {
        "truth":    "true_final",
        "llm":      "llm_final",
        "llm_log":      None
    }
}

# meta
PROG_NAME = "tools.evaluate_llm"
HELP = """Evaluate results from LLM automation tasks

Usage:
    {p} [options]

Options:
    --task=STR          Task to evaluate ({tasks_list}, 'all') [default: all]
    --sample=STR        Sample to evaluate (write sample name or "all" for all samples) [default: all]

    --data=DIR          Dir for data outputs [default: ./data]
    --sources=DIR       Dir for HTML outputs [default: ./sources]

    --debug             Show debug messages
    -q, --quiet         Show less messages

    -h, --help          Show this screen and exit
    -V, --version       Show version
""".format(
    p=PROG_NAME,
    tasks_list=', '.join(EVALUATION_SCHEMA.keys())
)

class LLMEvaluator():

    def __init__(self, samples_list, sources_dir, data_dir):
        self.sources_dir = sources_dir
        self.data_dir = data_dir
        self.samples_dict = self.filter_unannotated_samples(samples_list)

    def get_file_paths_for_task_and_sample(self, task, sample_name):
        task_tags_dict = EVALUATION_SCHEMA[task]
        out_dict = {}
        out_dict["truth_anno_path"] = self.data_dir / sample_name / (sample_name+"_anno_"+task_tags_dict["truth"]+".json")
        out_dict["llm_anno_path"] = self.data_dir / sample_name / (sample_name+"_anno_"+task_tags_dict["llm"]+".json")
        out_dict["truth_mcdict_path"] = self.data_dir / sample_name / (sample_name+"_mcdict_"+task_tags_dict["truth"]+".json")
        out_dict["llm_mcdict_path"] = self.data_dir / sample_name / (sample_name+"_mcdict_"+task_tags_dict["llm"]+".json")
        if task_tags_dict["llm_log"] is not None:
            out_dict["llm_log_path"] = self.data_dir / sample_name / (sample_name+"_llm_log_"+task_tags_dict["llm_log"]+".json")
        return out_dict

    def filter_unannotated_samples(self, samples_list):
        print("Filtering samples:")
        samples_dict = {}
        for task in EVALUATION_SCHEMA.keys():
            samples_dict[task] = []
        for sample_name in samples_list:
            for task in EVALUATION_SCHEMA.keys():
                paths_dict = self.get_file_paths_for_task_and_sample(task, sample_name)
                paths_check_list = [p.is_file() for p in paths_dict.values()]
                if all(paths_check_list):
                    samples_dict[task].append(sample_name)
                else:
                    print(f"Missing annotation data for sample {sample_name} in task {task}.")
        return samples_dict
    
    def get_file_contents_for_task_and_sample(self, task, sample_name):
        paths_dict = self.get_file_paths_for_task_and_sample(task, sample_name)
        out_dict = {}
        with open(paths_dict["truth_anno_path"], 'r') as f:
            out_dict["truth_anno_json"] = json.load(f)
        with open(paths_dict["llm_anno_path"], 'r') as f:
            out_dict["llm_anno_json"] =  json.load(f)
        with open(paths_dict["truth_mcdict_path"], 'r') as f:
            out_dict["truth_mcdict_json"] =  json.load(f)
        with open(paths_dict["llm_mcdict_path"], 'r') as f:
            out_dict["llm_mcdict_json"] =  json.load(f)
        if paths_dict.get("llm_log_path") is not None:
            with open(paths_dict["llm_log_path"], 'r') as f:
                out_dict["llm_log_json"] =  json.load(f)

        source_file_path = self.sources_dir / (sample_name+".html")
        with open(source_file_path, 'r') as html_file:
            out_dict["html_tree"] = etree.parse(html_file)

        return out_dict

        

    def wrap_groups_in_html_tree(self, html_tree, anno_dict):
        for group_id, group_info_dict in anno_dict["groups"].items():
            group_info = Group(**group_info_dict)
            if not wrap_custom_group(html_tree, group_id, group_info):
                raise(f"Group {group_id} (LLM case) could not be wrapped")
    
    def get_all_mi_ids_as_set_from_id(self, html_tree, comp_tag_id, ordered=False):
        xpath_condition = 'local-name()="mi"'
        return self.get_all_matching_ids_as_set_from_id(html_tree, xpath_condition, comp_tag_id, ordered)

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

        coverage_percentage = len(llm_mi_ids_set)/len(truth_mi_ids_set)*100

        return coverage_percentage, len(truth_mi_ids_set)
    
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

        scores = {"muc": None, "bcub": None, "ceafe": None, "lea": None}
        for metric in scores.keys():
            # print(f"Results for metric {metric}:")
            scorer_output = self.run_conll_scorer(key_conll_string, response_conll_string, metric=metric)
            # print(scorer_output)
            isolated_F1_score = scorer_output.splitlines()[-2].split()[-1]
            scores[metric] = float(isolated_F1_score.strip('%'))
        scores["average"] = (scores["muc"]+scores["bcub"]+scores["ceafe"])/3
        return scores

    def compute_accepted_sogs_ratio(self):
        print("NEED TO IMPLEMENT compute_accepted_sogs_ratio")

    def compute_sog_sets_comparisons(self, html_tree, llm_mcdict, truth_mcdict):
        """
        Compare sogs for each symbol.
        We assume that the symbol segmentation is the same in both sog prediction and ground truth (with same comp_tag_ids)
        """
        jaccard_scores_dict = dict()
        sdi_scores_dict = dict()
        for comp_tag_id in truth_mcdict["occurences_dict"].keys():
            llm_concept_name = llm_mcdict["occurences_dict"][comp_tag_id]["mc_id"]
            truth_concept_name = truth_mcdict["occurences_dict"][comp_tag_id]["mc_id"]
            llm_leaf_sog_ids = set()
            truth_leaf_sog_ids = set()
            for sog_info in llm_mcdict["concepts"][llm_concept_name]["sog_list"]:
                llm_leaf_sog_ids.update(set(self.sog_to_leaf_span_and_eq_ids(html_tree, sog_info)))
            for sog_info in truth_mcdict["concepts"][truth_concept_name]["sog_list"]:
                truth_leaf_sog_ids.update(set(self.sog_to_leaf_span_and_eq_ids(html_tree, sog_info)))

            intersection = llm_leaf_sog_ids.intersection(truth_leaf_sog_ids)
            union = llm_leaf_sog_ids.union(truth_leaf_sog_ids)
            jaccard_score = len(intersection)/len(union) if len(union) > 0 else 1.0
            jaccard_scores_dict[comp_tag_id] = jaccard_score*100
            sdi_score = 2*jaccard_score/(1+jaccard_score)
            sdi_scores_dict[comp_tag_id] = sdi_score*100

        return jaccard_scores_dict, sdi_scores_dict

    def run_segmentation_eval(self):
        task_name = "segmentation"
        evaluation_results = {}
        for sample_name in self.samples_dict[task_name]:
            evaluation_results[sample_name] = {}
            sample_results = evaluation_results[sample_name]

            file_contents = self.get_file_contents_for_task_and_sample(task_name, sample_name)
            truth_anno_json = file_contents["truth_anno_json"]
            llm_anno_json = file_contents["llm_anno_json"]
            truth_mcdict_json = file_contents["truth_mcdict_json"]
            llm_mcdict_json = file_contents["llm_mcdict_json"]
            html_tree = file_contents["html_tree"]

            eoi_ids_list = list(truth_mcdict_json["eoi_dict"].keys())

            sample_results["mi_coverage"] = {}
            coverage_ratio, total_mi_elements = self.compute_coverage_of_placeholder_assignment(html_tree, llm_mcdict_json, llm_anno_json, truth_mcdict_json, truth_anno_json)
            sample_results["mi_coverage"]["ratio"] = coverage_ratio
            sample_results["mi_coverage"]["total"] = total_mi_elements

            sample_results["coreference"] = {}
            conll_scores = self.compute_sets_correspondance(html_tree, eoi_ids_list, llm_mcdict_json, llm_anno_json, truth_mcdict_json, truth_anno_json)
            sample_results["coreference"]["CoNLL"] = conll_scores["average"]
            sample_results["coreference"]["LEA"] = conll_scores["lea"]

        return evaluation_results
    
    def run_segmentation_custom_eval(self):
        task_name = "segmentation_custom"
        evaluation_results = {}
        for sample_name in self.samples_dict[task_name]:
            evaluation_results[sample_name] = {}
            sample_results = evaluation_results[sample_name]

            file_contents = self.get_file_contents_for_task_and_sample(task_name, sample_name)
            truth_mcdict_json = file_contents["truth_mcdict_json"]
            llm_log_json = file_contents["llm_log_json"]

            eoi_ids_list = list(truth_mcdict_json["eoi_dict"].keys())

            sample_results["symbols_replication"] = {}
            symbols_replication_results = sample_results["symbols_replication"]
            for eoi_id in eoi_ids_list:
                symbols_replication_results[eoi_id] = {}
                accuracy_ratio, total_symbols = self.compute_eoi_accurate_symbols(llm_log_json, eoi_id)
                symbols_replication_results[eoi_id]["accuracy"] = accuracy_ratio
                symbols_replication_results[eoi_id]["total"] = total_symbols
            
        return evaluation_results


    def run_concepts_assignment_eval(self):
        task_name = "concepts_assignment"
        evaluation_results = {}
        for sample_name in self.samples_dict[task_name]:
            evaluation_results[sample_name] = {}
            sample_results = evaluation_results[sample_name]

            file_contents = self.get_file_contents_for_task_and_sample(task_name, sample_name)
            truth_anno_json = file_contents["truth_anno_json"]
            llm_anno_json = file_contents["llm_anno_json"]
            truth_mcdict_json = file_contents["truth_mcdict_json"]
            llm_mcdict_json = file_contents["llm_mcdict_json"]
            html_tree = file_contents["html_tree"]

            eoi_ids_list = list(truth_mcdict_json["eoi_dict"].keys())

            sample_results["coreference"] = {}
            conll_scores = self.compute_sets_correspondance(html_tree, eoi_ids_list, llm_mcdict_json, llm_anno_json, truth_mcdict_json, truth_anno_json)
            sample_results["coreference"]["CoNLL"] = conll_scores["average"]
            sample_results["coreference"]["LEA"] = conll_scores["lea"]
            
        return evaluation_results

    def run_highlight_eval(self):
        task_name = "highlight"
        evaluation_results = {}
        for sample_name in self.samples_dict[task_name]:
            evaluation_results[sample_name] = {}
            sample_results = evaluation_results[sample_name]

            file_contents = self.get_file_contents_for_task_and_sample(task_name, sample_name)
            truth_mcdict_json = file_contents["truth_mcdict_json"]
            llm_mcdict_json = file_contents["llm_mcdict_json"]
            html_tree = file_contents["html_tree"]

            sample_results["set_comparison"] = {}
            jaccard_scores_dict, sdi_scores_dict = self.compute_sog_sets_comparisons(html_tree, llm_mcdict_json, truth_mcdict_json)
            jaccard_average = sum(jaccard_scores_dict.values())/len(jaccard_scores_dict)
            sdi_average = sum(sdi_scores_dict.values())/len(sdi_scores_dict)
            sample_results["set_comparison"]["avg_jaccard"] = jaccard_average
            sample_results["set_comparison"]["avg_sdi"] = sdi_average

        return evaluation_results



if __name__ == "__main__":
    # parse options
    args = docopt(HELP, version=VERSION)

    main_logger.set_logger(args['--quiet'], args['--debug'])

    task = args["--task"]

    # dirs and files
    data_dir = Path(args['--data'])
    sources_dir = Path(args['--sources'])

    sample_name = args["--sample"]
    if sample_name == "all":
        samples_list = [str(x.stem) for x in sources_dir.iterdir() if x.suffix == ".html"]
    else:
        source_path = sources_dir / sample_name+".html"
        if source_path.is_file():
            samples_list = [sample_name]
        else:
            raise "HTML source not found for specfied sample"
    
    evaluator = LLMEvaluator(samples_list, sources_dir, data_dir)

    if task in list(EVALUATION_SCHEMA.keys()):
        eval_function = getattr(evaluator,"run_"+task+"_eval")
        eval_results = eval_function()
    elif task == "all":
        eval_results = {}
        for current_task in EVALUATION_SCHEMA.keys():
            eval_function = getattr(evaluator,"run_"+current_task+"_eval")
            eval_results[current_task] = eval_function()
    else:
        raise "Unkonwn specified task to evaluate"
    
    print("Printing results:")
    print(json.dumps(eval_results, indent=4))

