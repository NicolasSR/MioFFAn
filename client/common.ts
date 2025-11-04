// --------------------------
// Type declaration
// --------------------------

export interface Identifier {
  hex: string;
  var: string;
  concept?: number;
}

export interface CompoundConceptOptionsInterface {
  compound_concept_candidates: string[];
  chosen_compound_concept?: number;
}

export interface Concept {
  affixes: string[];
  arity: number;
  description: string;
  color?: string;
}

export interface CompoundConcept {
  arity: number;
  description: string;
  color?: string;
  primitives_hex: string[];
}

export interface Source {
  mi_id: string;
  start_id: string;
  stop_id: string;
  type: number;  // 0: declaration, 1: definition, 2: others
}

export interface CompoundSource {
  comp_tag_id: string;
  start_id: string;
  stop_id: string;
  type: number;  // 0: declaration, 1: definition, 2: others
}

// --------------------------
// utility
// --------------------------

// escape for jQuery selector
export function escape_selector(raw: string) {
  return raw.replace(/[ !"#$%&'()*+,.\/:;<=>?@\[\\\]^`{|}~]/g, "\\$&");
}

// convert UTF-8 string to hex string
export function hex_encode(str: string) {
  let arr = Array.from((new TextEncoder()).encode(str)).map(
    v => v.toString(16));
  return arr.join('');
}

// construct the idf dict from a mi element
export function get_idf(elem: JQuery<any>) {
  let idf = {} as Identifier;
  idf.hex = hex_encode(elem.text());
  idf.var = 'default';

  let var_cand = elem.attr('mathvariant');
  if(var_cand != undefined) {
    if(var_cand == 'normal') {
      idf.var = 'roman';
    } else {
      idf.var = var_cand;
    }
  }

  let concept_cand = elem.data('math-concept');
  if(concept_cand != undefined)
    idf.concept = Number(concept_cand);

  return idf;
}

// // construct the get_comp_idf dict from a math element
// export function get_comp_idf(elem: JQuery<any>) {
//   let comp_idf = {} as CompoundIdentifier;
//   comp_idf.cmc_id = hex_encode(elem.html());

//   let comp_concept_cand = elem.data('compound-math-concept');
//   if(comp_concept_cand != undefined)
//     comp_idf.compound_concept = Number(comp_concept_cand);

//   return idf;
// }

export function get_primitive_hex_list(elem: JQuery<any>) {
  const primitives_list = elem.find("mi");
  let hex_list: string[] = [];
  primitives_list.each(function(index: number, mi_child: HTMLElement) {
    hex_list.push(hex_encode($(mi_child).text()));
  });

  return hex_list;
}

// accessors
export function get_concept(idf: Identifier) {
  if(idf.concept != undefined) {
    return mcdict[idf.hex][idf.var][idf.concept];
  } else {
    return undefined;
  }
}

export function get_comp_concept(elem: JQuery<any>) {
  let cmc_id = elem.data('compound-math-concept');
  if(cmc_id != undefined) {
    return cmcdict[cmc_id];
  } else {
    return undefined;
  }
}

export function get_comp_concept_id(elem: JQuery<any>) {
  let cmc_id = elem.data('compound-math-concept');
  if(cmc_id != undefined) {
    return cmc_id;
  } else {
    return undefined;
  }
}

export function get_concept_cand(idf: Identifier) {
  if(mcdict[idf.hex] != undefined)
    return mcdict[idf.hex][idf.var]; // can be undefined
}

export function get_comp_concept_cand(elem: JQuery<any>) {
  const primitive_hex_list = get_primitive_hex_list(elem);
  let candidates_set: Set<string> = new Set();
  for(const primitive_hex of primitive_hex_list) {
    for(const candidate of hextocmcmap[primitive_hex]){
      candidates_set.add(candidate);
    }
  }
  return Array.from(candidates_set.values());
}

// convert color code from hex to rgb
export function hex2rgb(hex: string) {
  if(hex.slice(0, 1) == "#") {
    hex = hex.slice(1);
  }
  if(hex.length == 3) {
    hex = hex.slice(0, 1) + hex.slice(0, 1) + hex.slice(1, 2) + hex.slice(1, 2) + hex.slice(2, 3) + hex.slice(2, 3);
  }

  return [hex.slice(0, 2), hex.slice(2, 4), hex.slice(4, 6)].map(function(str) {
    return parseInt(str, 16);
  });
}

export function dfs_mis(cur_node: JQuery<any>): JQuery<any>[] {

  let obtained_mis: JQuery<any>[] = [];

  // Add current node if its mi.
  // Only consider the mis in mcdict.
  if((cur_node.is('mi')) && (get_concept_cand(get_idf(cur_node)) != undefined)){
    obtained_mis =  [cur_node];
  }

  // DFS search the children.
  for (let i = 0; i < cur_node.children().length; i++){
    let child = cur_node.children().eq(i);
    obtained_mis = obtained_mis.concat(dfs_mis(child));
  }

  return obtained_mis;
}

export function dfs_comp_tags(cur_node: JQuery<any>): JQuery<any>[] {

  let obtained_comp_tags: JQuery<any>[] = [];

  // Add current node if its a compound tag.
  // Only consider the compound tags in cmcdict.
  if((cur_node.is('msup') || cur_node.is('msub')) && get_comp_concept_cand(cur_node) != undefined){
    obtained_comp_tags = [cur_node];
  }

  // DFS search the children.
  for (let i = 0; i < cur_node.children().length; i++){
    let child = cur_node.children().eq(i);
    obtained_comp_tags = obtained_comp_tags.concat(dfs_comp_tags(child));
  }

  return obtained_comp_tags;
}

// --------------------------
// Prepare the data
// --------------------------

// load from the external json file
export let mcdict_edit_id: number = 0;
export let mcdict = {} as {[key: string]: {[key: string]: Concept[]}};
$.ajax({
  url: '/mcdict.json',
  dataType: 'json',
  async: false,
  success: function(data) {
    // Data is extended to include mcdict version.
    mcdict_edit_id = data[0];
    mcdict = data[1];
  }
});

// Same for cmcdict
export let cmcdict_edit_id: number = 0;
export let cmcdict = {} as {[key: string]:  CompoundConcept};
$.ajax({
  url: '/cmcdict.json',
  dataType: 'json',
  async: false,
  success: function(data) {
    // Data is extended to include mcdict version.
    cmcdict_edit_id = data[0];
    cmcdict = data[1];
  }
});

// define color for each concept
let colors = [
  '#008b8b', '#ff7f50', '#ff4500', '#2f4f4f', '#006400', '#dc143c',
  '#c71585', '#4169e1', '#2e8b57', '#ff1493', '#191970', '#ff69b4',
  '#ff69b4', '#0000cd', '#f4a460', '#ff00ff', '#7cfc00', '#d2691e',
  '#a0522d', '#800000', '#9400d3', '#556b2f', '#4b0082', '#808000'
];

let cnt = 0;
for(let idf_hex in mcdict) {
  for(let idf_var in mcdict[idf_hex]) {
    for(let concept in mcdict[idf_hex][idf_var]) {
      if(mcdict[idf_hex][idf_var][concept].description != undefined) {
        mcdict[idf_hex][idf_var][concept].color = colors[cnt % colors.length];
        cnt++;
      }
    }
  }
}

let cnt_comp = 0;
for(let cmc_index in cmcdict) {
  cmcdict[cmc_index].color = colors[cnt_comp % colors.length];
  cnt_comp++;
}

// load sog from the external json file
export let sog = {} as {sog: Source[]};
$.ajax({
  url: '/sog.json',
  dataType: 'json',
  async: false,
  success: function(data) {
    sog = data;
  }
});

// load comp_sog from the external json file
export let comp_sog = {} as {sog: CompoundSource[]};
$.ajax({
  url: '/comp_sog.json',
  dataType: 'json',
  async: false,
  success: function(data) {
    comp_sog = data;
  }
});

// load hextocmcmap from the external json file
export let hextocmcmap = {} as {[key: string]:  string[]};
$.ajax({
  url: '/hex_to_cmc_map.json',
  dataType: 'json',
  async: false,
  success: function(data) {
    hextocmcmap = data;
  }
});

// load sog from the external json file
export let eoi_list = {} as {eoi_list: string[]};
$.ajax({
  url: '/eoi.json',
  dataType: 'json',
  async: false,
  success: function(data) {
    eoi_list = data;
  }
});


// --------------------------
// Error from the server
// --------------------------

$(function() {
  if($('#error-message').text().length != 0) {
    $('#error-dialog').dialog({
      dialogClass: 'error-dialog',
      modal: true,
      title: 'Error',
      buttons: {
        "OK": function() {
          $(this).dialog('close');
        }
      }
    });
  }
});