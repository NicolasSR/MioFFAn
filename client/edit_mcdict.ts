// the MioFFAn client
'use strict';

import {mcdict, mcdict_edit_id} from "./common";

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

    // let table_header = '<tr><th>Identifier</th><th>Progress</th><th>Description</th><th>Affix</th><th>Arity</th><th>#Occur</th><th>#Sog</th><th>Edit</th></tr>';
    let table_header = '<tr><th>Description</th><th>Tensor rank</th><th>Primitive symbols</th><th>Affix</th><th>#Sog</th><th>Edit</th></tr>';

    let table_content = '';

    for (let mc_id in mcdict) {
        const mc_obj = mcdict[mc_id];

        let primitive_symbols_decoded = "<math>";
        for (let hex of mc_obj.primitive_symbols) {
            primitive_symbols_decoded += `<mi>${hex_decode(hex)}</mi>`;
        }
        primitive_symbols_decoded += "</math>";

        const options_string = mc_obj.properties

        let concept_row = `<tr><td>${mc_obj.description}</td><td>${primitive_symbols_decoded}</td>
            <td>${options_string}</td><td>${mc_obj.sog_list.length}</td><td><a class="edit-concept-mcdict" data-mc-id="${mc_id}" href="javascript:void(0);">edit</a></td></tr>`;

        table_content += concept_row
    }

    let content = `<table border="1" cellpadding="5">${table_header}${table_content}</table>`;

    let mcdict_edit_box = $('#edit-mcdict-box');
    mcdict_edit_box.html(content)

    // enable concept dialogs
    // Removed for now

});


$(function () {
    $('button#back-to-index').button();
    $('button#back-to-index').on('click', function () {
        let form = $('#back-to-index-form');
        form.attr('action', '/');
        form.trigger("submit");
    });

});
