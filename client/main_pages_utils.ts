import {Concept, CompoundConcept, Source, CompoundSource, hex2rgb, eoi_list,
  get_comp_concept, get_comp_concept_id, cmcdict_edit_id, comp_sog, escape_selector, get_primitive_hex_list,
  cmcdict, get_comp_concept_cand, dfs_comp_tags} from "./common" ;

// --------------------------
// Interfaces
// --------------------------

// Define an interface to extend HTMLElement/HTMLSpanElement with our custom map property
interface WordIndexedSpan extends HTMLSpanElement {
    wordMap?: Map<number, string>;
}

// --------------------------
// Internal utilities
// --------------------------

function hasWordMap(element: HTMLSpanElement): element is WordIndexedSpan {
  const potentialWordMapElement = element as WordIndexedSpan;
  // 2. Use the 'in' operator to check if the property exists on the object
  // This is a type guard that also tells TypeScript the element is WordIndexedSpan
  return 'wordMap' in potentialWordMapElement;
}

function divide_and_index_text_span(e: WordIndexedSpan): void {
  let t = e.textContent;
  if (!t) {
    console.warn("Parent element has no text content to split.");
    throw new Error("Parent element has no text content to split.");
  }

  // Initialize the map on the parent element
  e.wordMap = new Map<number, string>();

  // Clear the original content
  e.textContent = '';

  // The regular expression \S+ matches one or more non-whitespace characters (a "word").
  // The 'g' flag ensures it finds all matches.
  const wordRegex = /\S+/g;
  let match: RegExpExecArray | null;

  // 3. Iterate and create a new span for each word
  while ((match = wordRegex.exec(t)) !== null) {
    const word = match[0];

    // The index is the position of the first character of the word in the original string.
    const positionIndex = match.index;

    // Create the new span element
    const wordSpan = document.createElement('span');

    // Set a unique ID for the new span
    // Combining the parent ID (if it exists) and the index/word for uniqueness
    const uniqueId = `${e.id || 'word'}-${positionIndex}`;
    wordSpan.id = uniqueId;

    // Set the text content (the word)
    wordSpan.textContent = word;

    // Optional: Add a class for styling/identification
    wordSpan.className = 'dyn_gd_word';

    // Store the mapping: Character Position -> Child Span Node
    e.wordMap.set(positionIndex, wordSpan.id);
    
    // 4. Append the new span to the original parent element
    e.appendChild(wordSpan);

    // 5. Add the whitespace that followed the word
    // Find the index where the current word ends
    const wordEndIndex = positionIndex + word.length;

    // Find the start of the next non-whitespace character (the next word)
    wordRegex.lastIndex = wordEndIndex; // Start searching for the next word from here
    const nextMatch = wordRegex.exec(t);
    
    let spaceText = '';
    if (nextMatch) {
        // If there's a next word, the space is the substring between the current word's end 
        // and the next word's start
        spaceText = t.substring(wordEndIndex, nextMatch.index);
    } else {
        // If this is the last word, the space is any trailing whitespace
        spaceText = t.substring(wordEndIndex);
    }
    
    if (spaceText.length > 0) {
        let spaceNode = document.createElement('span');
        spaceNode.textContent = spaceText;
        spaceNode.className = "dyn_space";
        e.appendChild(spaceNode);
    }

    // Reset the regex index for the next loop iteration, which will restart
    // from the last word found's end position due to the while condition's exec call.
    // We set lastIndex for the space logic, but the while loop's exec call
    // will automatically use the updated lastIndex from the *previous* call.
    // We must ensure 'match' is used for the *current* word processing.
    if (nextMatch) {
        wordRegex.lastIndex = nextMatch.index; // Ensure the next exec starts correctly
    } else {
        // No more words, stop the loop after this iteration
        break; 
    }
  };
}


