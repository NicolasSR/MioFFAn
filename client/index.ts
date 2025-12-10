// the MioGatto client
'use strict';

import { post } from "jquery";
import {
    COMPOUND_CONCEPT_TAGS, dataLoadingPromise, Source, dfs_comp_tags, mcdict, mcdict_edit_id,
    escape_selector, get_mc_id_from_query, get_concept_cand, get_primitive_hex_list,
    fetch_mcdict_json_data
} from "./common";
import {
    highlight_sog_nodes, remove_highlight, sog_to_sog_nodes_for_addition, get_selection,
    reorder_anchor_and_focus_ids, handle_selection_ends, give_eoi_borders, submit_update_concept
} from "./main_pages_utils"

// --------------------------
// Get list of tags used as mathematical identifiers ffrom configuration json
// --------------------------

const compound_tags_selector = COMPOUND_CONCEPT_TAGS.join(', ');

// --------------------------
// Options
// --------------------------

let miogatto_options: { [name: string]: boolean } = {
    limited_highlight: false,
    show_definition: false,
}

$(function () {
    dataLoadingPromise.then(() => {

        // Mark borders of EoI
        give_eoi_borders()

        let input_opt_hl = $('#option-limited-highlight');
        let input_opt_def = $('#option-show-definition');

        // first time check
        if (localStorage['option-limited-highlight'] == 'true') {
            input_opt_hl.prop('checked', true);
            miogatto_options.limited_highlight = true
        } else {
            miogatto_options.limited_highlight = false
        }

        if (localStorage['option-show-definition'] == 'true') {
            input_opt_def.prop('checked', true);
            miogatto_options.show_definition = true
        } else {
            miogatto_options.show_definition = false
        }

        give_sog_highlight();

        // toggle
        input_opt_hl.on('click', function () {
            if ($(this).prop('checked')) {
                localStorage['option-limited-highlight'] = 'true';
                miogatto_options.limited_highlight = true
            } else {
                localStorage['option-limited-highlight'] = 'false';
                miogatto_options.limited_highlight = false
            }
            give_sog_highlight();
        });

        input_opt_def.on('click', function () {
            if ($(this).prop('checked')) {
                localStorage['option-show-definition'] = 'true';
                miogatto_options.show_definition = true
            } else {
                localStorage['option-show-definition'] = 'false';
                miogatto_options.show_definition = false
            }
            give_sog_highlight();
        });
    });
});

// --------------------------
// Sidebar
// --------------------------

$(function () {
    dataLoadingPromise.then(() => {
        $('.sidebar-tab input.tab-title').each(function () {
            let tab_name = this.id;
            if (localStorage[tab_name] == 'true') {
                $(`#${tab_name}`).prop('checked', true);
            }

            $(`#${tab_name}`).on('change', function () {
                if ($(this).prop('checked')) {
                    localStorage[tab_name] = true;
                } else {
                    localStorage[tab_name] = false;
                }
            });
        });
    });
});


// --------------------------
// text color
// --------------------------

function give_color($target: JQuery) {
    console.log('give_color target', $target)
    const mc_id = get_mc_id_from_query($target)
    console.log('give_color mc_id', mc_id)
    if (mc_id != undefined) {
        const concept = mcdict[mc_id]
        console.log('color', concept.color)
        if (concept != undefined && concept.color != undefined) {
            $target.css('color', concept.color);
        }
    }
}

$(function () {
    dataLoadingPromise.then(() => {
        $(compound_tags_selector).each(function () {
            give_color($(this));
        });
    });
})

// --------------------------
// SoG highlight
// --------------------------


function apply_highlight(sog_nodes: JQuery, sog: Source, mc_id: string) {
    remove_highlight(sog_nodes);

    let concept = mcdict[mc_id];
    highlight_sog_nodes(concept, sog_nodes, sog, miogatto_options.show_definition)

    // embed SoG information for removing
    sog_nodes.attr({
        'data-sog-mc-id': mc_id,
        'data-sog-type': sog.type,
        'data-sog-start': sog.start_id,
        'data-sog-stop': sog.stop_id
    });
}

