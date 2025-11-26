// the MioGatto client. Logic for the sample navigation bar.
'use strict';


window.initializeSampleNavButtons = function()  {
    // Ensure jQuery UI button is initialized
    $('button#select-new-file').button();
    $('button#select-new-file').on('click', function() {
        const $listContainer = $('#file-selection-list');
        $listContainer.toggle(); // Show/hide the container
        console.log("Toggled file selection list.");

        // If showing, fetch the list
        if ($listContainer.is(':visible')) {
            $listContainer.html('Loading files...');

            console.log("Fetching sample IDs...");
            
            fetch('/list_sample_ids', {               // Your new endpoint from the previous answer
                method: 'GET',
            })
            .then(response => {
                // 1. Check HTTP Status (Handles 404, 500, etc.)
                if (!response.ok) {
                    throw new Error(`HTTP error! Status: ${response.status}`);
                }
                // 2. Parse the response body as JSON
                return response.json(); 
            })
            .then(data => {
                const available_ids: string[] = data.available_ids;
                console.log(available_ids);

                let html = '<h4>Select Sample:</h4><ul>';
                if (Array.isArray(available_ids)) {
                    available_ids.forEach(sample_id => {
                        // The URL should be your new server-side switch route
                        html += `<li><a href="/switch_to_sample/${sample_id}">${sample_id}</a></li>`;
                    });
                } else {
                    html += `<li>Error: Could not load file list.</li>`;
                }
                $listContainer.html(html + '</ul>');
            })
            .catch(() => {
                    $listContainer.html('<li>Network error fetching file list.</li>');
                });
        }
    });

    // Delegated handler for clicking a file link
    $('#file-selection-list').on('click', 'a', function(event) {
        // Prevent default navigation initially
        event.preventDefault(); 
        
        const targetUrl = $(this).attr('href');
        if (targetUrl) {
            // --- CRITICAL STEP: CLEAR SESSION STORAGE ---
            // Clear all session storage specific to the previous file
            sessionStorage.clear(); // Use removeItem() if you need to preserve other keys
            
            // 2. Perform the server-side file switch and redirect
            
            window.location.href = targetUrl;
        } else {
            // Optional: Handle a scenario where the link somehow had no href
            console.error("Clicked link element is missing the 'href' attribute.");
        }
    });
};
