// the MioFFAn client
'use strict';

import {mcdict, dataLoadingPromise, mcdict_edit_id} from "./common";
import {render_concept_dialog} from "./concept_edition_utils";

// --------------------------
// Edit mcdict
// --------------------------


// convert hex string to UTF-8 string
function hex_decode(str: string) {
    let bytes: number[] = Array();

    // Convert hex to int.
    for (let i = 0; i < str.length; i += 2) {
        bytes.push(parseInt(str.slice(i, i + 2), 16));
    }

    //console.log(new Uint8Array(bytes));

    let decoded: string = (new TextDecoder()).decode(new Uint8Array(bytes));
    return decoded;
}

// Show identifiers in edit-mcdict-box.
$(function () {
    dataLoadingPromise.then(() => {
        // let table_header = '<tr><th>Identifier</th><th>Progress</th><th>Description</th><th>Affix</th><th>Arity</th><th>#Occur</th><th>#Sog</th><th>Edit</th></tr>';
        let table_header = '<tr><th>Variable name</th><th>Description</th><th>Concept category</th><th>Properties</th><th>Primitive symbols</th><th>#Sog</th><th>Edit</th></tr>';

        let table_content = '';

        for (let mc_id in mcdict) {
            const mc_obj = mcdict[mc_id];

            let primitive_symbols_decoded = "<math>";
            for (let hex of mc_obj.primitive_symbols) {
                primitive_symbols_decoded += `<mi>${hex_decode(hex)}</mi>`;
            }
            primitive_symbols_decoded += "</math>";

            const properties = mc_obj.properties
            const properties_string = JSON.stringify(properties, null, 2);

            let concept_row = `<tr><td>${mc_obj.code_var_name}</td><td>${mc_obj.description}</td><td>${mc_obj.concept_category}</td><td>${properties_string}</td>
                <td>${primitive_symbols_decoded}</td><td>${mc_obj.sog_list.length}</td><td><a class="edit-concept-mcdict" data-mc-id="${mc_id}" href="javascript:void(0);">edit</a></td></tr>`;

            table_content += concept_row
        }

        let content = `<table border="1" cellpadding="5">${table_header}${table_content}</table>`;

        let mcdict_edit_box = $('#edit-mcdict-box');
        mcdict_edit_box.html(content)

        // enable concept dialogs
        // Removed for now
    });
});


$(function () {
    dataLoadingPromise.then(() => {
        $('button#back-to-index').button();
        $('button#back-to-index').on('click', function () {
            let form = $('#back-to-index-form');
            form.attr('action', '/');
            form.trigger("submit");
        });
        $('button#add-new-concept').button();
        $('button#add-new-concept').on('click', function () {
            let primitive_symbols: string[] = [];
            let $dialog = $('#concept-dialog-template');
            render_concept_dialog($dialog, primitive_symbols, (assigned_mc_id) => {});
        });
        
        $('#edit-mcdict-box').on('mouseup', function (event) {

            const target = event.target as HTMLElement;

            // Find the closest anchor tag with your specific class
            const edit_link = target.closest('.edit-concept-mcdict') as HTMLAnchorElement | null;

            if (edit_link) {
                event.preventDefault(); // Prevent default link behavior
                
                // Retrieve the data attribute. 
                // Note: HTML "data-mc-id" automatically maps to camelCase "mcId" in JS/TS dataset!
                const mc_id = edit_link.dataset.mcId; 
                
                if (mc_id) {
                    let primitive_symbols = mcdict[mc_id].primitive_symbols;
                    let $dialog = $('#concept-dialog-template');
                    render_concept_dialog($dialog, primitive_symbols, (assigned_mc_id) => {}, mc_id);
                }
            }
        });

    });
});