function give_sog_highlight() {
    for (let mc_id in mcdict)  {
        for (let s of mcdict[mc_id].sog_list) {
            let sog_nodes = sog_to_sog_nodes_for_addition(s)

            const sog_concept_id = mc_id;
            if (miogatto_options.limited_highlight) {
                // Option for limited highlighting:
                // Only highlight sogs related to currently selected sog
                if (sessionStorage['comp_tag_id'] != undefined) {
                    const session_mc_id = get_mc_id_from_query($('#' + escape_selector(sessionStorage['comp_tag_id'])))
                    if (session_mc_id == sog_concept_id) {
                        apply_highlight(sog_nodes, s, mc_id);
                    } else {
                        remove_highlight(sog_nodes);
                    }
                } else {
                    console.log("No mathematical element selected yet.")
                }
            } else {
                apply_highlight(sog_nodes, s, mc_id)
            }
        }
    }
}

// --------------------------
// tooltip
// --------------------------

$(function () {
    dataLoadingPromise.then(() => {
        $(document).tooltip({
            show: false,
            hide: false,
            items: '[data-mc-id]',
            content: function () {
                let concept = mcdict[get_mc_id_from_query($(this))!];
                if (concept != undefined) {
                    let args_info = 'NONE';
                    if (concept.affixes.length > 0) {
                        args_info = concept.affixes.join(', ');
                    }
                    return `${concept.description} <span style="color: #808080;">[${args_info}] (rank: ${concept.tensor_rank})</span>`;
                } else {
                    return '(No description)';
                }
            },
            open: function (_event, _ui) {
                $('mi').each(function () {
                    give_color($(this));
                })
            }
        });
    });
});

// --------------------------
// Comp Tag selection
// --------------------------

function select_comp_tag($comp_tag: JQuery) {
    console.log('Selected: ', $comp_tag)
    // if already selected, remove it
    let old_comp_tag_id = sessionStorage.getItem('comp_tag_id');
    if (old_comp_tag_id != undefined) {
        $('#' + escape_selector(old_comp_tag_id)).css({'border': '', 'padding': ''});
    }

    // store id of the currently selected mi
    sessionStorage['comp_tag_id'] = $comp_tag.attr('id');

    // show the annotation box
    show_anno_box($comp_tag);

    // also update SoG highlight
    if (localStorage['option-limited-highlight'] == 'true') {
        miogatto_options.limited_highlight = true;
    }
    give_sog_highlight();
}

// --------------------------
// Annotation box
// --------------------------

// show the box for annotation in the sidebar 
function draw_anno_box(comp_tag_id: string, mc_candidates: string[]) {

    let radios = '';
    for (let mc_radio_num in mc_candidates) {
        const mc_candidate_id = mc_candidates[mc_radio_num];
        const mc_candidate = mcdict[mc_candidate_id]
        
        // If mc was already assigned to the comp_tag, then check the corresponding radio button
        const check = (mc_candidate_id == get_mc_id_from_query($('#' + escape_selector(comp_tag_id)))) ? 'checked' : ''

        let radio_input = `<input type="radio" name="mc_id" id="c${mc_radio_num}" value="${mc_candidate_id}" ${check} />`;
        
        let args_info = 'NONE';
        if (mc_candidate.affixes.length > 0) {
            args_info = mc_candidate.affixes.join(', ');
        }

        let item = `${radio_input}<span class="keep"><label for="c${mc_radio_num}">
${mc_candidate.description} <span style="color: #808080;">[${args_info}] (tensor_rank: ${mc_candidate.tensor_rank})</span>
(<a class="edit-concept" data-mc-id="${mc_candidate_id}" href="javascript:void(0);">edit</a>)
</label></span>`
        radios += item;
    }

    let candidates_list = `<div class="keep" id="mc-radio-list-${comp_tag_id}">${radios}</div>`;
    let buttons = '<p><button id="assign-concept">Assign</button> <button id="remove-concept" type="button">Remove</button> <button id="new-concept" type="button">New</button></p>'
    let form_elements = candidates_list + buttons

    // show the box
    let id_span = `ID: <span style="font-family: monospace;">${comp_tag_id}</span>`
    let anno_box_content = `<p>${id_span}<hr color="#FFF">${form_elements}</p>`

    // write the content
    let anno_box = $('#anno-box')
    anno_box.html(anno_box_content);
    
    // assign chosen concept
    $('button#assign-concept').button();
    $('button#assign-concept').on('click', function () {
        const checked_item = anno_box.find('input[name="mc_id"]:checked');
        if (checked_item.length == 1) {
            const mc_id = checked_item.attr('value')!
            submit_assign_concept(comp_tag_id, mc_id)
        } else {
            alert('Please select a concept.');
            return false;
        }
    });

    // remove assignment
    $('button#remove-concept').button();
    $('button#remove-concept').on('click', function () {
        fetch('/_remove_concept', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                mcdict_edit_id: mcdict_edit_id,
                comp_tag_id: comp_tag_id
            }),
        }).then(async(response) => {
            const data = await response.json()
            if (response.ok) {
                window.location.reload();
            } else {
                if (data.action === 'reload') {
                    alert(data.message);
                    window.location.reload(); // Manually trigger the reload here
                }
                console.error("Error:", data.message);
                alert("Error: " + data.message);
                return;
            }
        }).catch(error => {
            console.error('Error removing concept:', error);
        });
    });

    // enable concept dialogs
    new_concept_button(comp_tag_id);
    $('a.edit-concept').on('click', function () {
        let mc_id = $(this).attr('data-mc-id');
        if (mc_id != undefined) {
            edit_concept(mc_id);
        }
    });

    // give colors at the same time
    $(compound_tags_selector).each(function () {
        give_color($(this));
    });
}

