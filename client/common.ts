// --------------------------
// Type declaration
// --------------------------

declare global {
    interface Window {
        COMPOUND_CONCEPT_TAGS: string[];
        initializeNavButtons: () => void;
        initializeSampleNavButtons: () => void;
    }
}

export const COMPOUND_CONCEPT_TAGS: string[] = window.COMPOUND_CONCEPT_TAGS.concat("mi");

export interface Source {
    start_id: string;
    stop_id: string;
    type: number;  // 0: declaration, 1: definition, 2: others
}

export interface Concept {
    code_var_name: string;
    description: string;
    concept_category: string;
    properties: { [key: string]: string };
    primitive_symbols: string[];
    sog_list: Source[];
    color?: string;
}

export interface EoI {
    symbolic_code: string;
}

export interface Occurence {
    mc_id: string;
    tag_name: string;
    properties: { [key: string]: string };
}

// --------------------------
// Internal functions
// --------------------------

// convert UTF-8 string to hex string
function hex_encode(str: string) {
    let arr = Array.from((new TextEncoder()).encode(str)).map(
        v => v.toString(16));
    return arr.join('');
}

// load hextocmcmap from the external json file
let hextocmcmap = {} as { [key: string]: string[] };
$.ajax({
    url: '/hex_to_mc_map.json',
    dataType: 'json',
    async: false,
    success: function (data) {
        hextocmcmap = data;
    }
});

// --------------------------
// utility
// --------------------------