function get_word_id_by_index(e: WordIndexedSpan, char_index: number): string {
    const wordMap = e.wordMap;

    if (!wordMap || wordMap.size === 0) {
        throw new Error("Word map not found or is empty.");
    }

    // 1. Check for an exact match (if the index is the start of a word)
    if (wordMap.has(char_index)) {
        return wordMap.get(char_index)!; // '!' assertion is safe due to .has() check
    }

    // 2. Search for the closest preceding index (if the index is within a word)

    // Get all starting indices (keys) and sort them descending
    const sortedIndices = Array.from(wordMap.keys()).sort((a, b) => b - a);

    // Iterate through the sorted indices to find the first one that is <= charIndex
    for (const startIndex of sortedIndices) {
        if (startIndex < char_index) {
            return wordMap.get(startIndex)!;
            // Check if the character index is still within the bounds of this word
            // We use textContent.length to find the word's end position
            // if (startIndex + node.textContent!.length > char_index) {
            //     return node;
            // }
        }
    }

    // If no word is found (e.g., index is before the first word)
    throw new Error("No corresponding word was found by index");
}

function cast_dyn_word_selection_into_text_span(initial_id: string, offset:number): string {
  const last_dash_index = initial_id.lastIndexOf('-');
  const start_id_base = initial_id.slice(0, last_dash_index);
  const init_index = parseInt(initial_id.slice(last_dash_index+1),10);
  return start_id_base+'.'+(init_index+offset).toString(10)
}

// --------------------------
// Exported utilities
// --------------------------

export function give_eoi_borders() {
  for(let eoi_id of eoi_list.eoi_list) {
    let eoi_query = $('#'+eoi_id);
    eoi_query.attr('style', 'border: solid 4px #dcf9fa; padding: 10px;')
  }
}

export function highlight_sog_nodes(concept: Concept | CompoundConcept | undefined, sog_nodes: JQuery, sog: Source | CompoundSource, show_definition: boolean) {
    if (concept == undefined || concept.color == undefined) {
        // red underline if concept is unassigned
        sog_nodes.css('border-bottom', 'solid 2px #FF0000');
        } else {
        // highlight it!
        sog_nodes.css('background-color', `rgba(${hex2rgb(concept.color).join()},0.3)`);
        if(show_definition && sog.type == 1) {
            sog_nodes.css('border-bottom', 'solid 3px');
        }
    }
}

export function remove_highlight(sog_nodes: JQuery) {
    sog_nodes.css('border-bottom', '');
    sog_nodes.css('background-color', '');
}

// export function sog_to_sog_nodes_for_removal(s: Source | CompoundSource) {
//     // get SoG nodes
//     // Note: this code is somehow very tricky but it works
//     const start_last_dot_index = s.start_id.lastIndexOf('.');
//     const stop_last_dot_index = s.stop_id.lastIndexOf('.');
//     let start_element_id = s.start_id.slice(0, start_last_dot_index);
//     let stop_element_id = s.stop_id.slice(0, stop_last_dot_index);
//     let sog_nodes;

//     // if (s.start_id == s.stop_id) {
//         // sog_nodes = $('#' + escape_selector(s.start_id));
//     if (start_element_id == stop_element_id) {
//         sog_nodes = $('#' + escape_selector(start_element_id));
//     } else {
//         // let start_node = $('#' + escape_selector(s.start_id));
//         // let stop_node = $('#' + escape_selector(s.stop_id));
//         let start_node = $('#' + escape_selector(start_element_id));
//         let stop_node = $('#' + escape_selector(stop_element_id));

//         // sog_nodes = start_node.nextUntil('#' + escape_selector(s.stop_id)).addBack().add(stop_node);
//         sog_nodes = start_node.nextUntil('#' + escape_selector(stop_element_id)).addBack().add(stop_node);
//     }

//     return sog_nodes
// }

