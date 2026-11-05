# MioFFAn Architecture Reference

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        MioFFAn Architecture                         │
└─────────────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────┐
│          EXTERNAL SOURCES                │
│                                          │
│  ScienceDirect API                       │
│  Springer Nature API (not implemented)   │
│  Local PDFs (Chandra OCR via vLLM)       │
│  Local HTML files                        │
└──────────┬───────────────────────────────┘
           │
                ▼ 
┌───────────────────────────────────────────────────────────────────┐
│                     PREPROCESSING PIPELINE                        │
│                   (tools/source_samples.py)                       │
│                                                                   │
│  ┌──────────────┐    ┌──────────────────┐    ┌────────────────┐   │
│  │  Source      │──▶│  XML/HTML         │──▶│  Preprocess    │   │
│  │  Paper       │    │  Parser+Pruning  │    │  (preprocess)  │   │
│  │  Content     │    │                  │    │  + ID Injection│   │
│  └──────────────┘    └──────────────────┘    └───────┬────────┘   │
│                                                      │            │
│                                                      ▼            │
│                                         ┌────────────────────────┐│
│                                         │ Output Files:          ││
│                                         │ sources/*.html         ││
│                                         │ data/<id>/*_anno.json  ││
│                                         │ data/<id>/*_mcdict.json││
│                                         └────────────────────────┘│
└───────────────────────────────────────────────────────────────────┘
           │
                ▼
┌─────────────────────────────────────────────────────────────────┐
│                     RUNTIME SERVER                              │
│                    (server/__main__.py)                         │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  MioFFAnServer                          │    │
│  │                  (server/mioffan.py)                    │    │
│  │                                                         │    │
│  │  ┌──────────────┐  ┌──────────────┐  ┌───────────────┐  │    │
│  │  │  Routes      │  │  Annotation  │  │  LLM Auto     │  │    │
│  │  │  (35+ end-   │  │  CRUD ops    │  │  (3 tasks)    │  │    │
│  │  │   points)    │  │  for concepts│  │               │  │    │
│  │  └──────────────┘  │  & groups    │  │  - Segment    │  │    │
│  │                    └──────────────┘  │  - Assign     │  │    │
│  │                    ┌──────────────┐  │  - Highlight  │  │    │
│  │                    │  CAS Plugin  │  └───────────────┘  │    │
│  │                    │  Interface   │  ┌───────────────┐  │    │
│  │                    └──────────────┘  │  Checkpoints  │  │    │
│  │                    ┌──────────────┐  │  & Data Mgmt  │  │    │
│  │                    │  Property    │  └───────────────┘  │    │
│  │                    │  Validation  │                     │    │
│  │                    └──────────────┘                     │    │
│  └─────────────────────────────────────────────────────────┘    │
│           │                                       │             │
│           │                                       │             │
└───────────┼──────────────────┬────────────────────┼─────────────┘
            │                  │                    │
            │                  │                    │
            │                  │  ┌───────────────────────────────┐
            │                  │  │           LIB LAYER           │
            │                  │  │                               │
            │                  │  │  annotation.py     MiAnno     │
            │                  │  │                       McDict  │
            │                  │  │  datatypes.py      Core data  │
            │                  │  │                       classes │
            │                  │  │  concept_properties  JSON-    │
            │                  │  │                       Logic   │
            │                  │  │  llm_utilities.py   OpenAI    │
            │                  │  │                       client  │
            │                  │  │  cas_plugins_iface Plugin     │
            │                  │  │                       factory │
            │                  │  │  util.py           Helpers    │
            │                  │  │  ocr_utilities.py  Chandra    │
            │                  │  │                       OCR     │
            │                  │  └───────────────────────────────┘
            │                  │                  │
            │                  │                  │
                  ▼                  │                 ▼
┌───────────────┐              │    ┌───────────────────────────────────┐
│   CLIENT      │              │    │  llm_implementation/              │
│  (TypeScript) │◄─────────────┤    │                                   │
│               │              │    │  llm_implementations.py       3   │
│  index.ts     │              │    │  automation functions             │
│  common.ts    │              │    │                                   │
│  concept_     │              │    │  llm_prompt_files/          Prompt│
│   edition_    │              │    │                          templates│
│   utils.ts    │              │    │                                   │
│  properties_  │              │    │  documentation/             Output│
│   assign.ts   │              │    │                            schemas│
│  symbolic_    │              │    └───────────────────────────────────┘
│   code_       │              │
│   assigner.ts │              │
│  main_pages_  │              │
│   utils.ts    │              │
│  nav.ts,      │              │
│  sample_nav   │              │
│  ast_parser   │              │
│  group_       │              │
│   creator     │              │
│  equations_   │              │
│   of_         │              │
│   interest    │              │
│   selector    │              │
└───────────────┘              │
                               │
                                              ▼
                ┌───────────────────────────────────────────┐
                │  cas_plugins/                             │
                │                                           │
                │  kratos_fe_compiler.py   FE Code Generator│
                │                                           │
                └───────────────────────────────────────────┘
```

## Data Flow

```
Paper Source → source_samples.py → HTML + JSON templates
                                       │
                        ┌──────────────┴──────────────┐
                        │                             │
                                    ▼                                           ▼
                  server/                          tools/
                  Flask API                       evaluate_llm.py
                        │                           (LLM output
                        │                             evaluation)
                                    ▼
                  client/
                  TypeScript UI
                  (browser)
                        │
                                    ▼
                  server/ ←→ lib/ ←→ llm_implementation/
                  routes    core         LLM calls
                        │
                                    ▼
                  cas_plugins/
                  (code generation)
```

## Directory Structure

```
MioFFAn/
├── config.json                  # Concept taxonomy, operators, CAS config
├── credentials.distr.json       # API credentials template
├── requirements.txt             # Python dependencies
│
├── server/                      # Flask backend
│   ├── templates/		 # Main HTML files for the frontend
│   ├── __main__.py              # Entry point, route definitions
│   └── mioffan.py               # MioFFAnServer class (all business logic)
│
├── client/                      # TypeScript frontend (webpack)
│   ├── index.ts                 # Main page: annotation, SoG, concepts
│   ├── common.ts                # Shared state, data loading
│   ├── concept_edition_utils.ts # Concept creation/editing dialogs
│   ├── properties_assignment.ts # Property form rendering + JSON-Logic
│   ├── symbolic_code_assigner.ts# EoI symbolic code editor
│   ├── ast_parser.ts            # Chevrotain-based AST parser
│   ├── main_pages_utils.ts      # DOM manipulation, highlighting
│   ├── nav.ts			 # navigation components for menus
│   ├── sample_nav.ts   	 # Navigation components for samples
│   ├── group_creator.ts         # Custom group creation
│   ├── equations_of_interest_selector.ts  # EoI selection page
│   └── edit_mcdict.ts           # MCDict editing page
│
├── lib/                         # Core library
│   ├── annotation.py            # MiAnno, McDict data handlers
│   ├── datatypes.py             # Dataclass definitions
│   ├── concept_properties.py    # JSON-Logic property validation
│   ├── llm_utilities.py         # OpenAI client, XML matching, schema validation
│   ├── cas_plugins_interface.py # Abstract CAS plugin interface + factory
│   ├── ocr_utilities.py         # Chandra OCR utilities
│   ├── util.py                  # DOM helpers, hex conversion
│   └── logger.py / version.py   # Logging, version info
│
├── llm_implementation/          # LLM automation logic
│   ├── llm_implementations.py   # 3 automation functions
│   ├── llm_prompt_files/        # Prompt templates
│   └── documentation/           # Generated output schemas
│
├── cas_plugins/                 # CAS code generators
│   └── kratos_fe_compiler.py    # Kratos FE template compiler
│
├── tools/                       # CLI utilities
│   ├── source_samples.py        # Fetch + preprocess papers
│   ├── preprocess.py            # HTML preprocessing
│   ├── inject_tag_ids.py        # Assign IDs to MathML elements
│   └── evaluate_llm.py          # CoNLL-based LLM evaluation
│
├── sourcing_info/               # Paper source configuration
│   └── sources_config.json
│
├── sources/                     # Preprocessed HTML papers
│
├── data/                        # Annotation JSON files
│   └── <paper_id>/
│       ├── <id>_anno.json       # Groups, primitive symbols
│       └── <id>_mcdict.json     # Concepts, occurrences, EoIs
│
└── templates/                   # Initial template copies of data files
    └── <paper_id>/
```

## Key Data Types (`lib/datatypes.py`)

| Type                 | Purpose                                                            |
|----------------------|--------------------------------------------------------------------|
| `PrimitiveSymbol`    | Base `<mi>` elements (text + unicode name)                         |
| `MathConcept`        | Semantic concept: var name, category, properties, SoGs, symbols    |
| `Occurence`          | Concept occurrence in document: mc_id, tag_name, properties        |
| `SoG`                | Source of Grounding: start/stop IDs + type                         |
| `Group`              | Custom symbol group: ID ranges + ancestry levels                   |
| `EoI`                | Equation of Interest: symbolic code, AST, variables, substitutions |
| `EnvironmentSetting` | Key-value pairs for CAS environment config                         |

## Core JSON Files

### `_anno.json` (managed by `MiAnno`)
- `primitive_symbols` — map of hex → symbol info
- `groups` — custom compound symbol groups
- `next_available_group_id` — auto-increment counter

### `_mcdict.json` (managed by `McDict`)
- `concepts` — map of mc_id → MathConcept
- `occurences_dict` — map of comp_tag_id → Occurence
- `eoi_dict` — map of equation_id → EoI
- `environment_settings_list` — CAS environment config
- `next_available_mc_id` — auto-increment counter

## Server Routes (selected)

| Route                      | Method | Purpose                        |
|----------------------------|--------|--------------------------------|
| `/`                        | GET    | Main annotation page           |
| `/_assign_concept`         | POST   | Assign concept to compound tag |
| `/_register_concept`       | POST   | Create new concept             |
| `/_add_sog`                | POST   | Add Source of Grounding        |
| `/_add_eoi`                | POST   | Mark equation as EoI           |
| `/_add_group`              | POST   | Create custom symbol group     |
| `/_edit_symbolic_code`     | POST   | Update EoI symbolic code + AST |
| `/_auto_segment_symbols`   | POST   | LLM: auto-segment symbols      |
| `/_auto_assign_concepts`   | POST   | LLM: auto-assign concepts      |
| `/_auto_highlight_sources` | POST   | LLM: auto-highlight SoGs       |
| `/_run_cas`                | POST   | Generate FE code via plugin    |
| `/_create_data_checkpoint` | POST   | Save annotation checkpoint     |
| `/_clear_annotation_data`  | POST   | Reset or restore checkpoint    |
