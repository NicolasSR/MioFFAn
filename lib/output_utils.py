import json

def generate_FE_compiler_output(ast, ast_mc_dict):
    
    vars_dict = {
        "unknown_vars":[],
        "nodal_vars": [],
        "undefined_functions": [],
        "symbolic_vars": [],
        "numerical_vars": [],
        "defined_functions": []
    }
    
    sorted_mc_lists = {}
    config_settings_dict = {}
    for mc_id, concept in ast_mc_dict.items():
        if concept.concept_category=="variable":
            var_type = concept.properties.get("variable-type", None)
            if var_type not in sorted_mc_lists:
                sorted_mc_lists[var_type] = []
            sorted_mc_lists[var_type].append(concept)

        elif concept.concept_category=="config_setting":
            config_type = concept.properties.get("config-type", None)
            if config_type == "bool":
                if concept.properties.get("bool-value", None) == "on":
                    value = True
                else:
                    value = False
            elif config_type == "string":
                value = concept.properties.get("string-value", None)
            elif config_type == "number":
                value = concept.properties.get("number-value", None)
            else:
                raise ValueError(f"Unsupported config type: {config_type}")
            config_settings_dict[concept.code_var_name] = value


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
        vars_dict["symbolic_vars"].append(concept_info)

    for concept in sorted_mc_lists.get("numerical-variable", []):
        vars_dict["numerical_vars"].append({
            "symbol": concept.code_var_name,
            "tensor_rank": concept.properties.get("tensor-rank", None),
            "value": concept.properties.get("value", None)
        })

    for concept in sorted_mc_lists.get("defined-function", []):
        vars_dict["defined_functions"].append({
            "symbol": concept.code_var_name,
            "tensor_rank": concept.properties.get("tensor-rank", None),
            "value": concept.properties.get("function-implementation", None)
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

    output = {
        "quantities": vars_dict,
        "functional_ssa": functional_ssa,
        "config_settings": config_settings_dict,
    }

    return output