function show_anno_box($comp_tag_node: JQuery) {
    // highlight the selected element
    $comp_tag_node.css({'border': 'dotted 2px #000000', 'padding': '10px'});

    // Get candidate concepts
    let concept_cand = get_concept_cand($comp_tag_node);
    console.log('concept_cand', concept_cand)

    // draw the annotation box
    let comp_tag_id = $comp_tag_node.attr('id');
    if (concept_cand != undefined && comp_tag_id != undefined) {
        if (concept_cand.length > 0) {
            draw_anno_box(comp_tag_id, concept_cand);
        } else {
            let id_span = `ID: <span style="font-family: monospace;">${comp_tag_id}</span>`
            let no_concept = '<p>No concept is available.</p>'
            let button = '<p><button id="new-concept" type="button">New</button></p>'
            let msg = `<p>${id_span}<hr color="#FFF">${no_concept}${button}</p>`
            $('#anno-box').html(msg);

            // enable the button
            new_concept_button(comp_tag_id);
        }
    }
}

function submit_assign_concept(comp_tag_id: string, mc_id: string) {
    const tag_name: string = $('#' + escape_selector(comp_tag_id)).prop("tagName").toLowerCase()

    fetch('/_assign_concept', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            mcdict_edit_id: mcdict_edit_id,
            comp_tag_id: comp_tag_id,
            mc_id: mc_id,
            tag_name: tag_name
        }),
    }).then(async(response) => {
        const data = await response.json();
        if (response.ok) {
            // Just reload the page
            window.location.reload();
        } else {
            if (data.action === 'reload') {
                alert(data.message);
                window.location.reload(); // Manually trigger the reload here
            }
            console.error("Error:", data.message);
            alert("Error: " + data.message);
            return;
        }
    }).catch(error => {
        console.error('Error assigning concept:', error);
    });
}

function submit_new_concept(comp_tag_id: string, concept_dialog: JQuery<HTMLElement>) {
    const code_var_name = concept_dialog.find('textarea[name="code-var-name"]').val()
    const description = concept_dialog.find('textarea[name="description"]').val()
    const tensor_rank = concept_dialog.find('input[name="tensor-rank"]').val()
    let affixes: string[] = [];
    for (let idx = 0; idx < 10; idx++) {  // This is hardcoded for now. Should be changed.
        const affix_value = concept_dialog.find(`select[name="affixes${idx}"]`).find(
        `option:selected`).attr('value');
        if (affix_value !== undefined && affix_value !== '') {
            affixes.push(affix_value)
        }
    }
    const primitive_symbols = get_primitive_hex_list($('#' + escape_selector(comp_tag_id)))

    fetch('/_new_concept', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            mcdict_edit_id: mcdict_edit_id,
            code_var_name: code_var_name,
            description: description,
            tensor_rank: tensor_rank,
            affixes: affixes,
            primitive_symbols: primitive_symbols
        }),
    }).then(async (response) => {
        const data = await response.json();
        if (response.ok) {
            // If concept is correctly created, assign it to the current comp_tag_id
            // First refresh MCDICT data to have the version with the new concept
            await fetch_mcdict_json_data();
            submit_assign_concept(comp_tag_id, data.mc_id);
        } else {
            console.error("Error:", data.message);
            alert("Error: " + data.message);
            window.location.reload(); // Manually trigger the reload here
        }
    }).catch(error => {
        console.error('Error creating concept:', error);
    });
}

