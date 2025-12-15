// the MioGatto client. Interface to create custom groups of concepts.
'use strict';

import { COMPOUND_CONCEPT_TAGS,dataLoadingPromise, mi_anno_edit_id, escape_selector} from "./common";
import { give_eoi_borders, getGroupLimitsFromUnorderedIds} from "./main_pages_utils";


let current_group: JQuery[] = [];


$(function () {
    dataLoadingPromise.then(() => {
        // If mark EoI option is checked, mark EoI borders
        let input_opt_mark_eoi = $('#option-mark-eoi');
        if (input_opt_mark_eoi.prop('checked')) {
            // Mark borders of EoI
            give_eoi_borders();
        }

        // Highlight existing groups
        $('mstyle.custom-group').css('background-color', 'rgba(#f9dcfa,0.3)');
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
// Grouping box
// --------------------------

$(function () {
    dataLoadingPromise.then(() => {
        // show the box for annotation in the sidebar 
        function show_grouping_box() {
            let selection_info = '<h4>Current Group Selection:</h4><ul>';
            if (current_group.length === 0) {
                selection_info += '<li>No elements selected.</li>';
            } else {
                for (const el of current_group) {
                    const id = el.attr('id') || 'No ID';
                    const text = el.text().trim().substring(0, 20);
                    selection_info += `<li>${id} (<em>${text}...</em>)</li>`;
                }
                if (current_group.length == 1 &&  current_group[0].attr('class')=="custom-group") {
                    selection_info += '<button id="remove-group">Remove Group</button>';
                } else if (current_group.length >= 2) {
                    selection_info += '<button id="finalize-group">Finalize Group</button>';
                    // selection_info += `<form id="form-finalize-group" method="POST">${hidden}</form>`;
                }
            }
            selection_info += '</ul>';
            let grouping_box = $('#grouping-box');
            grouping_box.html(selection_info);

            $('button#finalize-group').button();
            $('button#finalize-group').on('click', function() {
                const current_group_ids_string = current_group.map(el => el.attr('id') as string);
                const limits_result = getGroupLimitsFromUnorderedIds(current_group_ids_string);
                if (limits_result !== null) {
                    const [start_id, stop_id, ancestry_level_start, ancestry_level_stop] = limits_result;
                    fetch('/_add_group', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            mi_anno_edit_id: mi_anno_edit_id,
                            start_id: start_id,
                            stop_id: stop_id,
                            ancestry_level_start: ancestry_level_start,
                            ancestry_level_stop: ancestry_level_stop,
                        }),
                    }).then(response => {
                        if (response.ok) {
                            // Optionally handle success (e.g., notify user, refresh page)
                            window.location.reload();
                        } else {
                            // Optionally handle error (e.g., notify user)
                            console.error('Failed to submit group');
                        }
                    }).catch(error => {
                        console.error('Error submitting group:', error);
                    });
                }
            });

            $('button#remove-group').button();
            $('button#remove-group').on('click', function() {
                if (current_group.length != 1) {
                    console.error('Cannot remove group if more than one or none elements are selected:');
                }
                const current_group_id = current_group[0].attr('id')
                if (current_group_id !== undefined) {
                    fetch('/_remove_group', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                        },
                        body: JSON.stringify({
                            mi_anno_edit_id: mi_anno_edit_id,
                            group_id: current_group_id,
                        }),
                    }).then(response => {
                        if (response.ok) {
                            // Optionally handle success (e.g., notify user, refresh page)
                            window.location.reload();
                        } else {
                            // Optionally handle error (e.g., notify user)
                            console.error('Failed to remove group');
                        }
                    }).catch(error => {
                        console.error('Error removing group:', error);
                    });
                }
            });
        }

        // Delegated click handler for all potential math elements
        const allTagsSelector = ['mi'].concat(COMPOUND_CONCEPT_TAGS).join(', ');
        $('body').on('click', allTagsSelector, function (event) {
            event.stopPropagation();
            const target = $(this);
            const index = current_group.findIndex(el => el[0] === target[0]);
            if (index > -1) {
                target.css('border', '');
                current_group.splice(index, 1);
            } else {
                target.css('border', '2px solid #007bff');
                current_group.push(target);
            }
            show_grouping_box();
        });
    });
});

// --------------------------
// Remember page position
// --------------------------

// Set page position at the last
$(function () {
    $(window).scrollTop(localStorage['scroll_top']);
})