export function sog_to_sog_nodes_for_addition(s: Source | CompoundSource) {
    // get SoG nodes
    // Note: this code is somehow very tricky but it works

    const start_last_dot_index = s.start_id.lastIndexOf('-');
    const stop_last_dot_index = s.stop_id.lastIndexOf('-');
    const start_node_parent_id = s.start_id.slice(0, start_last_dot_index);
    const stop_node_parent_id = s.stop_id.slice(0, stop_last_dot_index);

    const start_node_parent = $('#' + escape_selector(start_node_parent_id))[0]
    const stop_node_parent = $('#' + escape_selector(stop_node_parent_id))[0]

    if (!hasWordMap(start_node_parent)) {
        divide_and_index_text_span(start_node_parent);
    }
    if (!hasWordMap(stop_node_parent)) {
        divide_and_index_text_span(stop_node_parent);
    }

    const start_node_query = $('#' + escape_selector(s.start_id))
    const stop_node_query = $('#' + escape_selector(s.stop_id))
    const start_node = start_node_query[0];
    const stop_node = stop_node_query[0];

    let sog_nodes_query;

    if (start_node == stop_node) {
        sog_nodes_query = start_node_query;
    } else if (start_node.parentNode == stop_node.parentNode) {
        sog_nodes_query = start_node_query.nextUntil(stop_node_query).addBack().add(stop_node_query);
    } else {
        sog_nodes_query = start_node_query.nextAll().addBack();
        sog_nodes_query = sog_nodes_query.add(stop_node_query.parent().children().first().nextUntil(stop_node_query).addBack()).add(stop_node_query);
        sog_nodes_query = sog_nodes_query.add(start_node_query.parent().nextUntil(stop_node_query.parent()));
    }

    return sog_nodes_query;
}

export function get_selection(): [
    string | undefined, string | undefined, HTMLElement | undefined] {
    // get selection
    let selected_text;
    if(window.getSelection) {
        selected_text = window.getSelection();
    } else if(document.getSelection) {
        selected_text = document.getSelection();
    }

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

    let anchor_id: string = '';
    let focus_id: string = '';
    if(anchor_node.className == 'gd_text') {
        anchor_id = anchor_node.id+'.'+anchor_offset;
    } else if (anchor_node.className == 'dyn_gd_word') {
        anchor_id = cast_dyn_word_selection_into_text_span(anchor_node.id, anchor_offset)
    } else if (anchor_node.className == 'dyn_space' && anchor_node.nextElementSibling?.className == 'dyn_gd_word') {
        // We assume anchor node will generally be the starting one
        const sibling_node_id = anchor_node.nextElementSibling?.id;
        const sibling_length = (anchor_node.nextElementSibling?.textContent?? "").length
        anchor_id = cast_dyn_word_selection_into_text_span(sibling_node_id, sibling_length);
    } else {
        console.warn('Invalid span for a source of grounding');
    }
    if(focus_node.className == 'gd_text') {
        focus_id = focus_node.id+'.'+focus_offset;
    } else if (focus_node.className == 'dyn_gd_word') {
        focus_id = cast_dyn_word_selection_into_text_span(focus_node.id, focus_offset)
    } else if (focus_node.className == 'dyn_space' && focus_node.previousElementSibling?.className == 'dyn_gd_word') {
        // We assume focus node will generally be the ending one
        const sibling_node_id = focus_node.previousElementSibling?.id;
        const sibling_length = (focus_node.previousElementSibling?.textContent?? "").length
        focus_id = cast_dyn_word_selection_into_text_span(sibling_node_id, sibling_length);
    } else {
        console.warn('Invalid span for a source of grounding');
    }
    
    return [anchor_id, focus_id, anchor_node];
}

export function handle_selection_ends(anchor_id: string, focus_id: string) {

    // In this fucntion we consider "global" to be referring to spans of type gd_text (parent),
    // and "local to be referring to spans of type dyn_gd_word"

    const anchor_last_dot_index = anchor_id.lastIndexOf('.');
    const focus_last_dot_index = focus_id.lastIndexOf('.');
    let anchor_global_id = anchor_id.slice(0, anchor_last_dot_index);
    let anchor_global_offset = parseInt(anchor_id.slice(anchor_last_dot_index +1), 10);
    let focus_global_id = focus_id.slice(0, focus_last_dot_index);
    let focus_global_offset = parseInt(focus_id.slice(focus_last_dot_index +1), 10);

    let anchor_global_node = $('#' + escape_selector(anchor_global_id))[0];
    let focus_global_node = $('#' + escape_selector(focus_global_id))[0];

    let anchor_local_id: string;
    let focus_local_id: string;
    if (anchor_global_node.className == "gd_text"){
        if (!hasWordMap(anchor_global_node)) {
            divide_and_index_text_span(anchor_global_node);
        }
        anchor_local_id = get_word_id_by_index(anchor_global_node, anchor_global_offset);
    } else {
        throw new Error("Grounding text must start and finish in 'gd_text' class");
    }
    if (focus_global_node.className == "gd_text"){
        if (!hasWordMap(focus_global_node)) {
            divide_and_index_text_span(focus_global_node);
        }
        focus_local_id = get_word_id_by_index(focus_global_node, focus_global_offset);
    } else {
        throw new Error("Grounding text must start and finish in 'gd_text' class");
    }

    return [anchor_local_id, focus_local_id]

}

