# Refactoring Task: Decompose MioFFAnServer God Class

## Problem Statement

The file `server/mioffan.py` contains a single class `MioFFAnServer` (~1,303 lines, ~45 methods) that handles all server-side business logic. It mixes together:

- HTML page rendering (6+ page methods, all identical boilerplate)
- Concept/SoG/Group/EoI CRUD operations (~10+ methods)
- LLM automation orchestration (3 methods, ~350 lines, with duplicated context-reduction logic)
- CAS/Kratos code generation (4 methods)
- Checkpoint and data management (2 methods)
- JSON serialization helpers (4 methods)
- Property validation HTML generation (2 methods)
- Sample switching (2 methods)
- Edit ID counters (2 methods)

Every POST endpoint repeats the same boilerplate: `request.json` -> `check_document_edit_id` -> `check_missing_variables` -> inner method -> `json.dumps` response -> `except PostRequestError`.

In `server/__main__.py`, 35+ route definitions are thin copy-paste wrappers forwarding to `server.method()`.

**Consequences:** No modularity, no testability, high cognitive load, difficulty adding features, duplicated patterns everywhere.

---

## Constraints

- **Do NOT change the external API.** Every endpoint must return the same response format.
- **Do NOT modify the client.** The TypeScript frontend must work unchanged.
- **Refactor incrementally.** After each step, the server must still start and serve requests correctly.
- **Workspace root:** `/home/nsibuet/srt_sandboxes/MioFFAn_sandbox/MioFFAn/`

---

## Proposed Solution (4 Phases)

### Phase 1: Extract Service Modules

Create `server/services/` directory. Extract groups of related methods into standalone service classes/modules. Each service should accept the data it needs as constructor args or method parameters, not hold global mutable state.

#### Target structure:

```
server/services/
    __init__.py
    annotation_service.py    # concept, SoG, group, EoI CRUD
    llm_service.py            # 3 LLM automation methods + shared context-reduction logic
    cas_service.py            # Kratos template + code generation
    checkpoint_service.py     # checkpointing and data clearing
    render_service.py         # page rendering (deduplicate the 6+ identical blocks)
    json_serialization.py     # gen_mcdict_json, gen_mi_anno_json, gen_hex_to_mc_map, get_sample_info
    validation_service.py     # property validation HTML generation
```

#### Per-service details:

**`annotation_service.py`**
- Extract: `assign_concept`, `assign_concept_inner`, `remove_concept`, `register_concept`, `register_concept_inner`, `add_sog`, `add_sog_inner`, `delete_sog`, `change_sog_type`, `add_eoi`, `remove_eoi`, `add_group`, `add_group_inner`, `remove_group`, `edit_symbolic_code`, `edit_environment_settings`, `edit_occurence_properties`
- Constructor accepts: `mi_anno: MiAnno`, `mcdict: McDict`, `config: dict`
- Each method operates on the passed objects, calls `dump()` and edit ID updaters as needed

