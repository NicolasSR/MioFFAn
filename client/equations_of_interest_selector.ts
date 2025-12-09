// the MioGatto client
'use strict';

import { post } from "jquery";
import {COMPOUND_CONCEPT_TAGS, escape_selector, eoi_dict} from "./common" ;

// --------------------------
// Get list of tags used as mathematical identifiers ffrom configuration json
// ------------------------

const compound_tags_selector = COMPOUND_CONCEPT_TAGS.join(', ');

// --------------------------
// Highlight EoIs
// --------------------------

$(function() {
  sessionStorage['equation_id'] = undefined;
  give_eoi_highlight();
});

function give_eoi_highlight(){
  for(let eoi_id in eoi_dict) {
    let eoi_query = $('#' + escape_selector(eoi_id));
    eoi_query.css('background-color', `rgba(#dcf9fa,0.3)`);
  }
}

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
// Annotation box
// --------------------------

function get_equation_from_math(math_node: JQuery) {
  return math_node.closest('.formula')
}

function remove_selection_box(equation_id: string) {
  let equation_query = $('#'+equation_id)
  equation_query.removeAttr('style');
}

$(function() {
  // show the box for annotation in the sidebar 
  function show_anno_box(current_equation: JQuery) {
    // highlight the selected element
    let current_equation_id = current_equation.attr('id')
    if (current_equation_id != undefined) {
      sessionStorage["equation_id"] = current_equation_id

      current_equation.attr('style', 'border: dotted 2px #000000; padding: 10px;');
      let hidden = `<input type="hidden" name="equation_id" value="${current_equation_id}" />`;

      let anno_box = $('#anno-box')

      if (current_equation_id in eoi_dict) {
        let button_remove = '<p><button id="remove-eoi">Remove EoI</button>';
        let form_remove = `<form id="form-remove-eoi" method="POST">${hidden}</form>`;
        anno_box.html(button_remove+form_remove)
        $('button#remove-eoi').button();
        $('button#remove-eoi').on('click', function() {
          let form = anno_box.find(`#form-remove-eoi`);;
          form.attr('action', '/_remove_eoi');
          form.trigger("submit");
        });
      } else {
        let button_add = '<p><button id="add-eoi">Add EoI</button>';
        let form_add = `<form id="form-add-eoi" method="POST">${hidden}</form>`;
        anno_box.html(button_add+form_add)
        $('button#add-eoi').button();
        $('button#add-eoi').on('click', function() {
          let form = anno_box.find(`#form-add-eoi`);
          form.attr('action', '/_add_eoi');
          form.trigger("submit");
        });
      }
    } else {
      console.warn("Selected equation does not have an ID")
    }
  }

  $('math').on('click', function() {
    // if already selected, remove it
    let equation = get_equation_from_math($(this));
    remove_selection_box(sessionStorage['equation_id']);
    show_anno_box(equation);
    give_eoi_highlight();
    
  });

  // keep position and sidebar content after submiting the form
  // This '$(window).scrollTop' seems redundant but somehow fixes the page position problems...
  $(window).scrollTop(localStorage['scroll_top']);
  let equation_id = sessionStorage['equation_id'];
  if(equation_id != undefined) {
    show_anno_box($('#' + escape_selector(equation_id)));
  }
});

// --------------------------
// background color
// --------------------------

// for the equations that have not been added in eoi
function show_border(equation: JQuery) {
  let equation_id = equation.attr('id')
  if (equation_id != undefined) {
    if (equation_id in eoi_dict != true) {
      equation.attr('mathbackground', '#D3D3D3');
    }
  }
}

$(function() {
  $('math').each(function() {
    let equation = get_equation_from_math($(this))
    show_border(equation);
  });
})