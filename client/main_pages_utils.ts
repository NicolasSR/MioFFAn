import {Concept, CompoundConcept, Source, CompoundSource, hex2rgb,
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

    console.log(word)
    console.log(positionIndex)

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
        console.log('Word end', wordEndIndex)
        console.log('New match', nextMatch.index)
        console.log('Text', t)
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

export function sog_to_sog_nodes_for_removal(s: Source | CompoundSource) {
    // get SoG nodes
    // Note: this code is somehow very tricky but it works
    const start_last_dot_index = s.start_id.lastIndexOf('.');
    const stop_last_dot_index = s.stop_id.lastIndexOf('.');
    let start_element_id = s.start_id.slice(0, start_last_dot_index);
    let stop_element_id = s.stop_id.slice(0, stop_last_dot_index);
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

    return sog_nodes
}

export function sog_to_sog_nodes_for_addition(s: Source | CompoundSource) {
    // get SoG nodes
    // Note: this code is somehow very tricky but it works
    const start_last_dot_index = s.start_id.lastIndexOf('.');
    const stop_last_dot_index = s.stop_id.lastIndexOf('.');
    let start_element_id = s.start_id.slice(0, start_last_dot_index);
    let start_offset = parseInt(s.start_id.slice(start_last_dot_index +1), 10);
    let stop_element_id = s.stop_id.slice(0, stop_last_dot_index);
    let stop_offset = parseInt(s.stop_id.slice(stop_last_dot_index +1), 10);
    // let sog_nodes_root, sog_nodes;
    let sog_nodes;
    // if (s.start_id == s.stop_id) {
        // sog_nodes = $('#' + escape_selector(s.start_id));
    if (start_element_id == stop_element_id) {
        // sog_nodes_root = $('#' + escape_selector(start_element_id));
        const start_node_element = $('#' + escape_selector(start_element_id))[0];
        let start_span_id = '';
        let stop_span_id = '';

        if (start_node_element.className == "gd_text"){
            if (!hasWordMap(start_node_element)) {
                divide_and_index_text_span(start_node_element);
            }
            start_span_id = get_word_id_by_index(start_node_element, start_offset);
            stop_span_id = get_word_id_by_index(start_node_element, stop_offset);
        } else {
            throw new Error("Grounding text must start and finish in 'gd_text' class");
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
            let start_span_node = $('#' + escape_selector(start_span_id));
            let stop_span_node = $('#' + escape_selector(stop_span_id));
            sog_nodes = start_span_node.nextUntil('#' + escape_selector(stop_span_id)).addBack().add(stop_span_node);
        }

    } else {
        // let start_node = $('#' + escape_selector(s.start_id));
        // let stop_node = $('#' + escape_selector(s.stop_id));
        let start_node = $('#' + escape_selector(start_element_id));
        let stop_node = $('#' + escape_selector(stop_element_id));

        const start_node_element = start_node[0];
        const stop_node_element = stop_node[0];
        let start_span_id = '';
        let stop_span_id = '';

        if (start_node_element.className == "gd_text"){
            if (!hasWordMap(start_node_element)) {
                divide_and_index_text_span(start_node_element);
            }
            start_span_id = get_word_id_by_index(start_node_element, start_offset);
        } else {
            throw new Error("Grounding text must start and finish in 'gd_text' class");
        }

        if (stop_node_element.className == "gd_text"){
            if (!hasWordMap(stop_node_element)) {
                divide_and_index_text_span(stop_node_element);
            }
            stop_span_id = get_word_id_by_index(stop_node_element, stop_offset);
        } else {
            throw new Error("Grounding text must start and finish in 'gd_text' class");
        }

        if (start_span_id == stop_span_id) {
            sog_nodes = $('#' + escape_selector(start_span_id));
        } else {
            let start_span_node = $('#' + escape_selector(start_span_id));
            let stop_span_node = $('#' + escape_selector(stop_span_id));
            sog_nodes = start_span_node.nextAll().addBack();
            sog_nodes = sog_nodes.add(stop_node.children().first().nextUntil('#' + escape_selector(stop_span_id)).addBack()).add(stop_span_node);
            sog_nodes = sog_nodes.add(start_node.nextUntil('#' + escape_selector(stop_element_id)));
        }
        // sog_nodes = start_node.nextUntil('#' + escape_selector(stop_element_id)).addBack().add(stop_node);
    }

    return sog_nodes
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

  console.log("Anchor top, left")
  console.log(anchor_rect.top)
  console.log(anchor_rect.left)
  console.log("Focus top, left")
  console.log(focus_rect.top)
  console.log(focus_rect.left)

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