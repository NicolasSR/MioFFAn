import {Concept, CompoundConcept, Source, CompoundSource, hex2rgb,
  get_comp_concept, get_comp_concept_id, cmcdict_edit_id, comp_sog, escape_selector, get_primitive_hex_list,
  cmcdict, get_comp_concept_cand, dfs_comp_tags} from "./common" ;

// --------------------------
// Interfaces
// --------------------------

// Define an interface to extend HTMLElement/HTMLSpanElement with our custom map property
export interface WordIndexedSpan extends HTMLSpanElement {
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

