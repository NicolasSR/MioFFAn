// import {mcdict_edit_id} from "./common";

const jsonLogic = require('json-logic-js');

export function getFormData($form: JQuery) {
    const data: any = {};
    
    $form.serializeArray().forEach((item) => {
        data[item.name] = item.value;
    });
    return data;
}

export function refreshFormLogic($form: JQuery, config: any, priorData: {[key: string]: string} = {}) {
    const currentData = getFormData($form);
    const totalData = Object.assign({}, currentData, priorData);

    Object.entries(config).forEach(([field_name, field_info]: any) => {
        if(field_info.display_rule) {
            const isVisible = jsonLogic.apply(field_info.display_rule, totalData);
    
            const $el = $(`#field-container-${field_name}`);
            if (isVisible) {
                $el.show().find('input, select').prop('disabled', false);
            } else {
                $el.hide().find('input, select').prop('disabled', true);
            }
        }
    });
}

function getFieldInputType(field_name: string, field_info: any): string {
    switch (field_info.type) {
        case 'categorical':
            let options = '';
            field_info.values.forEach((value: any) => {
                options += `<option value="${value.value}">${value.label}</option>`;
            });
            return `<select name="${field_name}">${options}</select>`;
        case 'boolean':
            return `<input type="checkbox" id="${field_name}" name="${field_name}" />`;
        case 'integer':
            return `<input type="number" name="${field_name}" step="1" />`;
        case 'code':
            return `<textarea name="${field_name}" rows="1"></textarea>`;
        default:
            return `<input type="text" name="${field_name}" />`;
    }
}

export function renderPropertiesForm($form: JQuery, config: any, priorData: {[key: string]: string} = {}) {
    $form.empty();

    Object.entries(config).forEach(([field_name, field_info]: any) => {
        const html = `
            <div id="field-container-${field_name}" class="form-group" style="margin-bottom: 10px;">
                <label for="${field_name}">${field_info.label}</label>
                ${getFieldInputType(field_name, field_info)}
            </div>
        `;
        $form.append(html);
    });

    console.log('Form', $form.html());

    // Run the logic immediately to hide fields that shouldn't be there at start
    refreshFormLogic($form, config, priorData);
}

export function getFilteredFormData($form: JQuery) {
    const data: any = {};
    const unfilteredData = getFormData($form);

    // Remove fields that are in hidden containers or disabled inputs
    for (const [key, value] of Object.entries(unfilteredData)) {
        $form.find(`[name="${key}"]`).each(function() {
            if ($(this).is(':visible') && !$(this).prop('disabled')) {
                data[key] = value;
            } else {
                console.log(`Excluding field ${key} from submission because it is hidden or disabled.`);
            }
        });
    }
    
    return data;
}