function new_concept_button(comp_tag_id: string) {
    console.log("NEW CONCEPT BUTTON entered")
    $('button#new-concept').button();
    $('button#new-concept').on('click', function () {
        let concept_dialog = $('#concept-dialog-template').clone();
        concept_dialog.attr('id', 'concept-dialog');
        concept_dialog.removeClass('concept-dialog');

        concept_dialog.dialog({
            modal: true,
            title: 'New Concept',
            width: 500,
            buttons: {
                'OK': function() {
                    localStorage['scroll_top'] = $(window).scrollTop();
                    submit_new_concept(comp_tag_id, concept_dialog);
                },
                'Cancel': function() {
                    $(this).dialog('close');
                }
            },
            close: function() {
                $(this).remove();
            }
        });
    });
}

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

$(function () {
    dataLoadingPromise.then(() => {
        $(compound_tags_selector).on('click', function () {
            select_comp_tag($(this));
        });
    });
});

// --------------------------
// SoG Registration
// --------------------------

function submit_change_sog_type(sog_mc_id: string, sog_start_id: string, sog_stop_id: string, sog_type: string){
    fetch('/_change_sog_type', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            mcdict_edit_id: mcdict_edit_id,
            mc_id: sog_mc_id,
            start_id: sog_start_id,
            stop_id: sog_stop_id,
            sog_type: sog_type
        }),
    }).then(async (response) => {
        const data = await response.json();
        if (response.ok) {
            // Just reload the page
            window.location.reload();
        } else {
            if (data.action === 'reload') {
                alert(data.message);
                window.location.reload(); // Manually trigger the reload here
            }
            console.error("Error:", data.message);
            alert("Error: " + data.message);
            return;
        }
    }).catch(error => {
        console.error('Error updating type of Source of Grounding:', error);
    });
}

