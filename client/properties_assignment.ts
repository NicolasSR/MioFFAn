import {mcdict_edit_id} from "./common";

export function new_edit_occurence_properties_button(comp_tag_id: string) {
    $('button#edit-occurence-properties').button();
    $('button#edit-occurence-properties').on('click', async function () {

        // Get appropriate pulldown and checkbox HTML for the case.
        const options_html = await get_properties_options_html('occurence', {'comp_tag_id': comp_tag_id});

        let occ_prop_dialog = $('#occurence-properties-dialog-template').clone();
        occ_prop_dialog.attr('id', 'occurence-properties-dialog');
        occ_prop_dialog.removeClass('occurence-properties-dialog');

        let options_box = occ_prop_dialog.find('#occurence-properties-options-box');
        options_box.html(options_html);

        occ_prop_dialog.dialog({
            modal: true,
            title: 'Edit Occurence Properties',
            width: 500,
            buttons: {
                'OK': function() {
                    localStorage['scroll_top'] = $(window).scrollTop();
                    submit_edit_occurence_properties(comp_tag_id, occ_prop_dialog);
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

export async function get_properties_options_html(properties_type:string, parameters: {[key: string]: string}): Promise<string> {
    let out_html: string = '';

    try {
        if (!(['occurence', 'concept'].includes(properties_type))) {
            console.error("Error: invalid property type.");
            alert("Error: invalid property type.");
        };
        let fetch_url = `/_get_${properties_type}_properties_options_html`;
        let count = 0;
        for (const [key, value] of Object.entries(parameters)) {
            if (count > 0) {fetch_url += `&${key}=${value}`}
            else {fetch_url += `?${key}=${value}`}
            count += 1;
        }

        console.log('fetch_url', fetch_url);

        const response = await fetch(fetch_url, {
            method: 'GET',
            headers: {'Content-Type': 'application/json'}
        })

        const data = await response.json();

        if (response.ok) {
            out_html = data.out_html;
        } else {
            console.error("Error:", data.message);
            alert("Error: " + data.message);
        }
    } catch(error) {
        console.error('Error getting occurence properties options html:', error);
    }

    if (out_html === undefined) {
        console.error("Error: html_out is undefined");
    }

    return out_html;

}

function submit_edit_occurence_properties(comp_tag_id: string, occ_prop_dialog: JQuery<HTMLElement>) {
    
    // Gather selected options from pulldowns and checkboxes.
    // let selected_options: {[key: string]: string} = {};
    let selected_options: string[] = [];

    occ_prop_dialog.find('select').each(function() {
        const select_name = $(this).attr('name');
        const selected_value = $(this).val() as string;
        if (select_name !== undefined && selected_value !== '') {
            selected_options.push(selected_value);
        }
    }
    );
    
    occ_prop_dialog.find('input[type="checkbox"]').each(function() {
        const checkbox_name = $(this).attr('id');
        if (checkbox_name !== undefined) {
            if ($(this).is(':checked')) {
                selected_options.push(checkbox_name);
            }
        }
    }
    );

    // const selected_options_list = Object.keys(selected_options).map(key => selected_options[key]);

    // Submit the selected options to the server.
    fetch('/_edit_occurence_properties', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({
            mcdict_edit_id: mcdict_edit_id,
            comp_tag_id: comp_tag_id,
            selected_options: selected_options
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
        console.error('Error submitting occurence properties:', error);
    });
}