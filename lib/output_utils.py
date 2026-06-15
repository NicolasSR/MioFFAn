import json

def generate_FE_compiler_output(ast, ast_mc_dict, environment_settings_list, substitutions_dict_string):
    
    vars_dict = {
        "unknown_vars":[],
        "nodal_vars": [],
        "undefined_functions": [],
        "symbolic_vars": [],
        "constant_vars": [],
        "numerical_vars": [],
        "defined_functions": []
    }
    
    sorted_mc_lists = {}
    for mc_id, concept in ast_mc_dict.items():
        if concept.concept_category=="variable":
            var_type = concept.properties.get("variable-type", None)
            if var_type not in sorted_mc_lists:
                sorted_mc_lists[var_type] = []
            sorted_mc_lists[var_type].append(concept)

    for trial_func in sorted_mc_lists.get("trial-function", []):
        unknown_info = {
            "symbol": trial_func.code_var_name,
            "tensor_rank": trial_func.properties.get("tensor-rank", None)
        }
        for test_func in sorted_mc_lists.get("test-function", []):
            matched = False
            if test_func.properties.get("associated_trial_function", None) == trial_func.code_var_name:
                if not trial_func.properties.get("tensor-rank", None) == test_func.properties.get("tensor-rank", None):
                    raise ValueError(f"Tensor rank mismatch between trial function {trial_func.code_var_name} and test function {test_func.code_var_name}")
                unknown_info["test_function_symbol"] = test_func.code_var_name
                matched = True
                break
        if not matched:
            raise ValueError(f"No matching test function found for trial function {trial_func.code_var_name}")
        vars_dict["unknown_vars"].append(unknown_info)
    
    for concept in sorted_mc_lists.get("nodal-variable", []):
        vars_dict["nodal_vars"].append({
            "symbol": concept.code_var_name,
            "tensor_rank": concept.properties.get("tensor-rank", None)
        })

    for concept in sorted_mc_lists.get("symbolic-variable", []):
        concept_info = {
            "symbol": concept.code_var_name,
            "tensor_rank": concept.properties.get("tensor-rank", None)
        }
        if "positive" in concept.properties and concept.properties["positive"]=="on":
            concept_info["positive"] = True
        if "symmetric" in concept.properties and concept.properties["symmetric"]=="on":
            concept_info["symmetric"] = True
        if "third_symmetry" in concept.properties and concept.properties["third_symmetry"]=="on":
            concept_info["third_symmetry"] = True
        if "use_voigt_notation" in concept.properties and concept.properties["use_voigt_notation"]=="on":
            concept_info["use_voigt_notation"] = True
        vars_dict["symbolic_vars"].append(concept_info)

    for concept in sorted_mc_lists.get("constant-variable", []):
        concept_info = {
            "symbol": concept.code_var_name,
            "tensor_rank": concept.properties.get("tensor-rank", None)
        }
        if "positive" in concept.properties and concept.properties["positive"]=="on":
            concept_info["positive"] = True
        if "symmetric" in concept.properties and concept.properties["symmetric"]=="on":
            concept_info["symmetric"] = True
        if "third_symmetry" in concept.properties and concept.properties["third_symmetry"]=="on":
            concept_info["third_symmetry"] = True
        if "use_voigt_notation" in concept.properties and concept.properties["use_voigt_notation"]=="on":
            concept_info["use_voigt_notation"] = True
        vars_dict["constant_vars"].append(concept_info)

    for concept in sorted_mc_lists.get("numerical-variable", []):
        vars_dict["numerical_vars"].append({
            "symbol": concept.code_var_name,
            "tensor_rank": concept.properties.get("tensor-rank", None),
            "value": concept.properties.get("value", None)
        })

    for concept in sorted_mc_lists.get("defined-function", []):
        vars_dict["defined_functions"].append({
            "symbol": concept.code_var_name,
            "tensor_rank": concept.properties.get("tensor-rank", None)
        })

    for concept in sorted_mc_lists.get("undefined-function", []):
        vars_dict["undefined_functions"].append({
            "symbol": concept.code_var_name,
            "tensor_rank": concept.properties.get("tensor-rank", None),
            "dependencies": concept.properties.get("function-dependencies", [])
        })

    functional_ssa = []
    ast_list = ast.split("\n")
    for line in ast_list:
        if line.strip()=="":
            continue
        ssa = json.loads(line)
        if not ssa["op"]=="assignment":
            raise ValueError("Only assignment statements are supported as root of AST for FE compiler output generation.")
        new_var_name = ssa["args"][0]
        inner_ast = ssa["args"][1]
        functional_ssa.append({
            "name": new_var_name,
            "AST": inner_ast
        })

    config_settings_dict = {}
    for setting in environment_settings_list:
        raw_val = setting.value
        if raw_val in ["true","True"]:
            setting_val = True
        elif raw_val in ["false","False"]:
            setting_val = False
        else:
            try:
                setting_val = int(raw_val)
            except:
                try:
                    setting_val = float(raw_val)
                except:
                    setting_val = raw_val # If it's not a number, keep it as a string
        config_settings_dict[setting.name] = setting_val

    try:
        substitutions_dict = json.loads(substitutions_dict_string)
    except:
        raise ValueError("Could not parse substitutions dict")

    output = {
        "quantities": vars_dict,
        "functional_ssa": functional_ssa,
        "config_settings": config_settings_dict,
        "substitutions": substitutions_dict
    }

    return output