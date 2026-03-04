# Annotation data handler
import json
from pathlib import Path
from logging import Logger
from dataclasses import asdict

from lib.datatypes import PrimitiveSymbol, MathConcept, Group, Occurence, SoG, EoI
from lib.concept_properties import validate_properties

from lib.logger import main_logger

def dump_json(data, fp):
    json.dump(data, fp, ensure_ascii=False, indent=4, sort_keys=True, separators=(',', ': '))
    fp.write('\n')

logger = main_logger.getChild('annotation')

def cast_dicts_to_dataclass(dict_of_dicts: dict, dataclass):
    out_dict = dict()
    for id, obj in dict_of_dicts.items():
        out_dict[id] = dataclass(**obj)
    return out_dict

def cast_dataclass_to_dicts(dict_of_dataclass: dict):
    out_dict = dict()
    for id, obj in dict_of_dataclass.items():
        out_dict[id] = asdict(obj)
    return out_dict

class MiAnno:
    """Math identifier annotation"""

    def __init__(self, file: Path) -> None:
        with open(file, encoding='utf-8') as f:
            data = json.load(f)

        if data.get('_anno_version', '') != '1.0':
            logger.warning('%s: Annotation data version is incompatible', file)

        self.file = file
        self.anno_version: str = data.get('_anno_version', 'unknown')
        self.annotator: str = data.get('_annotator', 'unknown')
        self.next_available_group_id: int = data['next_available_group_id']

        self.primitive_symbols: dict[str, PrimitiveSymbol] = cast_dicts_to_dataclass(data['primitive_symbols'], PrimitiveSymbol)
        self.groups: dict[str, Group] = cast_dicts_to_dataclass(data['groups'], Group)

    def dump(self) -> None:

        with open(self.file, 'w') as f:
            dump_json(
                {
                    '_anno_version': self.anno_version,
                    '_annotator': self.annotator,
                    'primitive_symbols': cast_dataclass_to_dicts(self.primitive_symbols),
                    'groups': cast_dataclass_to_dicts(self.groups),
                    'next_available_group_id': self.next_available_group_id,
                },
                f,
            )


class McDict:
    """Math concept dictionary"""

    def __init__(self, file: Path) -> None:
        with open(file, encoding='utf-8') as f:
            data = json.load(f)

        if data.get('_mcdict_version', '') != '1.0':
            logger.warning('%s: Math concept dict version is incompatible', file)

        self.file = file
        self.author: str = data.get('_author', 'unknown')
        self.mcdict_version: str = data.get('_mcdict_version', 'unknown')
        self.next_available_mc_id = data['next_available_mc_id']

        with open('config.json', 'r') as f:
            taxonomy_config = json.load(f)["CONCEPT_TAXONOMY"]

        # self.concepts: dict[str, MathConcept] = cast_dicts_to_dataclass(data['concepts'], MathConcept)
        concepts = dict()
        for id, obj in data['concepts'].items():
            obj["sog_list"] = [SoG(**sog) for sog in obj["sog_list"]]
            category = obj["concept_category"]
            if category == "symbol-placeholder" and not category in taxonomy_config.keys():
                category_config = {}
            else:
                category_config = taxonomy_config.get(category)
                if not category_config:
                    raise ValueError(f"Unknown category: {category}")
            is_valid, error_msg = validate_properties(category_config.get('concept_fields', {}), obj["properties"])
            if not is_valid:
                raise ValueError(f"Invalid concept properties for concept {id}: {error_msg}")
            concepts[id] = MathConcept(**obj)
        self.concepts: dict[str, MathConcept] = concepts

        occurrences = dict()
        for id, obj in data['occurences_dict'].items():
            mc_category = self.concepts[obj['mc_id']].concept_category
            if mc_category == "symbol-placeholder" and not mc_category in taxonomy_config.keys():
                category_config = {}
            else:
                category_config = taxonomy_config.get(mc_category)
                if not category_config:
                    raise ValueError(f"Unknown category: {mc_category}")
            total_properties = self.concepts[obj['mc_id']].properties.copy()
            total_properties.update(obj["properties"])
            is_valid, error_msg = validate_properties(category_config.get('occurrence_fields', {}), total_properties)
            if not is_valid:
                raise ValueError(f"Invalid concept properties for concept {id}: {error_msg}")
            occurrences[id] = Occurence(**obj)
        self.occurences_dict: dict[str, Occurence] = occurrences

        self.eoi_dict: dict[str, EoI] = cast_dicts_to_dataclass(data['eoi_dict'], EoI)


    def dump(self):
        with open(self.file, 'w') as f:
            dump_json(
                {
                    '_author': self.author,
                    '_mcdict_version': self.mcdict_version,
                    'concepts': cast_dataclass_to_dicts(self.concepts),
                    'next_available_mc_id': self.next_available_mc_id,
                    'occurences_dict': cast_dataclass_to_dicts(self.occurences_dict),
                    'eoi_dict': cast_dataclass_to_dicts(self.eoi_dict)
                },
                f,
            )