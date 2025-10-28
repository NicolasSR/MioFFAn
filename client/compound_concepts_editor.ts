// the MioGatto client. Interface to edit compound concepts
'use strict';

import { post } from "jquery";
import {CompoundConceptOptionsInterface, CompoundConcept, CompoundSource, hex2rgb,
  get_comp_concept, get_comp_concept_id, cmcdict_edit_id, comp_sog, escape_selector, get_primitive_hex_list,
  cmcdict, get_comp_concept_cand, dfs_comp_tags} from "./common" ;
  // dfs_mis, get_idf, mcdict, mcdict_edit_id, sog, escape_selector, get_concept, get_concept_cand} from "./common";
import {highlight_sog_nodes} from "./main_pages_utils"

// --------------------------
// Options
// --------------------------

let miogatto_options: { [name: string]: boolean } = {
  limited_highlight: false,
  show_definition: false,
}

$(function() {

  let input_opt_hl = $('#option-limited-highlight');
  let input_opt_def = $('#option-show-definition');

  // first time check
  if(localStorage['option-limited-highlight'] == 'true') {
    input_opt_hl.prop('checked', true);
    miogatto_options.limited_highlight = true
  } else {
    miogatto_options.limited_highlight = false
  }

  if(localStorage['option-show-definition'] == 'true') {
    input_opt_def.prop('checked', true);
    miogatto_options.show_definition = true
  } else {
    miogatto_options.show_definition = false
  }

  give_sog_highlight();

  // toggle
  input_opt_hl.on('click', function() {
    if($(this).prop('checked')) {
      localStorage['option-limited-highlight'] = 'true';
      miogatto_options.limited_highlight = true
    } else {
      localStorage['option-limited-highlight'] = 'false';
      miogatto_options.limited_highlight = false
    }
    give_sog_highlight();
  });

  input_opt_def.on('click', function() {
    if($(this).prop('checked')) {
      localStorage['option-show-definition'] = 'true';
      miogatto_options.show_definition = true
    } else {
      localStorage['option-show-definition'] = 'false';
      miogatto_options.show_definition = false
    }
    give_sog_highlight();
  });
});

// --------------------------
// Sidebar
// --------------------------

$(function() {
  $('.sidebar-tab input.tab-title').each(function() {
    let tab_name = this.id;
    if(localStorage[tab_name] == 'true') {
      $(`#${tab_name}`).prop('checked', true);
    }

    $(`#${tab_name}`).on('change', function() {
      if($(this).prop('checked')) {
        localStorage[tab_name] = true;
      } else {
        localStorage[tab_name] = false;
      }
    });
  });
});


// --------------------------
// mathcolor
// --------------------------

function give_color(target: JQuery) {
  let comp_concept = get_comp_concept(target);
  if(comp_concept != undefined && comp_concept.color != undefined) {
    target.attr('mathcolor', comp_concept.color);
  }
}

$(function() {
  $('msub').each(function() {
    give_color($(this));
  });
  $('msup').each(function() {
    give_color($(this));
  });
})

// --------------------------
// SoG highlight
// --------------------------


function apply_highlight(sog_nodes: JQuery, comp_tag_node: JQuery, sog: CompoundSource) {
  remove_highlight(sog_nodes);

  let concept = get_comp_concept(comp_tag_node);
  highlight_sog_nodes(concept, sog_nodes, sog, miogatto_options.show_definition)

  // embed SoG information for removing
  sog_nodes.attr({
    'data-compound-sog-node-id': sog.comp_tag_id,
    'data-compound-sog-type': sog.type,
    'data-compound-sog-start': sog.start_id,
    'data-compound-sog-stop': sog.stop_id,
  });
}


