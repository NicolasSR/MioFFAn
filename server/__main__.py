# The Flask application
from flask import Flask
import os
import lxml.html
from docopt import docopt
from pathlib import Path

from lib.version import VERSION
from lib.annotation import MiAnno, McDict
from server.miogatto import MioGattoServer

# meta
PROG_NAME = "server"
HELP = """The server implementation for MioGatto

Usage:
    {p} [options]

Options:
    -d DIR, --data=DIR
        Dir for the gold data [default: ./data]
    -s DIR, --sources=DIR
        Dir for preprocessed HTML [default: ./sources]

    -D, --debug         Run in the debug mode
    -p, --port=NUM      Port number [default: 4100]
    --host=HOST         Host name [default: localhost]

    -h, --help          Show this screen and exit
    -V, --version       Show version
""".format(
    p=PROG_NAME
)


# the web app
app = Flask(__name__)
app.secret_key = os.urandom(12)


def routing_functions(server):
    @app.route('/list_sample_ids', methods=['GET'])
    def list_sample_ids():
        return server.list_sample_ids()
    
    @app.route('/switch_to_sample/<new_id>', methods=['GET'])
    def switch_to_sample(new_id):
        return server.switch_to_sample(new_id)

    @app.route('/', methods=['GET'])
    def index():
        return server.index()

    @app.route('/_assign_concept', methods=['POST'])
    def action_assign_concept():
        return server.assign_concept()

    @app.route('/_remove_concept', methods=['POST'])
    def action_remove_concept():
        return server.remove_concept()

    @app.route('/_new_concept', methods=['POST'])
    def action_new_concept():
        return server.new_concept()

    @app.route('/_update_concept', methods=['POST'])
    def action_update_concept():
        return server.update_concept()

    @app.route('/_add_sog', methods=['POST'])
    def action_add_sog():
        return server.add_sog()

    @app.route('/_delete_sog', methods=['POST'])
    def action_delete_sog():
        return server.delete_sog()

    @app.route('/_change_sog_type', methods=['POST'])
    def action_change_sog_type():
        return server.change_sog_type()

    @app.route('/mcdict.json', methods=['GET'])
    def mcdict_json():
        return server.gen_mcdict_json()
    
    @app.route('/mi_anno.json', methods=['GET'])
    def mi_anno_json():
        return server.gen_mi_anno_json()
    
    @app.route('/_add_eoi', methods=['POST'])
    def action_add_eoi():
        return server.add_eoi()
    
    @app.route('/_remove_eoi', methods=['POST'])
    def action_remove_eoi():
        return server.remove_eoi()

    @app.route('/_add_group', methods=['POST'])
    def action_add_group():
        return server.add_group()
    
    @app.route('/_remove_group', methods=['POST'])
    def action_remove_group():
        return server.remove_group()
    
    @app.route('/_edit_symbolic_code', methods=['POST'])
    def edit_symbolic_code():
        return server.edit_symbolic_code()
    
    @app.route('/hex_to_mc_map.json', methods=['GET'])
    def hex_to_mc_map():
        return server.gen_hex_to_mc_map()

    @app.route('/edit_mcdict', methods=['GET'])
    def edit_mcdict():
        return server.edit_mcdict()
    
    @app.route('/equations_of_interest_selector', methods=['GET'])
    def equations_of_interest_selector():
        return server.equations_of_interest_selector()
    
    @app.route('/symbolic-code-assigner', methods=['GET'])
    def symbolic_code_assigner():
        return server.symbolic_code_assigner()

    @app.route('/group_creator', methods=['GET'])
    def group_creator():
        return server.group_creator()
    
    @app.route('/nav', methods=['GET'])
    def nav():
        return server.nav()
    
    @app.route('/sample_nav', methods=['GET'])
    def sample_nav():
        return server.sample_nav()


def main():
    # parse options
    args = docopt(HELP, version=VERSION)

    # dir and files
    data_dir = Path(args['--data'])
    sources_dir = Path(args['--sources'])

    # Get ALL available IDs from the sources directory
    # Find all .html files and extract the ID (filename without extension)
    available_ids = [p.stem for p in sources_dir.glob('*.html')]
    if not available_ids:
        print(f"Error: No .html files found in {sources_dir}")
        return

    # Use the first ID to initialize the server (original functionality)
    initial_paper_id = available_ids[0]

    print(f"Initializing server with paper ID: {initial_paper_id}")

    anno_json = data_dir / '{}_anno.json'.format(initial_paper_id)
    mcdict_json = data_dir / '{}_mcdict.json'.format(initial_paper_id)
    source_html = sources_dir / '{}.html'.format(initial_paper_id)

    # load the data
    mi_anno = MiAnno(anno_json)
    mcdict = McDict(mcdict_json)
    tree = lxml.html.parse(str(source_html))

    # run the app
    app.debug = args['--debug']

    # Initialize the server, passing directory context
    server = MioGattoServer(
        initial_paper_id, tree, mi_anno, mcdict, app.logger, 
        data_dir=data_dir, 
        sources_dir=sources_dir,
        available_ids=available_ids # Pass the list of all available files
    )
    routing_functions(server)

    app.run(host=args['--host'], port=args['--port'])


if __name__ == '__main__':
    main()