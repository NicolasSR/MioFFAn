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


    def execute(self):
        case_name = f"{self.paper_id}_{self.eoi_id}"

        kratos_output_file_path = Path("output", f"{case_name}.json")
        if not kratos_output_file_path.is_file():
            raise FileNotFoundError(f"File {kratos_output_file_path} not found.") 
        
        case_dir = Path(self.cas_config["cases_dir"], case_name)

        # Create the case directory if it doesn't exist
        case_dir.mkdir(parents=True, exist_ok=True)

        # Copy the case to the cases directory
        shutil.copy2(kratos_output_file_path, case_dir / "fe_definition.json")

        # Generate default config file if there is none already
        if not (case_dir / "case_config.json").is_file():
            self._genetarate_default_case_config_file(case_dir)

        # Execute the Kratos FE Compiler
        self._execute_kratos_fe_compiler(case_name)
        



    def _genetarate_default_case_config_file(self, case_dir: Path):
        default_config = {
            "applied_configuration": {
                "dim": 2,
                "nnodes": 3
            },
            "compatibilities_dict": {
                "2": [3],
                "3": [4]
            }
        }

        with open(case_dir / "case_config.json", "w") as f:
            json.dump(default_config, f, indent=4)

    
    def _execute_kratos_fe_compiler(self, case_name):
        python_path = self._get_conda_python_path(self.cas_config["conda_env"])
        # compiler_script_path = Path(self.cas_config["cas_dir"],"kratos_fe_compiler","__main__.py")
        try:
            # Run the subprocess using the specific conda environment's python interpreter
            result = subprocess.run(
                [python_path, "-m", "kratos_fe_compiler", case_name],
                # [python_path, "-m", "kratos_fe_compiler", "--overwrite", case_name],
                cwd=Path(self.cas_config["cas_dir"]),
                capture_output=True,
                text=True,
                # timeout=self.timeout,
                check=True
            )
            print("Subprocess Output:", result.stdout)
            
        except subprocess.CalledProcessError as e:
            print("Subprocess failed!", e.stderr)

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

        