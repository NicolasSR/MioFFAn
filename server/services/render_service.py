from copy import deepcopy
from flask import render_template, Markup
from lxml import etree

from lib.version import VERSION

# Import at module level to avoid circular issues; these are set at module level in mioffan.py
GIT_REVISON = None


class RenderService:
    def __init__(self, tree, mi_anno, mcdict, config, paper_id):
        self.tree = tree
        self.mi_anno = mi_anno
        self.mcdict = mcdict
        self.config = config
        self.paper_id = paper_id

    def _render_page(self, template_name, title=None, **kwargs):
        copied_tree = deepcopy(self.tree)
        root = copied_tree.getroot()

        self._initialize_main_pages(root)

        body = root.xpath('body')[0]
        main_content = etree.tostring(body, method='html', encoding=str)
        style = root.xpath('head/style')[0]
        main_content_style = etree.tostring(style, method='html', encoding=str)

        context = {
            'version': VERSION,
            'git_revision': GIT_REVISON,
            'paper_id': self.paper_id,
            'annotator': self.mi_anno.annotator,
            'main_content': Markup(main_content),
            'main_content_style': Markup(main_content_style),
            'compound_concept_tags': self.config['COMPOUND_CONCEPT_TAGS'],
        }
        context.update(kwargs)

        if title is not None:
            context['title'] = title

        return render_template(template_name, **context)

    def _initialize_main_pages(self, root):
        from lib.util import wrap_custom_group

        for group_id, group_info in self.mi_anno.groups.items():
            if not wrap_custom_group(root, group_id, group_info):
                continue

        self._add_data_math_concept(root)

    def _add_data_math_concept(self, root):
        for comp_tag_id, annotation_obj in self.mcdict.occurences_dict.items():
            mc_id = annotation_obj.mc_id
            if mc_id is not None:
                xpath_expression = "//{}[@id='{}']".format(annotation_obj.tag_name, comp_tag_id)
                matches = root.xpath(xpath_expression)
                if len(matches) != 1:
                    continue

                matches[0].attrib['data-mc-id'] = str(mc_id)

    def index(self):
        return self._render_page(
            'index.html',
            title=f"MioKrattos: {self.paper_id}"
        )

    def equations_of_interest_selector(self):
        return self._render_page('equations_of_interest_selector.html')

    def group_creator(self):
        return self._render_page('group_creator.html')

    def symbolic_code_assigner(self):
        return self._render_page('symbolic_code_assigner.html')

    def edit_mcdict(self):
        return self._render_page('edit_mcdict.html')

    def nav(self):
        return render_template('nav.html')

    def sample_nav(self):
        return render_template('sample_nav.html')
