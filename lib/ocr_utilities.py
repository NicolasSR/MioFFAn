import subprocess
from tempfile import NamedTemporaryFile, TemporaryDirectory
from pathlib import Path
import shutil
import re
import os
import csv

from lxml import etree

"""
To use chandra-ocr model, run a vllm server via:
vllm serve datalab-to/chandra-ocr-2 --served-model-name=chandra
"""

def apply_chandra_ocr_on_pdf(dest_path, orig_path):
    sample_name = Path(orig_path).stem
    with TemporaryDirectory() as tmp_dir:
        tmp_path = Path(tmp_dir)
        subprocess.run(["chandra", orig_path, tmp_path])
        output_html_path = tmp_path / sample_name / (sample_name+".html")
        if output_html_path.exists():
            shutil.copy(output_html_path, dest_path)
    assert not tmp_path.exists()

def detect_errors(std_out):
    """
    Find strings starting by "Error:" within a subprocess output.
    If any, print them  and return True.
    """
    error_count = 0
    for line in std_out.splitlines():
        if line.startswith("Error:"):
            print(line)
            error_count += 1
    return bool(error_count)

def substitute_html_named_entities(tmp_latex_str):
    """
    Convert HTML entities (&lt; &amp; ...) within a string to their LaTeX equivalents
    """
    # Get conversion map from file
    map_html_latex_entities = dict()
    with open("lib/map_html_named_entities_to_latex.txt", "r") as f:
        csv_content = csv.reader(f,delimiter="\t")
        for row in csv_content:
            map_html_latex_entities[row[0]] = row[2]
    # Regex pattern for HTML entities
    regex_named_entities = re.compile("\&(.*?);")
    # Find entities and substitute
    return regex_named_entities.sub(lambda m: map_html_latex_entities[m.group(1)], tmp_latex_str)

def get_mathml_snippets_from_document(mathml_doc, is_inline=False):
    mathml_tree = etree.fromstring(mathml_doc.encode("utf-8"), parser=etree.HTMLParser())
    mathml_div_nodes = mathml_tree.xpath('//div[@class="ltx_para"]')
    mathml_snippets_list = clean_latexml_math(mathml_div_nodes, is_inline=is_inline)
    return mathml_snippets_list

def clean_latexml_math(math_div_nodes_list, is_inline=False):
    mathml_strings_list = []
    for math_div_node in math_div_nodes_list:
        table = math_div_node.xpath('.//table[contains(@class, "ltx_eqn_table")]')
        assert len(table) == 1, "Expected exactly one table with class 'ltx_eqn_table' within each math div"
        table = table[0]
        # Extract the actual <math> element
        math_nodes_list = table.xpath('.//math')
        if is_inline:
            assert len(math_nodes_list) == 1, "Expected exactly one <math> element for inline math"
            math_node = math_nodes_list[0]
            math_node.set('display', 'inline')
            mathml_string = etree.tostring(math_node, encoding='unicode')
        else:
            mathml_string = ""
            for math_node in  math_nodes_list:
                math_node.set('display', 'block')
                new_div = etree.Element("div")
                new_div.set('class', 'formula')
                new_div.append(math_node)
                mathml_string += etree.tostring(new_div, encoding='unicode')
        mathml_strings_list.append(mathml_string)
    return mathml_strings_list

def convert_to_mathml_list(tmp_latex_str, is_inline=False):
    """
    Use LaTeXML as subprocess to convert a LaTeX document (in string format) to HTML(+MathML).
    Then extract MathML snpippets from the final output and return as list of strings.
    """
    # Persistent files are used only to retain log and intermediate files if there is an error
    persistent_log_filename = 'latexml_error_log.txt'
    persistent_latex_filename = 'temprorary_latex_file.tex'
    persistent_latexml_filename = 'temporary_latexml_file.txt'
    # Delete any previous error-related files
    for file_to_delete in [persistent_log_filename, persistent_latex_filename, persistent_latexml_filename]:
        if os.path.exists(file_to_delete):
            os.remove(file_to_delete)

    # We use temporary files for inputs and outputs to LaTeXML subprocesses
    with NamedTemporaryFile("w") as tmp_latex_file:
        tmp_latex_file.write(tmp_latex_str)
        tmp_latex_file.flush()
        with NamedTemporaryFile() as tmp_xml_file, NamedTemporaryFile() as tmp_log_file:
            # Run 'latexml' subprocess (LaTeX to LaTeXML's own format)
            process_out = subprocess.run(['latexml', f'--dest={tmp_xml_file.name}', f'--log={tmp_log_file.name}', tmp_latex_file.name], capture_output=True)
            tmp_xml_file.flush()
            tmp_log_file.flush()
            # print(process_out.stderr.decode("utf-8"))
            # Error detection. If error, raise exception and copy error files to persistent files
            if detect_errors(process_out.stderr.decode("utf-8")):
                shutil.copy2(tmp_log_file.name,persistent_log_filename)
                shutil.copy2(tmp_latex_file.name,persistent_latex_filename)
                raise Exception(f"Errors while converting LaTeX to LaTeXML. Check log at {persistent_log_filename} and LaTeX file at {persistent_latex_filename}")
            with NamedTemporaryFile() as tmp_html_file:
                # Run 'latexmlpost' subprocess (LaTeXML's own format to MathML)
                process_out = subprocess.run(['latexmlpost', f'--dest={tmp_html_file.name}', f'--log={tmp_log_file.name}', '--format=html5', '--nonumbersections', tmp_xml_file.name], capture_output=True)
                tmp_html_file.flush()
                tmp_log_file.flush()
                # print(process_out.stderr.decode("utf-8"))
                # Error detection. If error, raise exception and copy error files to persistent files
                if detect_errors(process_out.stderr.decode("utf-8")):
                    shutil.copy2(tmp_log_file.name,persistent_log_filename)
                    shutil.copy2(tmp_xml_file.name,persistent_latexml_filename)
                    raise Exception(f"Errors while converting LaTeXML MathML. Check log at {persistent_log_filename} and LaTeX file at {persistent_latexml_filename}")
                # Get final output content
                with open(tmp_html_file.name, "r") as f:
                    mathml_raw = f.read()
                # shutil.copy2(tmp_html_file.name,'equations_html_out.html')
            assert not os.path.exists(tmp_html_file.name)
        assert not os.path.exists(tmp_xml_file.name)
        assert not os.path.exists(tmp_log_file.name)
    assert not os.path.exists(tmp_latex_file.name)

    # Extract MathML snippets from final output and return as list of strings
    mathml_list = get_mathml_snippets_from_document(mathml_raw, is_inline=is_inline)
    return mathml_list