**`llm_service.py`**
- Extract: `auto_segment_symbols`, `auto_assign_concepts`, `auto_highlight_sources`
- Constructor accepts: `mi_anno`, `mcdict`, `tree`, `config`, `paper_id`
- Factor out the duplicated `fits_in_context` context-reduction loop into a shared helper function (it's copy-pasted identically across all 3 LLM methods and also appears in `llm_implementations.py`)

**`cas_service.py`**
- Extract: `submit_template_file`, `download_output_file`, `run_cas`, `_generate_fe_definition_dict`
- Constructor accepts: `kratos_templates: dict`, `kratos_output_files: dict`, `mcdict`, `paper_id`

**`checkpoint_service.py`**
- Extract: `create_data_checkpoint`, `clear_annotation_data`
- Constructor accepts: `mi_anno`, `mcdict`

**`render_service.py`**
- Extract: `index`, `equations_of_interest_selector`, `group_creator`, `symbolic_code_assigner`, `edit_mcdict`, `nav`, `sample_nav`, `initialize_main_pages`, `add_data_math_concept`
- Constructor accepts: `tree`, `mi_anno`, `mcdict`, `config`, `paper_id`
- The 6 page-rendering methods are nearly identical (deepcopy tree -> initialize_main_pages -> extract body/style -> render_template). Deduplicate into a single `_render_page(template_name, **kwargs)` helper.

**`json_serialization.py`**
- Extract: `gen_mcdict_json`, `gen_mi_anno_json`, `gen_hex_to_mc_map`, `get_sample_info`
- Module-level functions, accept `mcdict`, `mi_anno`, `paper_id` as args

**`validation_service.py`**
- Extract: `get_occurence_properties_options_html`, `get_concept_properties_options_html`
- Constructor accepts: `mcdict`, `config`

#### Migration procedure per service:

1. Create the new file with the service class.
2. Move the methods from `MioFFAnServer` into it.
3. Replace `self.xxx` references with explicit parameters or service-level attributes.
4. In `MioFFAnServer.__init__`, instantiate the service and store it (e.g., `self.annotation_svc = AnnotationService(...)`).
5. Update each server method to delegate: `return self.annotation_svc.assign_concept(...)`.
6. Verify server still starts and endpoints work.

---

### Phase 2: Request Validation Decorator

Create `server/decorators.py` with a decorator that eliminates the repeated POST-handling boilerplate:

```python
from functools import wraps
from flask import request, json
from lib.util import check_document_edit_id, check_missing_variables, PostRequestError

def validated_post(server, edit_id_attr, **required_fields):
    """Decorator for POST endpoints that need edit-id and field validation."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            try:
                res = request.json
                edit_id_value = getattr(server, edit_id_attr)
                check_document_edit_id(edit_id_value, res.get(edit_id_attr.replace('_edit_id', '_edit_id')))
                extracted = {k: res.get(k) for k in required_fields}
                check_missing_variables(**extracted)
                return fn(res, *args, **kwargs)
            except PostRequestError as e:
                return json.dumps(e.to_dict()), e.http_status
        return wrapper
    return decorator
```

Apply this decorator to every POST method in `MioFFAnServer` that currently has the manual try/except/check pattern. This should eliminate ~30% of the code.

---

### Phase 3: Flask Blueprints

Split `server/__main__.py` into route modules under `server/routes/`:

```
server/routes/
    __init__.py
    annotation_routes.py    # concept, SoG, group, EoI endpoints
    llm_routes.py            # LLM automation endpoints
    cas_routes.py            # CAS endpoints
    page_routes.py           # page rendering endpoints
    data_routes.py           # checkpoint, JSON, sample switching
```

Each file defines a Flask Blueprint and registers its routes. `__main__.py` becomes a thin entry point that creates the server, registers blueprints, and calls `app.run()`.

---

### Phase 4: Basic Test Skeleton

Create `tests/` with at least:

```
tests/
    __init__.py
    test_annotation_service.py
    test_checkpoint_service.py
    test_json_serialization.py
```

Use `pytest`. Each service class should be instantiable without a Flask app, so tests can call methods directly with mocked or fixture data files.

---

## Execution Order

1. Phase 1 (services), one service module at a time. After each extraction, verify the server starts and a representative endpoint still works.
2. Phase 2 (decorator), applied after Phase 1 is complete.
3. Phase 3 (blueprints), applied after Phase 2.
4. Phase 4 (tests), can start in parallel with Phase 1 but complete after Phase 2.

## Files To Reference

- `server/mioffan.py` — source to refactor from
- `server/__main__.py` — route definitions
- `lib/annotation.py` — MiAnno and McDict data classes
- `lib/datatypes.py` — dataclass definitions
- `lib/util.py` — helper functions and PostRequestError
- `lib/concept_properties.py` — validation logic
- `llm_implementation/llm_implementations.py` — LLM implementation functions
- `lib/llm_utilities.py` — LLM utilities (note: context-reduction logic is duplicated here too)
