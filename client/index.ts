// the MioGatto client
'use strict';

import { post } from "jquery";

import {
    COMPOUND_CONCEPT_TAGS, dataLoadingPromise, Source, dfs_comp_tags, mcdict, occurences_dict,
    mcdict_edit_id, escape_selector, get_mc_id_from_query, get_concept_cand, get_primitive_hex_list,
    fetch_mcdict_json_data,
    mi_anno_edit_id
} from "./common";
import {
    highlight_sog_nodes, remove_highlight, sog_to_sog_nodes_for_addition, get_selection,
    reorder_anchor_and_focus_ids, handle_selection_ends, give_eoi_borders
} from "./main_pages_utils"
import {renderPropertiesForm, refreshFormLogic, getFilteredFormData} from "./properties_assignment";

import projectConfig from '../config.json';

// --------------------------
// Get list of tags used as mathematical identifiers ffrom configuration json
// --------------------------

const compound_tags_selector = COMPOUND_CONCEPT_TAGS.join(', ');

// --------------------------
// Options
// --------------------------

let miogatto_options: { [name: string]: boolean } = {
    show_definition: false,
}

$(function () {
    dataLoadingPromise.then(() => {

        // Mark borders of EoI
        give_eoi_borders()

        let input_opt_def = $('#option-show-definition');

        // first time check
        if (localStorage['option-show-definition'] == 'true') {
            input_opt_def.prop('checked', true);
            miogatto_options.show_definition = true
        } else {
            miogatto_options.show_definition = false
        }

        give_sog_highlight();

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
    const mc_id = get_mc_id_from_query($target)
    if (mc_id != undefined) {
        const concept = mcdict[mc_id]
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

    const current_occurrence_id = sessionStorage['comp_tag_id'];

    // First remove all highlights
    for (let mc_id in mcdict)  {
        for (let sog of mcdict[mc_id].sog_list) {
            const sog_nodes = sog_to_sog_nodes_for_addition(sog);
            remove_highlight(sog_nodes);
        }
    }

    if (current_occurrence_id != undefined) {
        const session_mc_id = get_mc_id_from_query($('#' + escape_selector(current_occurrence_id)));
        if (session_mc_id !== undefined) {
            for (let sog of mcdict[session_mc_id].sog_list) {
                const sog_nodes = sog_to_sog_nodes_for_addition(sog);
                apply_highlight(sog_nodes, sog, session_mc_id);
            }
        }
    } else {
        console.log("No mathematical element selected yet.");
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
                    if (Object.keys(concept.properties).length > 0) {
                        args_info = Object.entries(concept.properties).map(([key, value]) => `${key}: ${value}`).join(', ');
                    }
                    return `${concept.description} <span style="color: #808080;">[${args_info}]</span>`;
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
        if (Object.keys(mc_candidate.properties).length > 0) {
            args_info = Object.entries(mc_candidate.properties).map(([key, value]) => `${key}: ${value}`).join(', ');
        }

        let item = `${radio_input}<span class="keep"><label for="c${mc_radio_num}">
${mc_candidate.description} <span style="color: #808080;">[${args_info}]</span>
(<a class="edit-concept" data-mc-id="${mc_candidate_id}" href="javascript:void(0);">edit</a>)
</label></span>`
        radios += item;
    }

    let candidates_list = `<div class="keep" id="mc-radio-list-${comp_tag_id}">${radios}</div>`;
    let buttons = '<p><button id="assign-concept">Assign</button> <button id="remove-concept" type="button">Remove</button> <button id="new-concept" type="button">New</button></p>'

    console.log('occurences_dict', occurences_dict)
    if (comp_tag_id in occurences_dict) {
        buttons += '<p><button id="edit-occurence-properties">Edit occurence prop.</button></p>';
    }

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
                localStorage['scroll_top'] = $(window).scrollTop();
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
    edit_occurence_properties_button(comp_tag_id);
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

async function submit_concept($concept_dialog: JQuery, primitive_symbols: string[], mc_id: string | undefined): Promise<string | undefined> {

    const concept_data = {
        mcdict_edit_id: mcdict_edit_id,
        mc_id: mc_id,
        code_var_name: $concept_dialog.find('textarea[name="code-var-name"]').val(),
        description: $concept_dialog.find('textarea[name="description"]').val(),
        concept_category: $concept_dialog.find('select[name="concept-category"]').val(),
        properties: getFilteredFormData($concept_dialog.find('#concept-properties-form')),
        primitive_symbols: primitive_symbols
    }

    try {
        const response = await fetch('/_register_concept', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(concept_data),
        });

        const data = await response.json();
        if (response.ok) {
            return data.mc_id;
        } else {
            console.error("Error:", data.message);
            alert("Error: " + data.message);
            return undefined;
        }
    } catch(error) {
        console.error('Error creating concept:', error);
        return undefined;
    }
}

function render_concept_dialog(primitive_symbols: string[], onSuccess: (mc_id: string) => void, mc_id: string | undefined = undefined) {
    // 1. Prepare the Dialog Node
    // Use a <div> if the template is just a hidden skeleton
    let $dialog = $('#concept-dialog-template')
        .clone()
        .attr('id', 'concept-dialog')
        .appendTo('body') // Move it into the DOM so it's "real"
        .show(); 

    const $categoryContainer = $dialog.find('#concept-category-selector');
    const $propertiesForm = $dialog.find('#concept-properties-form');

    // 2. Setup Category Dropdown
    const taxonomy = projectConfig.CONCEPT_TAXONOMY;
    const categories = Object.keys(taxonomy) as Array<keyof typeof taxonomy>;
    
    let options = categories.map(cat => `<option value="${cat}">${cat}</option>`).join('');
    options += `<option value="symbol-placeholder">Symbol Placeholder</option>`
    $categoryContainer.html(`<select name="concept-category" class="form-control">${options}</select>`);
    
    const $select = $categoryContainer.find('select');

    let previous_properties: {[key: string]: string} | undefined = undefined;
    if (mc_id) {
        const concept = mcdict[mc_id];
        if (concept) { 
            $dialog.find('textarea[name="code-var-name"]').val(concept.code_var_name);
            $dialog.find('textarea[name="description"]').val(concept.description);
            $select.val(concept.concept_category);
            previous_properties = concept.properties;
        } else {
            console.warn(`Concept with mc_id ${mc_id} not found in mcdict.`);
        }

    }

    // 3. Define the "Update" behavior
    const updateUI = (init: boolean = false) => {
        const selected = $select.val() as keyof typeof taxonomy;
        const config = taxonomy[selected].concept_fields;
        
        // Re-render the HTML fields
        renderPropertiesForm($propertiesForm, config);

        if (previous_properties && init) {
            for (const [key, value] of Object.entries(previous_properties)) {
                const $input = $propertiesForm.find(`[name="${key}"]`);
                if ($input.length > 0) {
                    if ($input.attr('type') === 'checkbox' && value === "on") {
                        $input.prop('checked', 'on');
                    } else {
                        $input.val(value);
                    }
                }
            }
        }

        // Apply the JSON-Logic (hiding/showing fields)
        refreshFormLogic($propertiesForm, config);
    };

    // 4. Attach Listeners
    // Change category -> Re-render everything
    $select.on('change', () => updateUI());

    // Change an input -> Only refresh logic (much faster)
    // $propertiesForm.on('change', 'input, select, textarea', () => {
    $propertiesForm.on('change', () => {
        const selected = $select.val() as keyof typeof taxonomy;
        refreshFormLogic($propertiesForm, taxonomy[selected].concept_fields);
    });

    // 5. Initialize & Open
    updateUI(true); // Build the initial state

    $dialog.dialog({
        modal: true,
        title: 'New Concept',
        width: 500,
        buttons: {
            'OK': async function() {
                const $this = $(this);
                // Disable button to prevent double-clicks
                $this.parent().find('button:contains("OK")').prop('disabled', true);
                const assigned_mc_id = await submit_concept($dialog, primitive_symbols, mc_id);
                if (assigned_mc_id) {
                    await fetch_mcdict_json_data();
                    onSuccess(assigned_mc_id); // Run the assignment here!
                    $this.dialog('close');
                    window.location.reload();
                }
            },
            'Cancel': function() { $(this).dialog('close'); }
        },
        close: function() { $(this).remove(); } // Cleanup DOM after close
    });
}

async function submit_occurrence_properties(comp_tag_id: string, $occurrence_dialog: JQuery): Promise<boolean> {

    const occurrence_data = {
        mcdict_edit_id: mcdict_edit_id,
        comp_tag_id: comp_tag_id,
        properties: getFilteredFormData($occurrence_dialog.find('#occurrence-properties-form'))
    }

    try {
        const response = await fetch('/_edit_occurence_properties', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(occurrence_data),
        });

        const data = await response.json();
        if (response.ok) {
            return true
        } else {
            console.error("Error:", data.message);
            alert("Error: " + data.message);
            return false
        }
    } catch(error) {
        console.error('Error creating concept:', error);
        return false;
    }
}

function render_occurrence_dialog(comp_tag_id: string) {

    const occurrence = occurences_dict[comp_tag_id];
    if (occurrence === undefined) {
        console.warn(`No occurrence found for comp_tag_id ${comp_tag_id}`);
        return;
    }
    const mc_id = occurrence ? occurrence.mc_id : undefined;
    if (mc_id === undefined) {
        console.warn(`No mc_id found for occurrence with comp_tag_id ${comp_tag_id}`);
        return;
    }

    // Prepare the Dialog Node
    // Use a <div> if the template is just a hidden skeleton
    let $dialog = $('#occurrence-dialog-template')
        .clone()
        .attr('id', 'occurrence-dialog')
        .appendTo('body') // Move it into the DOM so it's "real"
        .show(); 

    const taxonomy = projectConfig.CONCEPT_TAXONOMY;
    const mc_category = mcdict[mc_id].concept_category as keyof typeof taxonomy;
    const mc_properties = mcdict[mc_id].properties;
    
    const $propertiesForm = $dialog.find('#occurrence-properties-form');
    const previous_properties = occurrence.properties;
    const config = taxonomy[mc_category].occurrence_fields;
    
    renderPropertiesForm($propertiesForm, config, mc_properties);
    
    if (previous_properties) {
        for (const [key, value] of Object.entries(previous_properties)) {
            const $input = $propertiesForm.find(`[name="${key}"]`);
            if ($input.length > 0) {
                if ($input.attr('type') === 'checkbox' && value === "on") {
                    $input.prop('checked', 'on');
                } else {
                    $input.val(value);
                }
            }
        }
    }

    // Apply the JSON-Logic (hiding/showing fields)
    refreshFormLogic($propertiesForm, config, mc_properties);

    // Change an input -> Only refresh logic (much faster)
    // $propertiesForm.on('change', 'input, select, textarea', () => {
    $propertiesForm.on('change', () => {
        refreshFormLogic($propertiesForm, config, mc_properties);
    });

    $dialog.dialog({
        modal: true,
        title: 'New Concept',
        width: 500,
        buttons: {
            'OK': async function() {
                const $this = $(this);
                // Disable button to prevent double-clicks
                $this.parent().find('button:contains("OK")').prop('disabled', true);
                const success = await submit_occurrence_properties(comp_tag_id, $dialog);
                if (success) {
                    await fetch_mcdict_json_data();
                    $this.dialog('close');
                    window.location.reload();
                } else {
                    alert("Unsuccessful Occurrence Properties Submission")
                }
            },
            'Cancel': function() { $(this).dialog('close'); }
        },
        close: function() { $(this).remove(); } // Cleanup DOM after close
    });
}

function new_concept_button(comp_tag_id: string) {
    const primitive_symbols = get_primitive_hex_list($('#' + escape_selector(comp_tag_id)))
    const $btn = $('button#new-concept').button();
    $btn.on('click', function () {
        render_concept_dialog(primitive_symbols, (assigned_mc_id) => {
            submit_assign_concept(comp_tag_id, assigned_mc_id);
        });
    });
}

function edit_concept(mc_id: string) {
    const primitive_symbols = mcdict[mc_id].primitive_symbols
    render_concept_dialog(primitive_symbols, (assigned_mc_id) => {}, mc_id);
    };

function edit_occurence_properties_button(comp_tag_id: string) {
    const $btn = $('button#edit-occurence-properties').button();
    $btn.on('click', function () { 
        render_occurrence_dialog(comp_tag_id);
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

//-------------------------------
//LLM utilities
//-------------------------------
$(function () {
    dataLoadingPromise.then(() => {
        $('button#auto_segment_symbols').button();
        $('button#auto_segment_symbols').on('click', function () {
            localStorage['scroll_top'] = $(window).scrollTop();
            fetch('/_auto_segment_symbols', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    mi_anno_edit_id: mi_anno_edit_id,
                    mcdict_edit_id: mcdict_edit_id,
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
                console.error('Error segmenting symbols:', error);
            });
        });

        $('button#auto_assign_concepts').button();
        $('button#auto_assign_concepts').on('click', function () {
            localStorage['scroll_top'] = $(window).scrollTop();
            fetch('/_auto_assign_concepts', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    mi_anno_edit_id: mi_anno_edit_id,
                    mcdict_edit_id: mcdict_edit_id,
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
                console.error('Error assigning concepts automtically:', error);
            });
        });

        $('button#auto_highlight_sources').button();
        $('button#auto_highlight_sources').on('click', function () {
            localStorage['scroll_top'] = $(window).scrollTop();
            fetch('/_auto_highlight_sources', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    mi_anno_edit_id: mi_anno_edit_id,
                    mcdict_edit_id: mcdict_edit_id,
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
                console.error('Error assigning concepts automtically:', error);
            });
        });

    });
});


// ------------------------------
// Set page position at the last
// ------------------------------

$(function () {
    $(window).scrollTop(localStorage['scroll_top']);
})