function give_sog_highlight() {
  // remove highlight
  for(let s of comp_sog.sog) {
    // get Compound SoG nodes
    // Note: this code is somehow very tricky but it works
    const start_last_dot_index = s.start_id.lastIndexOf('.');
    const stop_last_dot_index = s.stop_id.lastIndexOf('.');
    let start_element_id = s.start_id.slice(0, start_last_dot_index);
    let start_offset = s.start_id.slice(start_last_dot_index +1);
    let stop_element_id = s.stop_id.slice(0, stop_last_dot_index);
    let stop_offset = s.stop_id.slice(stop_last_dot_index +1);
    let sog_nodes;

    // if (s.start_id == s.stop_id) {
      // sog_nodes = $('#' + escape_selector(s.start_id));
    if (start_element_id == stop_element_id) {
      sog_nodes = $('#' + escape_selector(start_element_id));
    } else {
      // let start_node = $('#' + escape_selector(s.start_id));
      // let stop_node = $('#' + escape_selector(s.stop_id));
      let start_node = $('#' + escape_selector(start_element_id));
      let stop_node = $('#' + escape_selector(stop_element_id));

      // sog_nodes = start_node.nextUntil('#' + escape_selector(s.stop_id)).addBack().add(stop_node);
      sog_nodes = start_node.nextUntil('#' + escape_selector(stop_element_id)).addBack().add(stop_node);
    }

    // Option for limited highlighting:
    // If evaluated sog does not match currently selected sompound element, unhighlight it.
    const sog_comp_tag_id = s.comp_tag_id;
    if(miogatto_options.limited_highlight && sessionStorage['comp_tag_id'] != undefined) {
      if(sessionStorage['comp_tag_id'] != sog_comp_tag_id) {
        remove_highlight(sog_nodes);
      }
    }
  }

  // apply highlight
  // for(let s of ) {
  for (let sog_id = 0; sog_id < comp_sog.sog.length; sog_id++) {
    const s = comp_sog.sog[sog_id];
    // get Compound SoG nodes
    // Note: this code is somehow very tricky but it works
    const start_last_dot_index = s.start_id.lastIndexOf('.');
    const stop_last_dot_index = s.stop_id.lastIndexOf('.');
    let start_element_id = s.start_id.slice(0, start_last_dot_index);
    let start_offset = parseInt(s.start_id.slice(start_last_dot_index +1), 10);
    let stop_element_id = s.stop_id.slice(0, stop_last_dot_index);
    let stop_offset = parseInt(s.stop_id.slice(stop_last_dot_index +1), 10);
    let sog_nodes_root, sog_nodes;
    // if (s.start_id == s.stop_id) {
      // sog_nodes = $('#' + escape_selector(s.start_id));
    if (start_element_id == stop_element_id) {
      sog_nodes_root = $('#' + escape_selector(start_element_id));
      const start_node_element = sog_nodes_root[0];
      let start_span_id = ''
      let stop_span_id = ''

      if (start_node_element.className == "gd_text"){
        if (!hasWordMap(start_node_element)) {
          divide_and_index_text_span(start_node_element);
        }
        start_span_id = get_word_id_by_index(start_node_element, start_offset);
        stop_span_id = get_word_id_by_index(start_node_element, stop_offset);
      } else {
        throw new Error("Grounding text must start and finish in 'gd_text' class")
      }

      // newSpan.className = 'sog_selection';
      // if (start_node_original_text !== null) {
      //   newSpan.textContent = start_node_original_text.substring(start_offset, stop_offset);
      //   newSpan.id = newSpan_id;
      //   tail_text = start_node_original_text.substring(stop_offset);
      //   sog_nodes_root[0].textContent = start_node_original_text.substring(0, start_offset)
      // } else {
      //   newSpan.textContent = "TEXT PLACEHOLDER";
      //   tail_text = 'TAIL TEXT PLACEHOLDER'
      //   console.warn("Element exists but has no text content.");
      // }
      // start_node_element.appendChild(newSpan);
      // start_node_element.appendChild(document.createTextNode(tail_text))
      
      if (start_span_id == stop_span_id) {
        sog_nodes = $('#' + escape_selector(start_span_id));
      } else {
        let start_node = $('#' + escape_selector(start_span_id));
        let stop_node = $('#' + escape_selector(stop_span_id));
        sog_nodes = start_node.nextUntil('#' + escape_selector(stop_span_id)).addBack().add(stop_node);
      }

    } else {
      // let start_node = $('#' + escape_selector(s.start_id));
      // let stop_node = $('#' + escape_selector(s.stop_id));
      let start_node = $('#' + escape_selector(start_element_id));
      let stop_node = $('#' + escape_selector(stop_element_id));

      sog_nodes = start_node.nextUntil('#' + escape_selector(stop_element_id)).addBack().add(stop_node);
    }

    const sog_comp_tag_id = s.comp_tag_id;
    const comp_tag_node = $('#' + escape_selector(sog_comp_tag_id))
    if(miogatto_options.limited_highlight && sessionStorage['comp_tag_id'] != undefined) {
      if(sessionStorage['comp_tag_id'] ==  sog_comp_tag_id) {
        apply_highlight(sog_nodes, comp_tag_node, s);
      } 
    } else {
      // always apply
      apply_highlight(sog_nodes, comp_tag_node, s);
    }
  }
}

