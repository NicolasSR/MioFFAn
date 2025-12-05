# Annotation data handler
import json
from pathlib import Path
from logging import Logger
from dataclasses import asdict

from lib.datatypes import PrimitiveSymbol, MathConcept, Group, Occurence, SoG

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
        self.eoi_list: list = data['eoi_list']
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
                    'eoi_list': self.eoi_list,
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

        # self.concepts: dict[str, MathConcept] = cast_dicts_to_dataclass(data['concepts'], MathConcept)
        concepts = dict()
        for id, obj in data['concepts'].items():
            obj["sog_list"] = [SoG(**sog) for sog in obj["sog_list"]]
            concepts[id] = MathConcept(**obj)
        self.concepts: dict[str, MathConcept] = concepts

        self.occurences: dict[str, Occurence] = cast_dicts_to_dataclass(data['occurences'], Occurence)


    def dump(self):

        with open(self.file, 'w') as f:
            dump_json(
                {
                    '_author': self.author,
                    '_mcdict_version': self.mcdict_version,
                    'concepts': cast_dataclass_to_dicts(self.concepts),
                    'next_available_mc_id': self.next_available_mc_id,
                    'occurences': cast_dataclass_to_dicts(self.occurences)
                },
                f,
            )