def generate_temporary_latex_doc(latex_expressions):
    """
    In order to convert several LaTeX mathematical expressions at once, we write them all within a LaTeX document (string)
    """
    # Define LaTeX document structure

    latex_head = """\\documentclass[12pt]{article}
\\usepackage{amsmath}
\\newcommand{\\lt}{<}
\\newcommand{\\gt}{>}
\\begin{document}

\\begin{equation*}"""
    latex_tail = """\\end{equation*}
\\end{document}"""
    # Insert LaTeX expressions, with display math delimiters
    out_str = latex_head + "\\end{equation*}\n\n\\begin{equation*}".join(latex_expressions) + latex_tail

    # Convert HTML entities (&lt; &amp; ...) to their LaTeX equivalents
    out_str = substitute_html_named_entities(out_str)

    # with open('latex_doc.tex','w') as f:
    #     f.write(out_str)
    return out_str

def subs_matches_with_list_elements(regex_pattern, full_string, replacements_list):
    """
    Substitute each occurrence of a regex pattern by the next string in a given list
    """
    class LambdaCounter():
        def __init__(self):
            self.count = 0
        def __call__(self, *args, **kwargs):
            self.count += 1
            return self.count-1
        
    lambda_counter = LambdaCounter()
    out_string =  regex_pattern.sub(lambda m: replacements_list[lambda_counter()], full_string)
    assert lambda_counter.count == len(replacements_list)
    return out_string

def add_space_to_aligned_envs(expressions_list):
    processed_expressions_list = []
    for expression in expressions_list:
        if expression.strip().startswith("\\begin{aligned}") and expression.strip().endswith("\\end{aligned}"):
            processed_expressions_list.append(expression+"\ ")
        else:
            processed_expressions_list.append(expression)
    return processed_expressions_list

def substitute_expressions(html_string):
    """
    Given HTML with LaTeX mathematical expressions within <math> tags, get these expressions, convert them
    to MathML via latexml and substitute the MathML back into the original HTML string.
    """
    # Regex expressions for inline and display math within the input HTML
    regex_inline = re.compile(r"<math>(.*?)<\/math>", flags=re.MULTILINE | re.UNICODE)
    regex_display = re.compile(r'<math\s+display="block">(.*?)<\/math>', flags=re.MULTILINE | re.UNICODE)
    # Get lists of LaTeX expressions
    inline_matches = regex_inline.findall(html_string)
    display_matches = regex_display.findall(html_string)
    # If any expression contains only an aligned environment, we add a single space at the end to make LaTeXML converti it to a single math node
    display_matches = add_space_to_aligned_envs(display_matches)
    # Join expressions into temporary LaTeX documents
    tmp_latex_str_inline = generate_temporary_latex_doc(inline_matches)
    tmp_latex_str_display = generate_temporary_latex_doc(display_matches)
    # Apply latexml onto temporary documents and return list of MathML equivalents
    mathml_list_inline = convert_to_mathml_list(tmp_latex_str_inline, is_inline=True)
    mathml_list_display = convert_to_mathml_list(tmp_latex_str_display, is_inline=False)
    # Insert MathML back into HTML string
    html_string = subs_matches_with_list_elements(regex_inline, html_string, mathml_list_inline)
    html_string = subs_matches_with_list_elements(regex_display, html_string, mathml_list_display)
    return html_string

def preprocess_equation_tags(html_string):
    """
    In the Chandra OCR output, math equation tags are defined as "\quad (n)" or "\tag{(n)}" (where n is the equation number) inside the <math> tag content itself.
    This function moves this tag outside the <math> tag and into a separate div.
    """
    # Regex patterns to find the equation tag within the math content
    regex_equation_tag = re.compile(r"\\tag{(.*)}\s*<\/math>", flags=re.MULTILINE | re.UNICODE)
    regex_equation_quad = re.compile(r"\\quad\s*\((.*)\)\s*<\/math>", flags=re.MULTILINE | re.UNICODE)
    
    def replace_equation_number(match):
        equation_number = match.group(1)
        return f'</math>\n<div class="formula-label">({equation_number})</div>'

    # Substitute the equation tags in the HTML string
    html_string = regex_equation_tag.sub(replace_equation_number, html_string)
    html_string = regex_equation_quad.sub(replace_equation_number, html_string)

    return html_string