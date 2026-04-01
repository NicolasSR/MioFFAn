## Example: NSLP 2026

To check and evaluate the annotated samples from this example follow these steps:

Replace the sources_config.json file at root with the one in this directory. Then fetch the sources via
```shell
python -m tools.source_samples
```
After that, delete the contents in the ./data directory and copy the ones within any ./examples/NSLP_2026_case/annotation_files/[MODEL_NAME]/[FRAMEWORK_MODEALITY]/ directory (e.g. ./examples/NSLP_2026_case/annotation_files/gemma-3-4b-it/original_characters/). Then proceed by running MioFFAn or the evaluation tool normally.

To use the automation framework explained in the conference paper, with the original prompt files, use branch "nslp2026" from the official Github repository.