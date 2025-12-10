// the MioGatto client
'use strict';

import {mcdict, mcdict_edit_id} from "./common";
import {submit_update_concept} from "./main_pages_utils"

// --------------------------
// Edit mcdict
// --------------------------

// Sending a form specific to edit_mcdict
function edit_concept(mc_id: string) {
    let concept_dialog = $('#concept-dialog-template').clone();
    concept_dialog.removeAttr('id');

    const concept = mcdict[mc_id];
    let $code_var_name_node = concept_dialog.find('textarea[name="code-var-name"]');
    let $description_node = concept_dialog.find('textarea[name="description"]');
    let $tensor_rank_node = concept_dialog.find('input[name="tensor-rank"]');

    // put the current values
    $code_var_name_node.text(concept.code_var_name);
    $description_node.text(concept.description);
    $tensor_rank_node.attr('value', concept.tensor_rank);
    concept.affixes.forEach(function (value, idx) {
        concept_dialog.find(`select[name="affixes${idx}"]`).find(
            `option[value="${value}"]`).prop('selected', true);
    })

    concept_dialog.dialog({
        modal: true,
        title: 'Edit Concept',
        width: 500,
        buttons: {
            'OK': function () {
                localStorage['scroll_top'] = $(window).scrollTop();
                submit_update_concept(mc_id, concept_dialog)
            },
            'Cancel': function () {
                $(this).dialog('close');
            }
        }
    });
}


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

        const affixes_string = mc_obj.affixes.join(', ')

        let concept_row = `<tr><td>${mc_obj.description}</td><td>${mc_obj.tensor_rank}</td><td>${primitive_symbols_decoded}</td>
            <td>${affixes_string}</td><td>${mc_obj.sog_list.length}</td><td><a class="edit-concept-mcdict" data-mc-id="${mc_id}" href="javascript:void(0);">edit</a></td></tr>`;

        table_content += concept_row
    }

    let content = `<table border="1" cellpadding="5">${table_header}${table_content}</table>`;

    let mcdict_edit_box = $('#edit-mcdict-box');
    mcdict_edit_box.html(content)

    // enable concept dialogs
    $('a.edit-concept-mcdict').on('click', function () {
        const mc_id = $(this).attr('data-mc-id');
        if (mc_id !== undefined) {
            edit_concept(mc_id);
        }
    });

});


$(function () {
    $('button#back-to-index').button();
    $('button#back-to-index').on('click', function () {
        let form = $('#back-to-index-form');
        form.attr('action', '/');
        form.trigger("submit");
    });

});