$(function () {
    dataLoadingPromise.then(() => {
        let page_x: number;
        let page_y: number;

        $(document).on('mouseup', function (e) {
            page_x = e.pageX;
            page_y = e.pageY;

            $('.sog-menu').css('display', 'none');
            let [anchor_id, focus_id, parent] = get_selection();

            if (parent == undefined)
                return;

            // use jquery-ui
            $('.sog-menu input[type=submit]').button();

            // ----- Action SoG add -----
            let comp_tag_id = sessionStorage['comp_tag_id'];

            // show it only if a comp_tag with concept annotation selected
            if (comp_tag_id != undefined) {
                const mc_id = get_mc_id_from_query($('#' + escape_selector(comp_tag_id)))
                if (mc_id != undefined) {
                    $('.sog-menu').css({
                        'left': page_x,
                        'top': page_y - 20
                    }).fadeIn(200).css('display', 'flex');
                }
            }

            // show the current target
            let id_span = `<span style="font-family: monospace;">${comp_tag_id}</span>`;
            let add_menu_info = `<p>Selected tag: ${id_span}</p>`;
            $('.sog-add-menu-info').html(add_menu_info);

            // the add function
            $('.sog-menu .sog-add').off('click');
            $('.sog-menu .sog-add').on('click',
                function () {
                    $('.sog-menu').css('display', 'none');

                    if (anchor_id == undefined || focus_id == undefined) {
                        console.error("Anchor or Focus node ids is undefined")
                    } else {
                        let [anchor_local_id, focus_local_id] = handle_selection_ends(anchor_id, focus_id)
                        let [start_local_id, stop_local_id] = reorder_anchor_and_focus_ids(anchor_local_id, focus_local_id)

                        const mc_id = get_mc_id_from_query($('#' + escape_selector(comp_tag_id)))

                        localStorage['scroll_top'] = $(window).scrollTop();

                        fetch('/_add_sog', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({
                                mcdict_edit_id: mcdict_edit_id,
                                mc_id: mc_id,
                                start_id: start_local_id,
                                stop_id: stop_local_id
                            }),
                        }).then(async (response) => {
                            const data = await response.json();
                            if (response.ok) {
                                // Just reload the page
                                window.location.reload();
                            } else {
                                if (data.action === 'reload') {
                                    alert(data.message);
                                    window.location.reload(); // Manually trigger the reload here
                                }
                                console.error("Error:", data.message);
                                alert("Error: " + data.message);
                                return;
                            }
                        }).catch(error => {
                            console.error('Error adding Source of Grounding:', error);
                        });
                    }
                });

            // ----- SoG menu -----

            let sog_mc_id = parent.getAttribute('data-sog-mc-id');
            let sog_type_int = Number(parent.getAttribute('data-sog-type'));
            let sog_start_id = parent.getAttribute('data-sog-start');
            let sog_stop_id = parent.getAttribute('data-sog-stop');

            // Do not show sog-mod-menu when the sog is not highlighted.
            let is_sog_highlighted = true;
            if (miogatto_options.limited_highlight && comp_tag_id != undefined && sog_mc_id != undefined) {
                let cur_mc_id = get_mc_id_from_query($('#' + escape_selector(comp_tag_id)));
                if (!(cur_mc_id == sog_mc_id )) {
                    is_sog_highlighted = false;
                }
            }
            // show it only if SoG is selected and highlighted.
            if (parent?.getAttribute('data-sog-mc-id') != undefined && is_sog_highlighted) {
                $('.sog-mod-menu').css('display', 'inherit');
            } else {
                $('.sog-mod-menu').css('display', 'none');
            }

            let sog_type = 'unknown';
            if (sog_type_int == 0) {
                sog_type = 'declaration';
            } else if (sog_type_int == 1) {
                sog_type = 'definition';
            } else if (sog_type_int == 2) {
                sog_type = 'others';
            }

            let mod_menu_info = `<p>SoG for ${id_span}<br/>Type: ${sog_type}</p>`;
            $('.sog-mod-menu-info').html(mod_menu_info);

            // ----- Action SoG change type -----
            $('.sog-menu .sog-type').off('click');
            $('.sog-menu .sog-type').on('click',
                function () {
                    $('.sog-menu').css('display', 'none');

                    // make sure parent exists
                    // Note: the button is shown only if it exists
                    if (parent == undefined)
                        return;

                    let sog_type_dialog = $('#sog-type-dialog-template').clone();
                    sog_type_dialog.attr('id', 'sog-type-dialog');
                    sog_type_dialog.removeClass('sog-type-dialog');

                    // Mark the initial SoG type in the form
                    sog_type_dialog.find(`input[value="${sog_type_int}"]`).prop('checked', true);

                    sog_type_dialog.dialog({
                        modal: true,
                        title: 'Change SoG Type',
                        width: 200,
                        buttons: {
                            'OK': function () {
                                const checked_item = sog_type_dialog.find('input[name="sog_type"]:checked');
                                if (checked_item.length == 1) {
                                    localStorage['scroll_top'] = $(window).scrollTop();
                                    const new_sog_type = checked_item.attr('value')!
                                    submit_change_sog_type(sog_mc_id!, sog_start_id!, sog_stop_id!, new_sog_type)
                                } else {
                                    alert('Please select a sog type.');
                                    return false;
                                }    
                            },
                            'Cancel': function () {
                                $(this).dialog('close');
                            }
                        },
                        close: function () {
                            $(this).remove();
                        }
                    });
                });

            // ----- Action SoG delete -----
            $('.sog-menu .sog-del').off('click');
            $('.sog-menu .sog-del').on('click',
                function () {
                    $('.sog-menu').css('display', 'none');

                    // make sure parent exists
                    // Note: the button is shown only if it exists
                    if (parent == undefined)
                        return;

                    localStorage['scroll_top'] = $(window).scrollTop();

                    fetch('/_delete_sog', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            mcdict_edit_id: mcdict_edit_id,
                            mc_id: parent.getAttribute('data-sog-mc-id'),
                            start_id: parent.getAttribute('data-sog-start'),
                            stop_id: parent.getAttribute('data-sog-stop')
                        }),
                    }).then(async (response) => {
                        const data = await response.json();
                        if (response.ok) {
                            // Just reload the page
                            window.location.reload();
                        } else {
                            if (data.action === 'reload') {
                                alert(data.message);
                                window.location.reload(); // Manually trigger the reload here
                            }
                            console.error("Error:", data.message);
                            alert("Error: " + data.message);
                            return;
                        }
                    }).catch(error => {
                        console.error('Error deleting Source of Grounding:', error);
                    });
                });
        });
    });
});

// --------------------------
// background color
// --------------------------

// for the identifiers that have not been annotated
function give_gray_background(target: JQuery) {
    if (target.data('mc-id') == undefined)
        target.css('background-color', '#D3D3D3');
}

$(function () {
    dataLoadingPromise.then(() => {
        $(compound_tags_selector).each(function () {
            give_gray_background($(this));
        });
    });
})

// --------------------------
// Keybord shortcuts
// --------------------------

