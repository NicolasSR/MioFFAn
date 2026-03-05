// the MioFFAn client. Logic for the common navigation bar.
'use strict';


// --------------------------
// Navigation
// --------------------------

window.initializeNavButtons = function()  {
    $('button#edit-equations-of-interest').button();
    $('button#edit-equations-of-interest').on('click', function () {
        let form = $('#edit-equations-of-interest-form');
        form.attr('action', '/equations_of_interest_selector');
        form.trigger("submit");
    });

    $('button#edit-concepts').button();
    $('button#edit-concepts').on('click', function () {
        let form = $('#edit-concepts-form');
        form.attr('action', '/');
        form.trigger("submit");
    });

    $('button#create-concept-group').button();
    $('button#create-concept-group').on('click', function () {
        let form = $('#create-concept-group-form');
        form.attr('action', '/group_creator');
        form.trigger("submit");
    });

    $('button#edit-symbolic-code').button();
    $('button#edit-symbolic-code').on('click', function () {
        let form = $('#edit-symbolic-code-form');
        form.attr('action', '/symbolic-code-assigner');
        form.trigger("submit");
    });
    
    $('button#edit-mcdict').button();
    $('button#edit-mcdict').on('click', function () {
        let form = $('#edit-mcdict-form');
        form.attr('action', '/edit_mcdict');
        form.trigger("submit");
    });
};

