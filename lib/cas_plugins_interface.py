import json
import importlib
import inspect
from abc import ABC, abstractmethod

class CASPluginInterface(ABC):
    
    @abstractmethod
    def execute(self):
        """Every plugin must implement this method."""
        pass

    @classmethod
    def create(cls, paper_id, eoi_id):
        """Factory method to load and instantiate the configured plugin."""
        # 1. Load configuration
        with open('config.json', 'r') as f:
            cas_config = json.load(f)["CAS_PLUGIN_CONFIG"]
        
        plugin_name = cas_config["plugin_name"]
        
        # 2. Dynamically import the module
        # Assumes your files are inside a folder/package named 'cas_plugins'
        module_path = f"cas_plugins.{plugin_name}"
        plugin_module = importlib.import_module(module_path)
        
        # 3. Find the class inside the module that inherits from this interface
        for name, obj in inspect.getmembers(plugin_module, inspect.isclass):
            if issubclass(obj, cls) and obj is not cls:
                # 4. Instantiate and return the plugin instance
                return obj(cas_config = cas_config, paper_id = paper_id, eoi_id = eoi_id)
        
        raise ImportError(f"No valid CASPluginInterface subclass found in {module_path}")