// escape for jQuery selector
export function escape_selector(raw: string) {
    return raw.replace(/[ !"#$%&'()*+,.\/:;<=>?@\[\\\]^`{|}~]/g, "\\$&");
}

export function get_idf(elem: JQuery<any>) {
    console.error("get_idf is deprecated. Please use get_primitive_hex_list instead")    
}

export function get_primitive_hex_list(elem: JQuery<any>) {
    const primitives_list = elem.find("mi").add(elem.filter("mi"));
    let hex_list: string[] = [];
    primitives_list.each(function (index: number, mi_child: HTMLElement) {
        hex_list.push(hex_encode($(mi_child).text()));
    });
    return hex_list;
}

export function get_concept(idf: any) {
    console.error("get_concept is deprecated. Use get_mc_id_from_query instead")
}

// accessors
export function get_mc_id_from_query($elem: JQuery<any>):string | undefined {
    let mc_id = $elem.data('mc-id')
    if (mc_id !== undefined) {
        return mc_id.toString();
    } else {
        return undefined;
    }
}

export function get_concept_cand(elem: JQuery<any>) {
    const primitive_hex_list = get_primitive_hex_list(elem);
    console.log('primitive_hex_list', primitive_hex_list)
    console.log('hextocmcmap', hextocmcmap)
    let candidates_set: Set<string> = new Set();
    for (const primitive_hex of primitive_hex_list) {
        if (hextocmcmap[primitive_hex] !== undefined) {
            for (const candidate of hextocmcmap[primitive_hex]) {
                candidates_set.add(candidate);
            }
        }
    }
    console.log('candidates', Array.from(candidates_set.values()))
    return Array.from(candidates_set.values());
}

// convert color code from hex to rgb
export function hex2rgb(hex: string) {
    if (hex.slice(0, 1) == "#") {
        hex = hex.slice(1);
    }
    if (hex.length == 3) {
        hex = hex.slice(0, 1) + hex.slice(0, 1) + hex.slice(1, 2) + hex.slice(1, 2) + hex.slice(2, 3) + hex.slice(2, 3);
    }

    return [hex.slice(0, 2), hex.slice(2, 4), hex.slice(4, 6)].map(function (str) {
        return parseInt(str, 16);
    });
}

// Deep First Search for compound concept tags
export function dfs_comp_tags(cur_node: JQuery<any>): JQuery<any>[] {

    let obtained_comp_tags: JQuery<any>[] = [];

    // Add current node if its a compound tag.
    // Only consider the compound tags in cmcdict.
    const is_compound_tag = COMPOUND_CONCEPT_TAGS.some(tag => cur_node.is(tag));
    if (is_compound_tag && get_concept_cand(cur_node) != undefined) {
        obtained_comp_tags = [cur_node];
    }

    // DFS search the children.
    for (let i = 0; i < cur_node.children().length; i++) {
        let child = cur_node.children().eq(i);
        obtained_comp_tags = obtained_comp_tags.concat(dfs_comp_tags(child));
    }

    return obtained_comp_tags;
}

// --------------------------
// Prepare the data
// --------------------------

// define color for each concept
let colors = [
    '#008b8b', '#ff7f50', '#ff4500', '#2f4f4f', '#006400', '#dc143c',
    '#c71585', '#4169e1', '#2e8b57', '#ff1493', '#191970', '#ff69b4',
    '#ff69b4', '#0000cd', '#f4a460', '#ff00ff', '#7cfc00', '#d2691e',
    '#a0522d', '#800000', '#9400d3', '#556b2f', '#4b0082', '#808000'
];

// load mcdict info from the external json file
export let mcdict_edit_id: number = 0;
export let mcdict = {} as { [key: string]: Concept };
export let occurences_dict = {} as { [key: string]: Occurence };
export let eoi_dict = {} as { [key: string]: EoI };
// export let occdict = {} as { [key: string]: Occurence };

// Load data immediately when the app starts. Assign the promise to
// a variable so that other modules can await it.
export const dataLoadingPromise = (async () => {
    console.log("Start loading data...");
    await fetch_mcdict_json_data();
    await fetch_mi_anno_json_data();
    await fetch_sample_json_data();
    console.log("Data loading complete!");

    let cnt = 0;
    for (let mc_index in mcdict) {
        mcdict[mc_index].color = colors[cnt % colors.length];
        cnt++;
    }
})();

export function fetch_mcdict_json_data(onSuccess?: () => void) {
    return $.ajax({
        url: '/mcdict.json',
        dataType: 'json',
        async: true,
        success: function (data) {
            // Data is extended to include mcdict version.
            mcdict_edit_id = data[0];
            mcdict = data[1]['mcdict'];
            occurences_dict = data[1]['occurences_dict'];
            eoi_dict = data[1]['eoi_dict'];
            console.log("MCDict refreshed successfully!");
            
            // CRITICAL STEP: 
            // Updating variables doesn't automatically update the HTML.
            // You must call your render function here.
            if (onSuccess) {
                onSuccess();
            } else {
                // If you have a global render function, call it here:
                // updateUI(); 
            }
        },
        error: function(err) {
            console.error("Failed to fetch MCDict", err);
        }
    });
}

// load mio_anno info from the external json file
export let mi_anno_edit_id: number = 0;

export function fetch_mi_anno_json_data(onSuccess?: () => void) {
    return $.ajax({
        url: '/mi_anno.json',
        dataType: 'json',
        async: false,
        success: function (data) {
            // Data is extended to include mi_anno version.
            mi_anno_edit_id = data[0];
            console.log("MiAnno refreshed successfully!");
            
            // CRITICAL STEP: 
            // Updating variables doesn't automatically update the HTML.
            // You must call your render function here.
            if (onSuccess) {
                onSuccess();
            } else {
                // If you have a global render function, call it here:
                // updateUI(); 
            }
        },
        error: function(err) {
            console.error("Failed to fetch MiAnno", err);
        }
    });
}

export function fetch_sample_json_data(onSuccess?: () => void) {
    return $.ajax({
        url: '/get_sample_data.json',
        dataType: 'json',
        async: false,
        success: function (data) {
            sessionStorage["sample_name"] = data["sample_name"];
            console.log("Sample data gathered successfully!");
            
            // CRITICAL STEP: 
            // Updating variables doesn't automatically update the HTML.
            // You must call your render function here.
            if (onSuccess) {
                onSuccess();
            } else {
                // If you have a global render function, call it here:
                // updateUI(); 
            }
        },
        error: function(err) {
            console.error("Failed to fetch sample data", err);
        }
    });
}


// // load sog from the external json file
// export let sog = {} as { sog: Source[] };
// $.ajax({
//     url: '/sog.json',
//     dataType: 'json',
//     async: false,
//     success: function (data) {
//         sog = data;
//     }
// });

// --------------------------
// Error from the server
// --------------------------

$(function () {
    if ($('#error-message').text().length != 0) {
        $('#error-dialog').dialog({
            dialogClass: 'error-dialog',
            modal: true,
            title: 'Error',
            buttons: {
                "OK": function () {
                    $(this).dialog('close');
                }
            }
        });
    }
});