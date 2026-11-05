import re
import shutil
from pathlib import Path


class CheckpointService:
    def __init__(self, mi_anno, mcdict):
        self.mi_anno = mi_anno
        self.mcdict = mcdict

    def create_checkpoint(self, checkpoint_tag):
        self.mcdict.dump(checkpoint_tag)
        self.mi_anno.dump(checkpoint_tag)

        llm_log_path = self.mcdict.file.with_stem(re.sub("_mcdict", "_llm_log", self.mcdict.file.stem))
        if llm_log_path.is_file():
            target_llm_log_path = llm_log_path.with_stem(llm_log_path.stem + "_" + checkpoint_tag)
            shutil.copyfile(llm_log_path, target_llm_log_path)

    def clear_annotation_data(self, checkpoint_tag):
        data_mcdict_path = self.mcdict.file
        data_anno_path = self.mi_anno.file
        data_llm_log_path = self.mcdict.file.with_stem(re.sub("_mcdict", "_llm_log", self.mcdict.file.stem))

        if checkpoint_tag is None:
            target_mc_dict_path = Path("templates", data_mcdict_path.parts[-2], data_mcdict_path.name)
            target_anno_path = Path("templates", data_mcdict_path.parts[-2], data_anno_path.name)
        elif any(char.isalnum() for char in checkpoint_tag):
            target_mc_dict_path = data_mcdict_path.with_stem(data_mcdict_path.stem + "_" + checkpoint_tag)
            target_anno_path = data_anno_path.with_stem(data_anno_path.stem + "_" + checkpoint_tag)
            subst_string = f"_llm_log_{checkpoint_tag}"
            target_llm_log_path = self.mcdict.file.with_stem(re.sub("_mcdict", subst_string, self.mcdict.file.stem))
        else:
            raise ValueError("Checkpoint tag is not valid")

        shutil.copyfile(target_mc_dict_path, data_mcdict_path)
        shutil.copyfile(target_anno_path, data_anno_path)

        if data_llm_log_path.is_file():
            data_llm_log_path.unlink()
        if checkpoint_tag is not None and target_llm_log_path.is_file():
            shutil.copyfile(target_llm_log_path, data_llm_log_path)