function select_concept(num: number) {
    let elem = $(`#c${num - 1}`);
    if (elem[0]) {
        $('input[name="mc_id"]').prop('checked', false);
        $(`#c${num - 1}`).prop('checked', true);
    }
}

for (let i = 1; i < 10; i++) {
    $(document).on('keydown', function (event) {
        if (!$('#concept-dialog')[0]) {
            if (event.key == i.toString(10)) {
                select_concept(i);
            }
        }
    });
}

$(document).on('keydown', function (event) {
    if (event.key == 'Enter') {
        if (!$('#concept-dialog')[0]) {
            $('#assign-concept').trigger('click');
        }
    }
});

$(document).on('keydown', function (event) {
    if (event.key == 'k') {
        $('button#jump-to-next-comp-tag').trigger('click');
    } else if (event.key == 'j') {
        $('button#jump-to-prev-comp-tag').trigger('click');
    }
});


// --------------------------
// Utilities 
// --------------------------

let comp_tag_list: JQuery[] = [];
let comp_tag_id2index: { [comp_tag_id: string]: number } = {};

// Update comp_tag_list after loading html.
$(function () {
    dataLoadingPromise.then(() => {
        // Load mi_list.
        comp_tag_list = dfs_comp_tags($(":root"));

        for (let i = 0; i < comp_tag_list.length; i++) {
            let comp_tag_id = comp_tag_list[i].attr('id');

            if (comp_tag_id != undefined) {
                comp_tag_id2index[comp_tag_id] = i;
            } else {
                console.error('comp_tag_id undefiend!');
                console.error(i);
                console.error(comp_tag_list[i]);
            }
        }
    });
});

$(function () {
    dataLoadingPromise.then(() => {
        $('button#jump-to-next-comp-tag').button();
        $('button#jump-to-next-comp-tag').on('click', function () {
            // First set this value so that the next comp tag is the first one when comp_tag_id is not stored.
            let current_index: number = comp_tag_list.length - 1;

            // Use the stored comp_tag_id if there is.
            if ((sessionStorage['comp_tag_id'] != undefined) && (sessionStorage['comp_tag_id'] in comp_tag_id2index)) {
                current_index = comp_tag_id2index[sessionStorage['comp_tag_id']];
            }

            // Get next index and comp tag.
            const next_index: number = (current_index + 1) % comp_tag_list.length;
            const next_comp_tag = comp_tag_list[next_index];

            const jump_dest = next_comp_tag?.offset()?.top;
            const window_height = $(window).height();
            if (jump_dest != undefined && window_height != undefined) {
                $(window).scrollTop(jump_dest - (window_height / 2));

                // Click the next mi.
                select_comp_tag(next_comp_tag);
            }
        });

        $('button#jump-to-prev-comp-tag').button();
        $('button#jump-to-prev-comp-tag').on('click', function () {
            // First set this value so that the prev comp tag is the last one when comp_tag_id is not stored.
            let current_index: number = 0

            // Use the stored comp_tag_id if there is.
            if ((sessionStorage['comp_tag_id'] != undefined) && (sessionStorage['comp_tag_id'] in comp_tag_id2index)) {
                current_index = comp_tag_id2index[sessionStorage['comp_tag_id']];
            }

            // Get previous index and comp tag.
            const prev_index: number = (current_index + comp_tag_list.length - 1) % comp_tag_list.length;
            const prev_comp_tag = comp_tag_list[prev_index]

            const jump_dest = prev_comp_tag?.offset()?.top;
            const window_height = $(window).height();
            if (jump_dest != undefined && window_height != undefined) {
                $(window).scrollTop(jump_dest - (window_height / 2));

                // Click the prev mi.
                select_comp_tag(prev_comp_tag);
            }
        });
    });
});

$(function () {
    dataLoadingPromise.then(() => {
        $('button#back-to-selected-comp-tag').button();
        $('button#back-to-selected-comp-tag').on('click', function () {
            // Do nothing if no comp_tag is stored.
            if (sessionStorage['comp_tag_id'] != undefined) {
                const selected_comp_tag = $('#' + escape_selector(sessionStorage['comp_tag_id']))

                const jump_dest = selected_comp_tag?.offset()?.top;
                const window_height = $(window).height();
                if (jump_dest != undefined && window_height != undefined) {
                    $(window).scrollTop(jump_dest - (window_height / 2));
                }
            }

        });
    });

});

// ------------------------------
// Set page position at the last
// ------------------------------

$(function () {
    $(window).scrollTop(localStorage['scroll_top']);
})