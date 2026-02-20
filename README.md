# MioFFAn: An annotation software for Formula Formalization with partial automation.

MioFFAn (Math identifier-oriented Formula Formalization Annotator) is a tool for
the annotation of symbolic code representing specific mathematical expressions
within STEM documents. The framework makes the process intuitive and fine-grained,
annotating first themeaning and properties of the symbols within the formula,
grounding them to the rest of the document's content and finally writing the symbolic
code according to the annotated variables and a customizable grammar of operators. We
refer to this complete task as Formula Formalization.

Customization capabilities in terms of the taxonomy of concepts to annotate, their
properties and the operators to use make this software applicable to field-specific,
real-world research documents.

The framework supports automation of certain tasks via an interface to local LLM server.
Provisional automation approaches are available, although they are a work in progress.

MioFFAn builds off from the MioGatto annotation tool (github.com/wtsnjp/MioGatto)

## System requirements

* Python3 (3.9 or later)
* A Web Browser with MathML support (for the GUI annotation system)
    * [Firefox](https://www.mozilla.org/firefox/) is recommended

## Installation

The dependencies will be all installed with one shot:

```shell
python -m pip install -r requirements.txt
```

In case you don't want to install the dependencies into your system, please
consider using [venv](https://docs.python.org/3/library/venv.html).

## Acknowledgements

This project has been supported by .... (Anonymized)

## License

This software is licensed under [the MIT license](./LICENSE).

### Third-party software
* [MioGatto](https://github.com/wtsnjp/MioGatto): Copyright 2021 Takuto Asakura (wtsnjp). Licensed under [the MIT license](https://github.com/wtsnjp/MioGatto/blob/main/LICENSE).
* [jQuery](https://jquery.org/): Copyright JS Foundation and other contributors. Licensed under [the MIT license](https://jquery.org/license).
* [jQuery UI](https://jqueryui.com/): Copyright jQuery Foundation and other contributors. Licensed under [the MIT license](https://github.com/jquery/jquery-ui/blob/HEAD/LICENSE.txt).