// --------------------------
// tooltip
// --------------------------

$(function() {
  $(document).tooltip({
    show: false,
    hide: false,
    items: '[data-compound-math-concept]',
    content: function() {
      let concept = get_comp_concept($(this));
      if(concept != undefined) {
        return `${concept.description} <span style="color: #808080;"> (arity: ${concept.arity})</span>`;
      } else {
        return '(No description)';
      }
    },
    open: function(_event, _ui) {
      $('msub').each(function() {
        give_color($(this));
      });
      $('msup').each(function() {
        give_color($(this));
      });
    }
  });
});

// --------------------------
// Annotation box
// --------------------------

$(function() {
  // show the box for annotation in the sidebar 
  function draw_anno_box(comp_tag_id: string, comp_concept_cand: string[]) {
    // construct the form with the candidate list
    let hidden = `<input type="hidden" name="comp_tag_id" value="${comp_tag_id}" />`;
    let radios = '';

    for(let comp_concept_radio_num in comp_concept_cand) {
      let cand_cmc_id = comp_concept_cand[comp_concept_radio_num];
      let cand_cmc = cmcdict[cand_cmc_id]

      // let check = (Number(concept_id) == idf.concept) ? 'checked' : '';
      const check = (cand_cmc_id == get_comp_concept_id($('#' + escape_selector(comp_tag_id)))) ? 'checked' : ''
      let input = `<input type="radio" name="cmc_id" id="c${comp_concept_radio_num}" value="${cand_cmc_id}" ${check} />`;

      let item = `${input}<span class="keep"><label for="c${comp_concept_radio_num}">
${cand_cmc.description} <span style="color: #808080;"> (arity: ${cand_cmc.arity})</span>
(<a class="edit-comp-concept" data-comp-tag-id="${comp_tag_id}" data-comp-concept="${cand_cmc_id}" href="javascript:void(0);">edit</a>)
</label></span>`
      radios += item;
    }

    let cand_list = `<div class="keep">${radios}</div>`;
    let buttons = '<p><button id="assign-comp-concept">Assign</button> <button id="remove-comp-concept" type="button">Remove</button> <button id="new-comp-concept" type="button">New</button></p>';
    let form_elements = hidden + cand_list + buttons;

    let form_str = `<form id="form-${comp_tag_id}" method="POST">${form_elements}</form>`;

    // show the box
    let id_span = `ID: <span style="font-family: monospace;">${comp_tag_id}</span>`;
    let anno_box_content = `<p>${id_span}<hr color="#FFF">${form_str}</p>`;

    //console.debug(anno_box_content);

    // write the content
    let anno_box = $('#anno-box');
    anno_box.html(anno_box_content);

    // assign chosen concept
    $('button#assign-comp-concept').button();
    $('button#assign-comp-concept').on('click', function() {
      let form = anno_box.find(`#form-${escape_selector(comp_tag_id)}`);
      if($(`#form-${escape_selector(comp_tag_id)} input:checked`).length > 0) {
        localStorage['scroll_top'] = $(window).scrollTop();
        form.attr('action', '/_comp_concept');
        form.append(`<input type="hidden" name="cmcdict_edit_id" value="${cmcdict_edit_id}" />`);
        form.trigger("submit");
      } else {
        alert('Please select a concept.');
        return false;
      }
    });

    // remove assignment
    $('button#remove-comp-concept').button();
    $('button#remove-comp-concept').on('click', function() {
      let form = anno_box.find(`#form-${escape_selector(comp_tag_id)}`);
      form.attr('action', '/_remove_comp_concept');
      form.append(`<input type="hidden" name="cmcdict_edit_id" value="${cmcdict_edit_id}" />`)
      form.trigger("submit");
    });

    // enable concept dialogs
    new_comp_concept_button(comp_tag_id);
    $('a.edit-comp-concept').on('click', function() {
      let comp_tag_id = $(this).attr('data-comp-tag-id');
      let cmc_id = $(this).attr('data-comp-concept');

      if(comp_tag_id != undefined && cmc_id != undefined) {
        edit_comp_concept(cmc_id);
      }
    });

    // give colors at the same time
    $('msub').each(function() {
      give_color($(this));
    });
    $('msup').each(function() {
      give_color($(this));
    });
  }

  function show_anno_box(comp_tag_node: JQuery) {
    // highlight the selected element
    comp_tag_node.attr('style', 'border: dotted 2px #000000; padding: 10px;');

    // prepare idf and get candidate concepts
    let comp_concept_cand = get_comp_concept_cand(comp_tag_node);

    // draw the annotation box
    let comp_tag_id = comp_tag_node.attr('id');
    if(comp_concept_cand != undefined && comp_tag_id != undefined) {
      if(comp_concept_cand.length > 0) {
        draw_anno_box(comp_tag_id, comp_concept_cand);
      } else {
        let id_span = `ID: <span style="font-family: monospace;">${comp_tag_id}</span>`
        let no_concept = '<p>No compound concept is available.</p>'
        let button = '<p><button id="new-comp-concept" type="button">New</button></p>'
        let msg = `<p>${id_span}<hr color="#FFF">${no_concept}${button}</p>`
        $('#anno-box').html(msg);

        // enable the button
        new_comp_concept_button(comp_tag_id);
      }
    }
  }

  function new_comp_concept_button(comp_tag_id: string) {

    $('button#new-comp-concept').button();
    $('button#new-comp-concept').on('click', function() {
      
      const hex_primitives = get_primitive_hex_list($('#' + escape_selector(comp_tag_id)));
      const hex_primitives_string = hex_primitives.join(',');

      let concept_dialog = $('#comp-concept-dialog-template').clone();
      concept_dialog.attr('id', 'comp-concept-dialog');
      concept_dialog.removeClass('comp-concept-dialog');
      let form = concept_dialog.find('#comp-concept-form');
      form.attr('action', '/_new_comp_concept');

      concept_dialog.dialog({
        modal: true,
        title: 'New Compound Concept',
        width: 500,
        buttons: {
          'OK': function() {
            localStorage['scroll_top'] = $(window).scrollTop();
            form.append(`<input type="hidden" name="cmcdict_edit_id" value="${cmcdict_edit_id}" />`);
            form.append(`<input type="hidden" name="hex_primitives_string" value="${hex_primitives_string}" />`);
            form.trigger("submit");
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

  function edit_comp_concept(cmc_id: string) {
    let concept_dialog = $('#comp-concept-dialog-template').clone();
    concept_dialog.removeAttr('id');
    let form = concept_dialog.find('#comp-concept-form');
    form.attr('action', '/_update_comp_concept');

    // put the current values
    let concept = cmcdict[cmc_id];
    form.find('textarea').text(concept.description);
    form.find('input[name="arity"]').attr('value', concept.arity);

    let primitive_hex_string = concept.primitives_hex.join('')

    concept_dialog.dialog({
      modal: true,
      title: 'Edit Compound Concept',
      width: 500,
      buttons: {
        'OK': function() {
          localStorage['scroll_top'] = $(window).scrollTop();
          form.append(`<input type="hidden" name="cmcdict_edit_id" value="${cmcdict_edit_id}" />`)
          form.append(`<input type="hidden" name="hex-primitives" value="${primitive_hex_string}" />`);
          form.trigger("submit");
        },
        'Cancel': function() {
          $(this).dialog('close');
        }
      }
    });
  }

  $('msup, msub').on('click', function() {
    // if already selected, remove it
    let old_comp_tag_id = sessionStorage.getItem('comp_tag_id');
    if(old_comp_tag_id != undefined) {
      $('#' + escape_selector(old_comp_tag_id)).removeAttr('style');
    }

    // store id of the currently selected mi
    sessionStorage['comp_tag_id'] = $(this).attr('id');

    // show the annotation box
    show_anno_box($(this));

    // also update SoG highlight
    if(localStorage['option-limited-highlight'] == 'true') {
      miogatto_options.limited_highlight = true;
    }
    give_sog_highlight();
  });

  // keep position and sidebar content after submiting the form
  // This '$(window).scrollTop' seems redundant but somehow fixes the page position problems...
  $(window).scrollTop(localStorage['scroll_top']);
  let comp_tag_id = sessionStorage['comp_tag_id'];
  if(comp_tag_id != undefined) {
    show_anno_box($('#' + escape_selector(comp_tag_id)));
  }
});

// --------------------------
// SoG Registration
// --------------------------

function cast_dyn_word_selection_into_text_span(initial_id: string, offset:number): string {
  const last_dash_index = initial_id.lastIndexOf('-');
  const start_id_base = initial_id.slice(0, last_dash_index);
  const init_index = parseInt(initial_id.slice(last_dash_index+1),10);
  return start_id_base+'.'+(init_index+offset).toString(10)
}

function get_selection(): [
    string | undefined, string | undefined, HTMLElement | undefined] {
  // get selection
  let selected_text;
  if(window.getSelection) {
    selected_text = window.getSelection();
  } else if(document.getSelection) {
    selected_text = document.getSelection();
  }

  console.log("Selection Object:", selected_text);

  // return undefineds for unproper cases
  if(selected_text == undefined || selected_text.type != 'Range')
    return [undefined, undefined, undefined];

  let anchor_node = selected_text?.anchorNode?.parentElement;
  let anchor_offset = selected_text?.anchorOffset;
  let focus_node = selected_text?.focusNode?.parentElement;
  let focus_offset = selected_text?.focusOffset;
  if(anchor_node == undefined || focus_node == undefined)
    return [undefined, undefined, undefined];

  if($(anchor_node).parents('.main').length == 0 || $(focus_node).parents('.main').length == 0)
    return [undefined, undefined, undefined];

  // determine which (start|stop)_node
  let anchor_rect = anchor_node.getBoundingClientRect();
  let focus_rect = focus_node.getBoundingClientRect();

  let start_node, stop_node;
  let start_offset, stop_offset;
  if(anchor_rect.top < focus_rect.top) {
    [start_node, stop_node] = [anchor_node, focus_node];
    [start_offset, stop_offset] = [anchor_offset, focus_offset];
  } else if(anchor_rect.top == focus_rect.top && anchor_rect.left <= focus_rect.left) {
    [start_node, stop_node] = [anchor_node, focus_node];
    [start_offset, stop_offset] = [anchor_offset, focus_offset];
  } else {
    [start_node, stop_node] = [focus_node, anchor_node];
    [start_offset, stop_offset] = [focus_offset, anchor_offset];
  }

  // get start_id and stop_id
  let start_id, stop_id;

  // if(start_node.className == 'gd_word') {
  //   start_id= start_node.id;
  // } else if(start_node.nextElementSibling?.className == 'gd_word') {
  //   start_id = start_node.nextElementSibling.id;
  // } else {
  //   console.warn('Invalid span for a source of grounding');
  // }

  if(start_node.className == 'gd_text') {
    start_id = start_node.id+'.'+start_offset;
  } else if (start_node.className == 'dyn_gd_word') {
    start_id = cast_dyn_word_selection_into_text_span(start_node.id, start_offset)
  } else if (start_node.className == 'dyn_space' && start_node.nextElementSibling?.className == 'dyn_gd_word') {
    const sibling_node_id = start_node.nextElementSibling?.id
    start_id = cast_dyn_word_selection_into_text_span(sibling_node_id, 0)
  } else {
    console.warn('Invalid span for a source of grounding');
  }
  console.log("Start id:", start_id);

  // if(stop_node.className == 'gd_word') {
  //   stop_id = stop_node.id;
  // } else if(stop_node.previousElementSibling?.className == 'gd_word') {
  //   stop_id = stop_node.previousElementSibling.id;
  // } else {
  //   console.warn('Invalid span for a source of grounding');
  // }

  if(stop_node.className == 'gd_text') {
    stop_id = stop_node.id+'.'+stop_offset;
  } else if (stop_node.className == 'dyn_gd_word') {
    stop_id = cast_dyn_word_selection_into_text_span(stop_node.id, stop_offset)
  } else if (stop_node.className == 'dyn_space' && stop_node.previousElementSibling?.className == 'dyn_gd_word') {
    const sibling_node_id = stop_node.previousElementSibling?.id;
    const sibling_length = (stop_node.previousElementSibling?.textContent?? "").length
    stop_id = cast_dyn_word_selection_into_text_span(sibling_node_id, sibling_length);
  } else {
    console.warn('Invalid span for a source of grounding');
  }
  console.log("Stop id:", stop_id);

  return [start_id, stop_id, start_node];
}

$(function() {
  let page_x: number;
  let page_y: number;

  $(document).on('mouseup', function(e) {
    page_x = e.pageX;
    page_y = e.pageY;
  
    $('.sog-menu').css('display', 'none');
    let [start_id, stop_id, parent] = get_selection();

    console.log("Selection data:", [start_id, stop_id, parent])

    if(parent == undefined)
      return;

    // use jquery-ui
    $('.sog-menu input[type=submit]').button();

    // ----- Action SoG add -----
    let comp_tag_id = sessionStorage['comp_tag_id'];

    // show it only if an comp_tag with compound concept annotation selected
    if(comp_tag_id != undefined) {
      let concept = get_comp_concept($('#' + escape_selector(comp_tag_id)));
      if(concept != undefined) {
        $('.sog-menu').css({
          'left': page_x,
          'top' : page_y - 20
        }).fadeIn(200).css('display', 'flex');
      }
    }

    // show the current target
    let id_span = `<span style="font-family: monospace;">${comp_tag_id}</span>`;
    let add_menu_info = `<p>Selected compound tag id: ${id_span}</p>`;
    $('.sog-add-menu-info').html(add_menu_info);

    // the add function
    $('.sog-menu .sog-add').off('click');
    $('.sog-menu .sog-add').on('click',
    function() {
      $('.sog-menu').css('display', 'none');

      // post the data
      let post_data = {
        'cmcdict_edit_id': cmcdict_edit_id,
        'comp_tag_id': comp_tag_id,
        'start_id': start_id,
        'stop_id': stop_id
      };

      localStorage['scroll_top'] = $(window).scrollTop();

      $.when($.post('/_add_comp_sog', post_data))
      .done(function() {
        location.reload();
      })
      .fail(function() {
        console.error('Failed to POST _add_comp_sog!');
      });
    });

    // ----- SoG menu -----

    let sog_comp_tag_id = parent.getAttribute('data-sog-comp-tag-id');
    let sog_type_int = Number(parent.getAttribute('data-sog-type'));
    let sog_start_id = parent.getAttribute('data-sog-start');
    let sog_stop_id = parent.getAttribute('data-sog-stop');

    // Do not show sog-mod-menu when the sog is not highlighted.
    let is_sog_highlighted = true;
    if(miogatto_options.limited_highlight && comp_tag_id != undefined && sog_comp_tag_id != undefined) {
      if(comp_tag_id != sog_comp_tag_id) {
        is_sog_highlighted = false;
      }
    }

    // show it only if SoG is selected and highlighted.
    if(parent?.getAttribute('data-sog-comp-tag-id-sog-mi') != undefined && is_sog_highlighted) {
      $('.sog-mod-menu').css('display', 'inherit');
    } else {
      $('.sog-mod-menu').css('display', 'none');
    }

    let sog_type = 'unknown';
    if(sog_type_int == 0) {
      sog_type = 'declaration';
    } else if(sog_type_int == 1) {
      sog_type = 'definition';
    } else if(sog_type_int == 2) {
      sog_type = 'others';
    }
    let id_span_for_sog = `<span style="font-family: monospace;">${sog_comp_tag_id}</span>`;
    let mod_menu_info = `<p>Compound SoG for ${id_span_for_sog}<br/>Type: ${sog_type}</p>`;
    $('.sog-mod-menu-info').html(mod_menu_info);

    // ----- Action SoG change type -----
    $('.sog-menu .sog-type').off('click');
    $('.sog-menu .sog-type').on('click',
    function() {
      $('.sog-menu').css('display', 'none');

      // make sure parent exists
      // Note: the button is shown only if it exists
      if(parent == undefined)
        return;

      let sog_type_dialog = $('#sog-type-dialog-template').clone();
      sog_type_dialog.attr('id', 'sog-type-dialog');
      sog_type_dialog.removeClass('sog-type-dialog');

      let form = sog_type_dialog.find('#sog-type-form');
      form.attr('action', '/_change_comp_sog_type');

      sog_type_dialog.find(`input[value="${sog_type_int}"]`).prop('checked', true);

      sog_type_dialog.dialog({
        modal: true,
        title: 'Change Compound SoG Type',
        width: 200,
        buttons: {
          'OK': function() {
            localStorage['scroll_top'] = $(window).scrollTop();
            form.append(`<input type="hidden" name="cmcdict_edit_id" value="${cmcdict_edit_id}" />`)
            form.append(`<input type="hidden" name="comp_tag_id" value="${sog_comp_tag_id}" />`);
            form.append(`<input type="hidden" name="start_id" value="${sog_start_id}" />`);
            form.append(`<input type="hidden" name="stop_id" value="${sog_stop_id}" />`);
            form.trigger("submit");
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

    // ----- Action SoG delete -----
    $('.sog-menu .sog-del').off('click');
    $('.sog-menu .sog-del').on('click',
    function() {
      $('.sog-menu').css('display', 'none');

      // make sure parent exists
      // Note: the button is shown only if it exists
      if(parent == undefined)
        return;

      // post the data
      let post_data = {
        'cmcdict_edit_id': cmcdict_edit_id,
        'comp_tag_id': parent.getAttribute('data-sog-comp-tag-id'),
        'start_id': parent.getAttribute('data-sog-start'),
        'stop_id': parent.getAttribute('data-sog-stop'),
      };

      localStorage['scroll_top'] = $(window).scrollTop();

      $.when($.post('/_delete_comp_sog', post_data))
      .done(function() {
        location.reload();
      })
      .fail(function() {
        console.error('Failed to POST _delete_comp_sog!');
      })
    });
  });
});

// --------------------------
// background color
// --------------------------

// for the identifiers that have not been annotated
function show_border(target: JQuery) {
  let concept_cand = get_comp_concept_cand(target);
  if(target.data('compound-math-concept') == undefined && concept_cand != undefined)
    target.attr('mathbackground', '#D3D3D3');
}

$(function() {
  $('msup, msub').each(function() {
    show_border($(this));
  });
})

// --------------------------
// Keybord shortcuts
// --------------------------

function select_comp_concept(num: number) {
  let elem = $(`#c${num - 1}`);
  if(elem[0]) {
    $('input[name="comp-concept"]').prop('checked', false);
    $(`#c${num - 1}`).prop('checked', true);
  }
}

for (let i=1; i<10; i++) {
  $(document).on('keydown', function(event) {
    if(!$('#comp-concept-dialog')[0]) {
      if(event.key == i.toString(10)) {
        select_comp_concept(i);
      }
    }
  });
}

$(document).on('keydown', function(event) {
  if(event.key == 'Enter') {
    if(!$('#comp-concept-dialog')[0]) {
      $('#assign-comp-concept').trigger('click');
    }
  }
});

$(document).on('keydown', function(event) {
  if(event.key == 'j') {
    $('button#jump-to-next-unannotated-comp-tag').trigger('click');
  } else if (event.key == 'k') {
    $('button#jump-to-prev-unannotated-comp-tag').trigger('click');
  }
});


// --------------------------
// Utilities 
// --------------------------


let comp_tag_list: JQuery[] = [];
let comp_tag_id2index: {[comp_tag_id: string]: number} = {};

// Update comp_tag_list after loading html.
$(function() {
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

// Search the next unannotated comp_tag starting from start_index.
function get_next_unannotated_comp_tag_index(start_index: number): number | undefined {
  // Loop over comp_tag_list at most once.
  for (let count = 0; count < comp_tag_list.length; count++) {
    let index: number = (start_index + count) % comp_tag_list.length;

    let comp_tag: JQuery<any> = comp_tag_list[index];

    // Check if the mi is unannotated.
    if(get_comp_concept(comp_tag) == undefined){
      return index;
    }
  }
  // Return undefined if there is no unannotated mi.
  return undefined;
}

// Search the next unannotated comp_tag starting from start_index.
function get_prev_unannotated_comp_tag_index(start_index: number): number | undefined {
  // Loop over mi_list at most once.
  for (let count = comp_tag_list.length; count > 0; count--) {
    let index: number = (start_index + count) % comp_tag_list.length;

    let comp_tag: JQuery<any> = comp_tag_list[index];

    // Check if the mi is unannotated.
    if(get_comp_concept(comp_tag) == undefined){
      return index;
    }
  }
  // Return undefined if there is no unannotated mi.
  return undefined;
}

$(function() {
  $('button#jump-to-next-unannotated-comp-tag').button();
  $('button#jump-to-next-unannotated--comp-tag').on('click', function() {
    // First set this value so that the next mi is the first unannotated mi when mi_id is not stored.
    let current_index: number = comp_tag_list.length - 1

    // Use the stored mi_id if there is.
    if ((sessionStorage['comp_tag_id'] != undefined) && (sessionStorage['comp_tag_id'] in comp_tag_id2index)) {
      current_index = comp_tag_id2index[sessionStorage['comp_tag_id']];
    }

    // Start searching the next unannotated mi from start_index.
    let start_index: number = (current_index + 1) % comp_tag_list.length

    let next_index: number | undefined = get_next_unannotated_comp_tag_index(start_index);

    // Do nothing if there is no unannotated mi.
    if (next_index != undefined) {
      let next_unannotated_comp_tag = comp_tag_list[next_index]

      let jump_dest = next_unannotated_comp_tag?.offset()?.top;
      let window_height = $(window).height();
      if(jump_dest != undefined && window_height != undefined){
        $(window).scrollTop(jump_dest - (window_height / 2));

        // Click the next mi.
        next_unannotated_comp_tag.trigger('click');
      }
    }
  });

  $('button#jump-to-prev-unannotated-comp-tag').button();
  $('button#jump-to-prev-unannotated-comp-tag').on('click', function() {
    // First set this value so that the prev mi is the last unannotated mi when mi_id is not stored.
    let current_index: number = 0

    // Use the stored mi_id if there is.
    if ((sessionStorage['comp_tag_id'] != undefined) && (sessionStorage['comp_tag_id'] in comp_tag_id2index)) {
      current_index = comp_tag_id2index[sessionStorage['comp_tag_id']];
    }

    // Start searching the prev unannotated mi from start_index.
    let start_index: number = (current_index + comp_tag_list.length - 1) % comp_tag_list.length

    let prev_index: number | undefined = get_prev_unannotated_comp_tag_index(start_index);

    // Do nothing if there is no unannotated mi.
    if (prev_index != undefined) {
      let prev_unannotated_comp_tag = comp_tag_list[prev_index]

      let jump_dest = prev_unannotated_comp_tag?.offset()?.top;
      let window_height = $(window).height();
      if(jump_dest != undefined && window_height != undefined){
        $(window).scrollTop(jump_dest - (window_height / 2));

        // Click the prev mi.
        prev_unannotated_comp_tag.trigger('click');
      }
    }
  });

});

$(function() {
  $('button#back-to-selected-comp-tag').button();
  $('button#back-to-selected-comp-tag').on('click', function() {
    // Do nothing if no comp_tag is stored.
    if (sessionStorage['comp_tag_id'] != undefined) {
      let selected_comp_tag = $('#' + escape_selector(sessionStorage['comp_tag_id']))

      let jump_dest = selected_comp_tag?.offset()?.top;
      let window_height = $(window).height();
      if(jump_dest != undefined && window_height != undefined){
        $(window).scrollTop(jump_dest - (window_height / 2));
      }
    }

  });

});

$(function() {
  $('button#edit-cmcdict').button();
  $('button#edit-cmcdict').on('click', function() {
    let form = $('#edit-cmcdict-form');
    form.attr('action', '/edit_cmcdict');
    form.trigger("submit");
  });

});

$(function() {
  $('button#edit-concepts').button();
  $('button#edit-concepts').on('click', function() {
    let form = $('#edit-concepts-form');
    form.attr('action', '/');
    form.trigger("submit");
  });
});

// Set page position at the last
$(function() {
  $(window).scrollTop(localStorage['scroll_top']);
})
