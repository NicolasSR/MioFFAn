## Example: NSLP 2026

To check and evaluate the annotated samples from this example follow these steps:

Replace the sources_config.json file at root with the one in this directory. Then fetch the sources via
```shell
python -m tools.source_samples
```
After that, delete the contents in the ./data directory and copy the ones in either annotation_files/explicit_names or annotation_files/original_characters within this folder. Then proceed by running MioFFAn or the evaluation tool normally.