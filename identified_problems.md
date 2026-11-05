# MioFFAn — Identified Architectural Problems

## 1. Monolithic Server (God Class)

`server/mioffan.py` is a single `MioFFAnServer` class (~1,303 lines, ~45 methods) containing all business logic: page rendering, annotation CRUD, LLM automation, CAS plugins, property validation, checkpoints, and data management. Every POST endpoint repeats the same validation boilerplate (~30% duplicated code). Zero modularity, zero testability, high cognitive load.

**Refactoring plan:** See `refactor_server_architecture.md`.

## 2. Frameworkless TypeScript Client with Scattered DOM Manipulation

The frontend is a dozen TypeScript files (`index.ts`, `main_pages_utils.ts`, `concept_edition_utils.ts`, `properties_assignment.ts`, etc.) doing direct DOM manipulation without any frontend framework. There's no structured state management, no component architecture, and no routing. As features are added, this becomes increasingly tangled and error-prone.

## 3. No Testing Infrastructure

The README mentions an evaluation tool for LLM outputs (`tools/evaluate_llm.py`), but there are no unit or integration tests for the core application logic. Combined with problem #1 (everything trapped in one class), this makes the codebase hard to verify and refactor safely.
