# Phase 1 Refactoring Report: Decomposing `MioFFAnServer`

## Overview

Extracted all business logic from the monolithic `MioFFAnServer` class into seven service modules under `server/services/`. The original class (~1,303 lines, ~45 methods) now functions as a thin facade (~622 lines) that delegates to dedicated services.

## New File Structure

```
server/services/
├── __init__.py                  (13 lines)   -- public exports
├── annotation_service.py        (273 lines)  -- Concept/SoG/Group/EoI CRUD + make_concept helper
├── llm_service.py               (196 lines)  -- 3 LLM automation orchestrators
├── cas_service.py               (105 lines)  -- Kratos template upload, CAS execution, output download
├── json_serialization.py         (88 lines)  -- Pure functions: mcdict/mi_anno JSON, hex map, sample info, preprocess_mcdict
├── render_service.py             (88 lines)  -- Deduplicated page rendering + _initialize_main_pages + _add_data_math_concept
├── checkpoint_service.py         (42 lines)  -- Checkpoint creation and annotation data clearing
└── validation_service.py         (61 lines)  -- Property validation HTML generation
```

**Total service code:** 866 lines across 7 modules (excluding `__init__.py`).

## Changes Per Service

### `annotation_service.py` (273 lines)
- **Extracted methods:** `assign_concept`, `assign_concept_inner`, `remove_concept`, `register_concept`, `register_concept_inner`, `add_sog`, `add_sog_inner`, `delete_sog`, `change_sog_type`, `add_eoi`, `remove_eoi`, `add_group`, `add_group_inner`, `remove_group`, `edit_symbolic_code`, `edit_environment_settings`, `edit_occurence_properties`
- **Also moved:** `make_concept` helper (previously in `mioffan.py`) to resolve circular import (`mioffan → services → annotation_service → mioffan`)
- **Constructor:** Accepts `mi_anno`, `mcdict`, `config`, plus edit-ID getters/incrementers via callbacks to avoid tight coupling
- **Notable design:** Edit ID counters remain on `MioFFAnServer` and are accessed via lambda callbacks, avoiding circular dependencies

### `llm_service.py` (196 lines)
- **Extracted methods:** `auto_segment_symbols`, `auto_assign_concepts`, `auto_highlight_sources`
- **Constructor:** Accepts `mi_anno`, `mcdict`, `tree`, `config`, `paper_id`, and a reference to `AnnotationService` (to delegate concept/group registration during LLM automation)
- **Key pattern:** Each LLM method deep-copies `tree`, `mcdict`, and `mi_anno` before processing, preserving immutability of server state during LLM calls

### `cas_service.py` (105 lines)
- **Extracted methods:** `submit_template_file`, `download_output_file`, `run_cas`, `_generate_fe_definition_dict`
- **Constructor:** Accepts `kratos_templates`, `kratos_output_files` (mutable dicts), `mcdict`, `paper_id`

### `checkpoint_service.py` (42 lines)
- **Extracted methods:** `create_checkpoint`, `clear_annotation_data`
- **Constructor:** Accepts `mi_anno`, `mcdict`

### `render_service.py` (88 lines)
- **Extracted methods:** `index`, `equations_of_interest_selector`, `group_creator`, `symbolic_code_assigner`, `edit_mcdict`, `nav`, `sample_nav`
- **Major deduplication:** The 6 nearly-identical page-rendering methods now call a single `_render_page(template_name, title, **kwargs)` helper that: deep-copies the tree, calls `_initialize_main_pages`, extracts body/style, and renders the template
- **Also extracted:** `_initialize_main_pages` and `_add_data_math_concept` as private helpers
- **Constructor:** Accepts `tree`, `mi_anno`, `mcdict`, `config`, `paper_id`
- **Special:** `GIT_REVISON` is set via a module-level variable to avoid circular imports

### `json_serialization.py` (88 lines)
- **Extracted as pure functions:** `gen_mcdict_json`, `gen_mi_anno_json`, `gen_hex_to_mc_map`, `get_sample_info`, `preprocess_mcdict`
- **Design:** Stateless module-level functions; accept data objects as parameters

### `validation_service.py` (61 lines)
- **Extracted methods:** `get_occurence_properties_options_html`, `get_concept_properties_options_html`
- **Constructor:** Accepts `mcdict`, `config`

## Changes to `server/mioffan.py`

### Before (~1,303 lines)
- Single class containing all business logic inline
- No separation of concerns; mixing rendering, CRUD, LLM, CAS, checkpointing, serialization, and validation

### After (622 lines, ~52% reduction)
- `__init__` stores state + instantiates 7 services
- Every method body is a thin delegation wrapper: `return self.annotation_svc.assign_concept(...)` etc.
- POST endpoints still handle Flask request parsing, edit-ID checking, and error catching (to be handled by Phase 2 decorator)
- New `_reinit_services()` method re-binds all services to fresh `MiAnno`/`McDict`/tree state on sample switch

### What Stayed on `MioFFAnServer`
- Request parsing and validation boilerplate (target for Phase 2)
- Edit ID counters (`mi_anno_edit_id`, `mcdict_edit_id`) and updaters
- Sample switching logic (`switch_to_sample`, `list_sample_ids`, `_reinit_services`)
- Flask response formatting (JSON dumps, redirects, flash messages)
- File path management and config loading

## Verification

- Import test passes: `python3 -c "from server.mioffan import MioFFAnServer"` succeeds without errors
- Server startup test: `python3 -m server` loads correctly (exit on "No .html files found in sources" is expected -- no sample data loaded, not a code error)

## Known Pre-Existing Issues (Not Introduced by This Refactoring)

1. **`build_occurence_properties_options_html`** and **`build_concept_properties_options_html`** are called in `validation_service.py` (lines 25 and 55) but are never defined anywhere in the codebase -- will crash at runtime when those endpoints are hit.

2. **`Occurence` dataclass** has a field named `properties`, but the original code at line 760 referenced `occurence.options` -- likely a field name mismatch.

## Next Steps (Per `refactor_server_architecture.md`)

| Phase | Status | Description |
|-------|--------|-------------|
| Phase 1 | **Done** | Extract service modules |
| Phase 2 | Pending | Request validation decorator to eliminate POST boilerplate |
| Phase 3 | Pending | Flask blueprints to split `__main__.py` |
| Phase 4 | Pending | Pytest test skeleton for services |
