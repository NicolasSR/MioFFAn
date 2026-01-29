// the MioGatto client
'use strict';

import { post } from "jquery";
import {
    COMPOUND_CONCEPT_TAGS, dataLoadingPromise, mcdict, mcdict_edit_id, eoi_dict,
    escape_selector, get_mc_id_from_query
} from "./common";
import { give_eoi_borders } from "./main_pages_utils"

// --------------------------
// Get list of tags used as mathematical identifiers ffrom configuration json
// --------------------------

const compound_tags_selector = COMPOUND_CONCEPT_TAGS.join(', ');

// --------------------------
// Options
// --------------------------

$(function () {
    dataLoadingPromise.then(() => {
        // Mark borders of EoI
        give_eoi_borders()
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
// Comp Tag selection
// --------------------------

// function select_comp_tag($comp_tag: JQuery) {
//     console.log('Selected: ', $comp_tag)
//     // if already selected, remove it
//     let old_comp_tag_id = sessionStorage.getItem('comp_tag_id');
//     if (old_comp_tag_id != undefined) {
//         $('#' + escape_selector(old_comp_tag_id)).css({ 'border': '', 'padding': '' });
//     }

//     // store id of the currently selected mi
//     sessionStorage['comp_tag_id'] = $comp_tag.attr('id');

//     // show the annotation box
//     show_anno_box($comp_tag);
// }


// --------------------------
// Annotation box
// --------------------------

function get_equation_from_math(math_node: JQuery) {
    return math_node.closest('.formula')
}

function remove_selection_box(equation_id: string) {
    let equation_query = $('#' + equation_id)
    equation_query.removeAttr('style');
}

$(function () {
    dataLoadingPromise.then(() => {
        // show the box for annotation in the sidebar 
        function show_anno_box(current_equation: JQuery) {
            // highlight the selected element
            let current_equation_id = current_equation.attr('id')
            if (current_equation_id != undefined && current_equation_id in eoi_dict) {
                sessionStorage["equation_id"] = current_equation_id
                current_equation.attr('style', 'border: dotted 2px #000000; padding: 10px;');

                let anno_box = $('#anno-box')

                let button_edit_symbolic_code = '<p><button id="edit-symbolic-code">Edit code</button></p>';
                anno_box.html(button_edit_symbolic_code)
                $('button#edit-symbolic-code').button();
                $('button#edit-symbolic-code').on('click', function () {
                    edit_symbolic_code(current_equation_id!)
                });
            } else {
                console.warn("Selected equation does not have an ID")
            }
        }

        $('math').on('click', function () {
            // if already selected, remove it
            let equation = get_equation_from_math($(this));
            remove_selection_box(sessionStorage['equation_id']);
            show_anno_box(equation);
        });

        // keep position and sidebar content after submiting the form
        // This '$(window).scrollTop' seems redundant but somehow fixes the page position problems...
        $(window).scrollTop(localStorage['scroll_top']);
        let equation_id = sessionStorage['equation_id'];
        if (equation_id != undefined) {
            show_anno_box($('#' + escape_selector(equation_id)));
        }
    });
});

function submit_edit_symbolic_code(eoi_id: string, symbolic_code_dialog: JQuery<HTMLElement>) {

    const symbolic_code = symbolic_code_dialog.find('textarea[name="symbolic-code"]').val();

    fetch('/_edit_symbolic_code', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            mcdict_edit_id: mcdict_edit_id,
            eoi_id: eoi_id,
            symbolic_code: symbolic_code
        }),
    }).then(async (response) => {
        const data = await response.json();
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
        console.error('Error creating concept:', error);
    });
}

function edit_symbolic_code(eoi_id: string) {

    let symbolic_code_dialog = $('#symbolic-code-dialog-template').clone();
    symbolic_code_dialog.removeAttr('id');

    const eoi = eoi_dict[eoi_id];
    
    // Initialize interactive lists of variables and operators
    let $symbolic_code_node = symbolic_code_dialog.find('textarea[name="symbolic-code"]');
    const $var_container = symbolic_code_dialog.find('div[id=var-list-container]');
    const $op_container = symbolic_code_dialog.find('div[id=op-list-container]');
    initEquationBuilder($symbolic_code_node, $var_container, $op_container);

    // put the current values
    $symbolic_code_node.text(eoi.symbolic_code);

    symbolic_code_dialog.dialog({
        modal: true,
        title: 'Edit Concept',
        width: 500,
        buttons: {
            'OK': function () {
                localStorage['scroll_top'] = $(window).scrollTop();
                submit_edit_symbolic_code(eoi_id, symbolic_code_dialog)
            },
            'Cancel': function () {
                $(this).dialog('close');
            }
        }
    });
}

/**
 * Helper function to create a button for a snippet and attach the click event
 */
function createTokenButton(token: string, $symbolic_code_node: JQuery): HTMLButtonElement {
    const btn = document.createElement('button');
    btn.textContent = token;
    btn.className = 'token-btn';
    btn.type = 'button'; // Prevent form submission if inside a form
    
    // Add click listener
    btn.addEventListener('click', () => {
        insertAtCursor(token, $symbolic_code_node);
    });
    
    return btn;
}

/**
 * The core logic: Inserts text where the user's cursor currently is
 */
function insertAtCursor(textToInsert: string, $symbolic_code_node: JQuery): void {
    let symbolic_code_node = $symbolic_code_node.get(0) as HTMLTextAreaElement

    if (symbolic_code_node === undefined) return;

    const startPos = symbolic_code_node.selectionStart;
    const endPos = symbolic_code_node.selectionEnd;

    // Insert the text between the start and end of the selection
    // (This works even if nothing is selected, effectively just inserting)
    symbolic_code_node.setRangeText(textToInsert, startPos, endPos, 'end');

    // UX Polish: Immediately bring focus back to the textarea so the user 
    // can keep typing or click another button without clicking the box again.
    symbolic_code_node.focus();
}

/**
 * Initialization function to populate the UI
 */
function initEquationBuilder($symbolic_code_node: JQuery, $var_container: JQuery, $op_container: JQuery): void {
    let var_container = $var_container.get(0)
    let op_container = $op_container.get(0)

    if (var_container === undefined || op_container === undefined) return;

    const var_list = prepare_var_list();
    const op_list = prepare_op_list();

    // Clear existing content if re-initializing
    var_container.innerHTML = '';
    op_container.innerHTML = '';

    // Populate Variables
    var_list.forEach(token => {
        var_container!.appendChild(createTokenButton(token, $symbolic_code_node));
    });

    // Populate Operators
    op_list.forEach(token => {
        op_container!.appendChild(createTokenButton(token, $symbolic_code_node));
    });
    
}

function prepare_var_list(): string[]{
    let var_list: string[] = [];
    for (let mc_id in mcdict) {
        if (!mc_id.includes("llm_placeholder_concept")) {
            var_list.push(mcdict[mc_id].code_var_name);
            }
        }
    return var_list
}

function prepare_op_list(): string[]{
    const op_list: string[] = [
        '+',
        '-',
        '*',
        'norm()',
        'dot_prod()',
        'contract()',
        'double_contract()',
        'grad()',
        'sym_grad()',
        'div()',
        'matrix_prod()',
        'matrix_transpose()',
        'matrix_vector_prod()',
        'matrix_determinant()',
        'matrix_inverse()',
        'matrix_cofactor()',
        'vector_cross_prod()',
        'vector_outer_prod()'
    ];
    return op_list;
}

// --------------------------
// Keybord shortcuts
// --------------------------


// $(document).on('keydown', function (event) {
//     if (event.key == 'k') {
//         $('button#jump-to-next-eoi').trigger('click');
//     } else if (event.key == 'j') {
//         $('button#jump-to-prev-eoi').trigger('click');
//     }
// });


// --------------------------
// Utilities 
// --------------------------


// $(function () {
//     $('button#jump-to-next-comp-tag').button();
//     $('button#jump-to-next-comp-tag').on('click', function () {
//         // First set this value so that the next comp tag is the first one when comp_tag_id is not stored.
//         let current_index: number = comp_tag_list.length - 1;

//         // Use the stored comp_tag_id if there is.
//         if ((sessionStorage['comp_tag_id'] != undefined) && (sessionStorage['comp_tag_id'] in comp_tag_id2index)) {
//             current_index = comp_tag_id2index[sessionStorage['comp_tag_id']];
//         }

//         // Get next index and comp tag.
//         const next_index: number = (current_index + 1) % comp_tag_list.length;
//         const next_comp_tag = comp_tag_list[next_index];

//         const jump_dest = next_comp_tag?.offset()?.top;
//         const window_height = $(window).height();
//         if (jump_dest != undefined && window_height != undefined) {
//             $(window).scrollTop(jump_dest - (window_height / 2));

//             // Click the next mi.
//             select_comp_tag(next_comp_tag);
//         }
//     });

//     $('button#jump-to-prev-comp-tag').button();
//     $('button#jump-to-prev-comp-tag').on('click', function () {
//         // First set this value so that the prev comp tag is the last one when comp_tag_id is not stored.
//         let current_index: number = 0

//         // Use the stored comp_tag_id if there is.
//         if ((sessionStorage['comp_tag_id'] != undefined) && (sessionStorage['comp_tag_id'] in comp_tag_id2index)) {
//             current_index = comp_tag_id2index[sessionStorage['comp_tag_id']];
//         }

//         // Get previous index and comp tag.
//         const prev_index: number = (current_index + comp_tag_list.length - 1) % comp_tag_list.length;
//         const prev_comp_tag = comp_tag_list[prev_index]

//         const jump_dest = prev_comp_tag?.offset()?.top;
//         const window_height = $(window).height();
//         if (jump_dest != undefined && window_height != undefined) {
//             $(window).scrollTop(jump_dest - (window_height / 2));

//             // Click the prev mi.
//             select_comp_tag(prev_comp_tag);
//         }
//     });

// });

// $(function () {
//     $('button#back-to-selected-comp-tag').button();
//     $('button#back-to-selected-comp-tag').on('click', function () {
//         // Do nothing if no comp_tag is stored.
//         if (sessionStorage['comp_tag_id'] != undefined) {
//             const selected_comp_tag = $('#' + escape_selector(sessionStorage['comp_tag_id']))

//             const jump_dest = selected_comp_tag?.offset()?.top;
//             const window_height = $(window).height();
//             if (jump_dest != undefined && window_height != undefined) {
//                 $(window).scrollTop(jump_dest - (window_height / 2));
//             }
//         }

//     });

// });

// ------------------------------
// Set page position at the last
// ------------------------------

$(function () {
    $(window).scrollTop(localStorage['scroll_top']);
})