import {mcdict, mcdict_edit_id, fetch_mcdict_json_data} from "./common";
import {renderPropertiesForm, refreshFormLogic, getFilteredFormData} from "./properties_assignment";

import projectConfig from '../config.json';


let concept_dialog_html = `<p>Variable name within symbolic code:<br />
    <textarea name="code-var-name" rows="1" cols="40"></textarea>
</p>
<p>Description:<br />
    <textarea name="description" rows="3" cols="40"></textarea>
</p>
<p>Category: <div id="concept-category-selector"></div></p>
<p>Properties:<br />
    <form id="concept-properties-form" onsubmit="return false;">
    </form>
</p>`

async function submit_concept(
    $concept_dialog: JQuery,
    primitive_symbols: string[],
    mc_id: string | undefined
): Promise<string | undefined> {

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


export function render_concept_dialog(
    $dialog: JQuery<HTMLElement>,
    primitive_symbols: string[],
    onSuccess: (mc_id: string) => void,
    mc_id: string | undefined = undefined
) {

    $dialog.clone()
        .attr('id', 'concept-dialog')
        .appendTo('body'); // Move it into the DOM so it's "real"
    
    $dialog.html(concept_dialog_html) // Give it the actual dialog content
    $dialog.show(); // Make it visible

    const $categoryContainer = $dialog.find('#concept-category-selector');
    const $propertiesForm = $dialog.find('#concept-properties-form');

    // Setup Category Dropdown
    let taxonomy = projectConfig.CONCEPT_TAXONOMY;
    const categories = Object.keys(taxonomy) as Array<keyof typeof taxonomy>;
    
    let options = categories.map(cat => `<option value="${cat}">${cat}</option>`).join('');
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

    // Define the "Update" behavior
    const updateUI = (init: boolean = false) => {
        const selected = $select.val() as keyof typeof taxonomy;
        const config = taxonomy[selected].concept_fields;
        
        // Re-render the HTML fields
        renderPropertiesForm($propertiesForm, config);

        if (previous_properties && init) {
            for (const [key, value] of Object.entries(previous_properties)) {
                const $field_container = $(`#field-container-${key}`);
                $field_container.show();
                const $input = $propertiesForm.find(`[name="${key}"]`);
                if ($input.length > 0) {
                    if ($input.attr('type') === 'checkbox' && value === "on") {
                        $input.prop('checked', 'on');
                        $input.val('on');
                        $input.prop('disabled', false)
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
                    localStorage['scroll_top'] = $(window).scrollTop();
                    window.location.reload();
                }
            },
            'Cancel': function() { $(this).dialog('close'); }
        },
        close: function() { $(this).remove(); } // Cleanup DOM after close
    });
}