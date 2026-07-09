from pathlib import Path
import shutil
import json
import subprocess
import os

from lib.cas_plugins_interface import CASPluginInterface

class KratosFECompilerPlugin(CASPluginInterface):
    def __init__(self, cas_config, paper_id, eoi_id):
        print("KratosFECompilerPlugin Initialized!")
        self.paper_id = paper_id
        self.eoi_id = eoi_id
        self.cas_config = cas_config

    def execute(self, input_data):
        case_name = f"{self.paper_id}_{self.eoi_id}"

        fe_definition_dict = input_data["fe_definition_dict"]
        template_files_content = input_data["template_files_content"]
        
        case_dir = Path(self.cas_config["cases_dir"], case_name)

        # Create the case directory if it doesn't exist
        case_dir.mkdir(parents=True, exist_ok=True)

        # Generate the fe_definition file within the case directory
        with open(case_dir / "fe_definition.json", "w") as fe_definition_file:
            json.dump(fe_definition_dict, fe_definition_file, indent = 4)
        
        # Write element and condition templates in case directory
        element_template_file_name = "element_template.cpp"
        condition_template_file_name = "condition_template.cpp"
        with open(case_dir / element_template_file_name, "w") as element_template_file:
            element_template_file.write(template_files_content["element"])
        with open(case_dir / condition_template_file_name, "w") as condition_template_file:
            condition_template_file.write(template_files_content["condition"])

        # Generate the case config file for the compiler
        element_output_file_name = "element.cpp"
        condition_output_file_name = "condition.cpp"
        default_config = {
            "kratos_configuration": {
                "input_output_paths": [
                    {
                        "template": element_template_file_name,
                        "output": element_output_file_name
                    },{
                    "template": condition_template_file_name,
                    "output": condition_output_file_name
                    }
                ]
            },
        }
        with open(case_dir / "case_config.json", "w") as f:
            json.dump(default_config, f, indent=4)

        # Execute the Kratos FE Compiler
        self._execute_kratos_fe_compiler(case_name)

        output_content = dict()
        with open(case_dir / "element.cpp") as element_output_file:
            output_content["element"] = element_output_file.read()
        with open(case_dir / "condition.cpp") as condition_output_file:
            output_content["condition"] = condition_output_file.read()

        return output_content
        

    def _execute_kratos_fe_compiler(self, case_name):
        python_path = self._get_conda_python_path(self.cas_config["conda_env"])
        # compiler_script_path = Path(self.cas_config["cas_dir"],"kratos_fe_compiler","__main__.py")
        try:
            # Run the subprocess using the specific conda environment's python interpreter
            result = subprocess.run(
                [python_path, "-m", "kratos_fe_compiler", case_name, "--type=kratos", "--overwrite"],
                # [python_path, "-m", "kratos_fe_compiler", "--overwrite", case_name],
                cwd=Path(self.cas_config["cas_dir"]),
                capture_output=True,
                text=True,
                # timeout=self.timeout,
                check=True
            )
            print("Subprocess Output:", result.stdout)
            
        except subprocess.CalledProcessError as e:
            raise Exception("Subprocess failed!", e.stderr)

    def _get_conda_python_path(self, env_name: str):
        """
        Finds the absolute path to the Python executable of a specific Conda environment.
        """
        # 1. Quick sanity check: If looking for base, check common names
        if env_name.lower() == "base":
            env_name = "base"

        # 2. Ensure 'conda' is actually installed and available in the current PATH
        if not shutil.which("conda"):
            raise EnvironmentError("Conda executable not found in system PATH.")

        try:
            # 3. Ask conda for the list of all environments in JSON format
            result = subprocess.run(
                ["conda", "env", "list", "--json"],
                capture_output=True,
                text=True,
                check=True
            )
            
            conda_data = json.loads(result.stdout)
            environments = conda_data.get("envs", [])
            
        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            raise RuntimeError(f"Failed to query conda environments: {e}")

        # 4. Filter the environments to find the one matching your target name
        target_prefix = None
        for env_path in environments:
            # The environment name is the final folder in its path (e.g., /envs/my_env)
            if os.path.basename(env_path) == env_name:
                target_prefix = env_path
                break
            # Special edge-case handle for the root 'base' environment
            elif env_name == "base" and "envs" not in os.path.basename(os.path.dirname(env_path)):
                # This is usually the root installation folder
                target_prefix = env_path

        if not target_prefix:
            raise ValueError(f"Conda environment '{env_name}' could not be found.")

        # 5. Build the platform-specific path to the Python binary
        if os.name == "nt":  # Windows
            python_executable = os.path.join(target_prefix, "python.exe")
        else:  # Linux / macOS
            python_executable = os.path.join(target_prefix, "bin", "python")

        # 6. Final safety validation
        if not os.path.exists(python_executable):
            raise FileNotFoundError(f"Found env path, but Python binary missing at: {python_executable}")

        return python_executable
    
    def generate_fe_definition_dict(self, ast, ast_mc_dict, environment_settings_list, substitutions_dict_string):
    
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

        if substitutions_dict_string.strip()  == "":
            substitutions_dict = {"pre_lhs": [], "post_lhs": []}
        else:
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