export function reorder_anchor_and_focus_ids(anchor_id: string, focus_id: string) {
    let anchor_node = $('#' + escape_selector(anchor_id));
    let focus_node = $('#' + escape_selector(focus_id));

    let start_id: string = '';
    let stop_id: string = '';
    if (anchor_node != undefined && focus_node != undefined) {
        let anchor_top = anchor_node?.offset()?.top ?? 0;
        let anchor_left = anchor_node?.offset()?.left ?? 0;
        let focus_top = focus_node?.offset()?.top ?? 0;
        let focus_left = focus_node?.offset()?.left ?? 0;
        
        if(anchor_top < focus_top) {
            [start_id, stop_id] = [anchor_id, focus_id];
        } else if(anchor_top == focus_top && anchor_left <= focus_left) {
            [start_id, stop_id] = [anchor_id, focus_id];
        } else {
            [start_id, stop_id] = [focus_id, anchor_id];
        }

    } else {
        console.error('Anchor or focus node not found');
    }

    return [start_id, focus_id];

}

//   // determine which (start|stop)_node
//   let anchor_rect = anchor_node.getBoundingClientRect();
//   let focus_rect = focus_node.getBoundingClientRect();

//   console.log("Anchor top, left")
//   console.log(anchor_rect.top)
//   console.log(anchor_rect.left)
//   console.log("Focus top, left")
//   console.log(focus_rect.top)
//   console.log(focus_rect.left)

//   let start_node, stop_node;
//   let start_offset, stop_offset;
//   if(anchor_rect.top < focus_rect.top) {
//     [start_node, stop_node] = [anchor_node, focus_node];
//     [start_offset, stop_offset] = [anchor_offset, focus_offset];
//   } else if(anchor_rect.top == focus_rect.top && anchor_rect.left <= focus_rect.left) {
//     [start_node, stop_node] = [anchor_node, focus_node];
//     [start_offset, stop_offset] = [anchor_offset, focus_offset];
//   } else {
//     [start_node, stop_node] = [focus_node, anchor_node];
//     [start_offset, stop_offset] = [focus_offset, anchor_offset];
//   }

//   // get start_id and stop_id
//   let start_id, stop_id;

//   // if(start_node.className == 'gd_word') {
//   //   start_id= start_node.id;
//   // } else if(start_node.nextElementSibling?.className == 'gd_word') {
//   //   start_id = start_node.nextElementSibling.id;
//   // } else {
//   //   console.warn('Invalid span for a source of grounding');
//   // }

  

//   // if(stop_node.className == 'gd_word') {
//   //   stop_id = stop_node.id;
//   // } else if(stop_node.previousElementSibling?.className == 'gd_word') {
//   //   stop_id = stop_node.previousElementSibling.id;
//   // } else {
//   //   console.warn('Invalid span for a source of grounding');
//   // }

//   if(stop_node.className == 'gd_text') {
//     stop_id = stop_node.id+'.'+stop_offset;
//   } else if (stop_node.className == 'dyn_gd_word') {
//     stop_id = cast_dyn_word_selection_into_text_span(stop_node.id, stop_offset)
//   } else if (stop_node.className == 'dyn_space' && stop_node.previousElementSibling?.className == 'dyn_gd_word') {
//     const sibling_node_id = stop_node.previousElementSibling?.id;
//     const sibling_length = (stop_node.previousElementSibling?.textContent?? "").length
//     stop_id = cast_dyn_word_selection_into_text_span(sibling_node_id, sibling_length);
//   } else {
//     console.warn('Invalid span for a source of grounding');
//   }
//   console.log("Stop id:", stop_id);

//   return [start_id, stop_id, start_node];
// }