/**
##
# Copyright (c) 2013-2015 Apple Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
##
*/

// Globals
var gSession = null;
var gViewController = null;

// Page load
$(function() {

	$("#progressbar").progressbar({
		value : false
	});
	showLoading(true);

    var params = {};
    var ps = window.location.search.split(/\?|&/);
    for (var i = 0; i < ps.length; i++) {
          if (ps[i]) {
                var p = ps[i].split(/=/);
                params[p[0]] = p[1];
          }
    }

    // Setup CalDAV session
	gSession = new CalDAVSession(params.user);
	gSession.init(function() {
		$("#title").text($("#title").text() + " for User: " + gSession.currentPrincipal.cn);
		gViewController.refreshed();
	});

	gViewController = new ViewController(gSession);
});

function showLoading(visible) {
	if (visible) {
		$("#progressbar").progressbar("enable");
		$("#loading").show();
	} else {
		$("#progressbar").progressbar("disable");
		$("#loading").hide();
	}
}

// Handles all the view interactions
ViewController = function(session) {
	this.session = session;
	this.ownedPolls = new PollList($("#sidebar-owned"), $("#sidebar-new-poll-count"));
	this.voterPolls = new PollList($("#sidebar-voter"), $("#sidebar-vote-poll-count"));
	this.activePoll = null;
	this.isNewPoll = null;

	this.init();
}

// Setup all the parts of the view
ViewController.prototype.init = function() {
	// Setup title area

	var view = this;

	// Setup sidebar UI widgets
	$("#sidebar").accordion({
		heightStyle : "content"
	});
	$("#sidebar-owned").menu({
		select : function(event, ui) {
			view.clickSelectPoll(event, ui, true);
		}
	});
	$("#sidebar-new-poll").button({
		icons : {
			primary : "ui-icon-plusthick"
		}
	}).click(function() {
		view.clickAddPoll();
	});

	$("#sidebar-voter").menu({
		select : function(event, ui) {
			view.clickSelectPoll(event, ui, false);
		}
	});

	$("#refresh-btn").button({
		icons : {
			primary : "ui-icon-refresh"
		}
	}).click(function() {
		view.clickRefresh();
	});


	// Detail Panel
	this.editSetVisible(false);
	$("#editpoll-title-edit").focus(function() {
		$(this).select();
	});
	$("#editpoll-tabs").tabs({
		beforeActivate : function(event, ui) {
			view.showResults(event, ui);
		}
	});
	$("#editpoll-save").button({
		icons : {
			primary : "ui-icon-check"
		}
	}).click(function() {
		view.clickPollSave();
	});
	$("#editpoll-cancel").button({
		icons : {
			primary : "ui-icon-close"
		}
	}).click(function() {
		view.clickPollCancel();
	});
	$("#editpoll-done").button({
		icons : {
			primary : "ui-icon-arrowreturnthick-1-w"
		}
	}).click(function() {
		view.clickPollCancel();
	});
	$("#editpoll-delete").button({
		icons : {
			primary : "ui-icon-trash"
		}
	}).click(function() {
		view.clickPollDelete();
	});
	$("#editpoll-autofill").button({
		icons : {
			primary : "ui-icon-gear"
		}
	}).click(function() {
		view.clickPollAutofill();
	});
	$("#editpoll-addevent").button({
		icons : {
			primary : "ui-icon-plus"
		}
	}).click(function() {
		view.clickAddEvent();
	});
	$("#editpoll-addvoter").button({
		icons : {
			primary : "ui-icon-plus"
		}
	}).click(function() {
		view.clickAddVoter();
	});
	
	$("#editpoll-autofill").hide();
	$("#response-key").hide();
	$("#response-menu").menu();
}

// Add a poll to the UI
ViewController.prototype.addPoll = function(poll) {
	if (poll.owned) {
		this.ownedPolls.addPoll(poll)			
	} else {
		this.voterPolls.addPoll(poll)			
	}
}

// Switching away from active poll
ViewController.prototype.aboutToClosePoll = function() {
	if (this.activePoll && this.activePoll.editing_poll.changed()) {
		alert("Save or cancel the current poll changes first");
		return false;
	} else {
		return true;
	}
}

// Refresh the side bar - try to preserve currently selected item
ViewController.prototype.clickRefresh = function() {
	if (!this.aboutToClosePoll()) {
		return;
	}

	var currentUID = this.activePoll ? this.activePoll.editing_poll.uid() : null;
	var active_tab = $("#editpoll-tabs").tabs("option", "active");
	if (this.activePoll) {
		this.clickPollCancel();
	}
	showLoading(true);
	this.ownedPolls.clearPolls();
	this.voterPolls.clearPolls();
	var this_view = this;
	this.session.currentPrincipal.refresh(function() {
		this_view.refreshed();
		if (currentUID) {
			this_view.selectPollByUID(currentUID);
			$("#editpoll-tabs").tabs("option", "active", active_tab);
			if (active_tab == 2) {
				this.activePoll.buildResults();
			}
		}
	});
}

// Add poll button clicked
ViewController.prototype.clickAddPoll = function() {
	if (!this.aboutToClosePoll()) {
		return;
	}

	// Make sure edit panel is visible
	this.activatePoll(new Poll(CalendarResource.newPoll("New Poll")));
	this.isNewPoll = true;
	$("#editpoll-title-edit").focus();
}

// A poll was selected
ViewController.prototype.clickSelectPoll = function(event, ui, owner) {
	if (!this.aboutToClosePoll()) {
		return;
	}

	this.selectPoll(ui.item.index(), owner);
}

// Select a poll from the list based on its UID
ViewController.prototype.selectPollByUID = function(uid) {
	var result = this.ownedPolls.indexOfPollUID(uid);
	if (result !== null) {
		this.selectPoll(result, true);
		return;
	}
	result = this.voterPolls.indexOfPollUID(uid);
	if (result !== null) {
		this.selectPoll(result, false);
		return;
	}
}

//A poll was selected
ViewController.prototype.selectPoll = function(index, owner) {

	// Make sure edit panel is visible
	this.activatePoll(owner ? this.ownedPolls.polls[index] : this.voterPolls.polls[index]);
	if (owner) {
		$("#editpoll-title-edit").focus();
	}
}

// Activate specified poll
ViewController.prototype.activatePoll = function(poll) {
	this.activePoll = poll;
	this.activePoll.setPanel();
	this.isNewPoll = false;
	this.editSetVisible(true);
}

// Save button clicked
ViewController.prototype.clickPollSave = function() {

	// TODO: Actually save it to the server

	this.activePoll.getPanel();
	if (this.isNewPoll) {
		this.ownedPolls.newPoll(this.activePoll);
	} else {
		this.activePoll.list.changePoll(this.activePoll);
	}
}

// Cancel button clicked
ViewController.prototype.clickPollCancel = function() {

	// Make sure edit panel is visible
	this.activePoll.closed();
	this.activePoll = null;
	this.isNewPoll = null;
	this.editSetVisible(false);
}

// Delete button clicked
ViewController.prototype.clickPollDelete = function() {

	// TODO: Actually delete it on the server

	this.activePoll.list.removePoll(this.activePoll);

	// Make sure edit panel is visible
	this.activePoll = null;
	this.isNewPoll = null;
	this.editSetVisible(false);
}

// Autofill button clicked
ViewController.prototype.clickPollAutofill = function() {
	this.activePoll.autoFill();
}

// Add event button clicked
ViewController.prototype.clickAddEvent = function() {
	this.activePoll.addEvent();
}

// Add voter button clicked
ViewController.prototype.clickAddVoter = function() {
	var panel = this.activePoll.addVoter();
	panel.find(".voter-address").focus();
}

// Toggle display of poll details
ViewController.prototype.editSetVisible = function(visible) {

	if (visible) {
		
		if (this.isNewPoll) {
			$("#editpoll-delete").hide();
			$("#editpoll-tabs").tabs("disable", 2);
		} else {
			$("#editpoll-delete").show();
			$("#editpoll-tabs").tabs("enable", 2);
		}
		if (this.activePoll.owned && this.activePoll.resource.object.mainComponent().editable()) {
			$("#editpoll-title-panel").hide();
			$("#editpoll-organizer-panel").hide();
			$("#editpoll-status-panel").hide();
			$("#editpoll-title-edit-panel").show();
			$("#editpoll-tabs").tabs("enable", 0);
			$("#editpoll-tabs").tabs("enable", 1);
			$("#editpoll-tabs").tabs("option", "active", 0);
			$("#response-key").hide();
		} else {
			$("#editpoll-title-edit-panel").hide();
			$("#editpoll-title-panel").show();
			$("#editpoll-organizer-panel").show();
			$("#editpoll-status-panel").show();
			$("#editpoll-tabs").tabs("option", "active", 2);
			$("#editpoll-tabs").tabs("disable", 0);
			$("#editpoll-tabs").tabs("disable", 1);
			$("#response-key").toggle(this.activePoll.resource.object.mainComponent().editable());
			this.activePoll.buildResults();
		}
		
		$("#editpoll-save").toggle(this.activePoll.resource.object.mainComponent().editable());
		$("#editpoll-cancel").toggle(this.activePoll.resource.object.mainComponent().editable());
		$("#editpoll-done").toggle(!this.activePoll.resource.object.mainComponent().editable());
		$("#editpoll-autofill").toggle(this.activePoll.resource.object.mainComponent().editable());

		$("#detail-nocontent").hide();
		$("#editpoll").show();
	} else {
		$("#editpoll").hide();
		$("#detail-nocontent").show();
	}
}

ViewController.prototype.refreshed = function() {
	showLoading(false);
	if (this.ownedPolls.polls.length == 0 && this.voterPolls.polls.length != 0) {
		$("#sidebar").accordion("option", "active", 1);
	} else {
		$("#sidebar").accordion("option", "active", 0);
	}
}

// Rebuild results panel each time it is selected
ViewController.prototype.showResults = function(event, ui) {
	if (ui.newPanel.selector == "#editpoll-results") {
		this.activePoll.buildResults();
	}
	$("#editpoll-autofill").toggle(ui.newPanel.selector == "#editpoll-results");
	$("#response-key").toggle(ui.newPanel.selector == "#editpoll-results");
}

// Maintains the list of editable polls and manipulates the DOM as polls are
// added
// and removed.
PollList = function(menu, counter) {
	this.polls = [];
	this.menu = menu;
	this.counter = counter;
}

// Add a poll to the UI.
PollList.prototype.addPoll = function(poll) {
	this.polls.push(poll);
	poll.list = this;
	this.menu.append('<li class="sidebar-list"><a href="#">' + poll.title() + '</a></li>');
	this.menu.menu("refresh");
	this.counter.text(this.polls.length);
}

// Add a poll to the UI and save its resource
PollList.prototype.newPoll = function(poll) {
	this.addPoll(poll);
	poll.saveResource();
	$("#editpoll-delete").show();
}

// Change a poll in the UI and save its resource
PollList.prototype.changePoll = function(poll) {
	var index = this.polls.indexOf(poll);
	this.menu.find("a").eq(index).text(poll.title());
	this.menu.menu("refresh");
	poll.saveResource();
}

// Remove a poll resource and its UI
PollList.prototype.removePoll = function(poll) {
	var this_polllist = this;
	poll.resource.removeResource(function() {
		var index = this_polllist.polls.indexOf(poll);
		this_polllist.polls.splice(index, 1);
		this_polllist.menu.children("li").eq(index).remove();
		this_polllist.menu.menu("refresh");
		this_polllist.counter.text(this_polllist.polls.length);
	});
}

PollList.prototype.indexOfPollUID = function(uid) {
	var result = null;
	$.each(this.polls, function(index, poll) {
		if (poll.resource.object.mainComponent().uid() == uid) {
			result = index;
			return false;
		}
	});
	return result;
}

// Remove all UI items
PollList.prototype.clearPolls = function() {
	this.menu.empty();
	this.menu.menu("refresh");
	this.polls = [];
	this.counter.text(this.polls.length);
}

// An editable poll. It manipulates the DOM for editing a poll
Poll = function(resource) {
	this.resource = resource;
	this.owned = this.resource.object.mainComponent().isOwned();
	this.editing_object = null;
	this.editing_poll = null;
}

Poll.prototype.title = function() {
	return this.editing_poll ? this.editing_poll.summary() : this.resource.object.mainComponent().summary();
}

Poll.prototype.closed = function() {
	this.editing_poll = null;
}

// Save the editable state
Poll.prototype.saveResource = function(whenDone) {
	// Only if it changed
	if (this.editing_poll.changed()) {
		this.resource.object = this.editing_object;
		var this_poll = this;
		this.resource.saveResource(function() {
			// Reload from the resource as it might change after write to server
			this_poll.editing_object = this_poll.resource.object.duplicate();
			this_poll.editing_poll = this_poll.editing_object.mainComponent();
			
			if (whenDone) {
				whenDone();
			}
		});
	}
}

// Fill the UI with details of the poll
Poll.prototype.setPanel = function() {
	
	var this_poll = this;
	this.editing_object = this.resource.object.duplicate();
	this.editing_poll = this.editing_object.mainComponent();

	// Setup the details panel with this poll
	$("#editpoll-title-edit").val(this.editing_poll.summary());
	$("#editpoll-title").text(this.editing_poll.summary());
	$("#editpoll-organizer").text(this.editing_poll.organizerDisplayName());
	$("#editpoll-status").text(this.editing_poll.status());
	$("#editpoll-eventlist").empty();
	$.each(this.editing_poll.events(), function(index, event) {
		this_poll.setEventPanel(this_poll.addEventPanel(), event);
	});
	$("#editpoll-voterlist").empty();
	$.each(this.editing_poll.voters(), function(index, voter) {
		this_poll.setVoterPanel(this_poll.addVoterPanel(), voter);
	});
}

// Get poll details from the UI
Poll.prototype.getPanel = function() {
	var this_poll = this;

	// Get values from the details panel
	if (this.owned) {
		this.editing_poll.summary($("#editpoll-title-edit").val());
		
		var events = this.editing_poll.events();
		$("#editpoll-eventlist").children().each(function(index) {
			this_poll.updateEventFromPanel($(this), events[index]);
		});

		var voters = this.editing_poll.voters();
		$("#editpoll-voterlist").children().each(function(index) {
			this_poll.updateVoterFromPanel($(this), voters[index]);
		});
	}
}

//Add a new event item in the UI
Poll.prototype.addEventPanel = function() {

	var ctr = $("#editpoll-eventlist").children().length + 1;
	var idstart = "event-dtstart-" + ctr;
	var idend = "event-dtend-" + ctr;

	// Add new list item
	var evt = '<div class="event">';
	evt += '<div class="edit-datetime">';
	evt += '<label for="' + idstart + '">Start: </label>';
	evt += '<input type="text" id="' + idstart + '" class="event-dtstart"/>';
	evt += '</div>';
	evt += '<div class="edit-datetime">';
	evt += '<label for="' + idend + '">End:   </label>';
	evt += '<input type="text" id="' + idend + '" class="event-dtend" />';
	evt += '</div>';
	evt += '<button class="input-remove">Remove</button>';
	evt += '</div>';
	evt = $(evt).appendTo("#editpoll-eventlist");

	evt.find(".event-dtstart").datetimepicker();
	evt.find(".event-dtend").datetimepicker();
	evt.find(".input-remove").button({
		icons : {
			primary : "ui-icon-close"
		}
	});

	return evt;
}

// Update the UI for this event
Poll.prototype.setEventPanel = function(panel, event) {
	panel.find(".event-dtstart").datetimepicker("setDate", event.dtstart());
	panel.find(".event-dtend").datetimepicker("setDate", event.dtend());
	return panel;
}

// Get details of the event from the UI
Poll.prototype.updateEventFromPanel = function(panel, event) {
	event.summary($("#editpoll-title-edit").val());
	event.dtstart(panel.find(".event-dtstart").datetimepicker("getDate"));
	event.dtend(panel.find(".event-dtend").datetimepicker("getDate"));
}

// Add event button clicked
Poll.prototype.addEvent = function() {
	
	var ctr = $("#editpoll-eventlist").children().length;
	var dtstart = new Date();
	dtstart.setDate(dtstart.getDate() + ctr);
	dtstart.setHours(12, 0, 0, 0);
	var dtend = new Date();
	dtend.setDate(dtend.getDate() + ctr);
	dtend.setHours(13, 0, 0, 0);

	// Add new list item
	var vevent = this.editing_poll.addEvent(dtstart, dtend);
	return this.setEventPanel(this.addEventPanel(), vevent);
}

//Add a new voter item in the UI
Poll.prototype.addVoterPanel = function() {

	var ctr = $("#editpoll-voterlist").children().length + 1;
	var idvoter = "voter-address-" + ctr;

	// Add new list item
	var vtr = '<div class="voter">';
	vtr += '<div class="edit-voter">';
	vtr += '<label for="' + idvoter + '">Voter: </label>';
	vtr += '<input type="text" id="' + idvoter + '" class="voter-address"/>';
	vtr += '</div>';
	vtr += '<button class="input-remove">Remove</button>';
	vtr += '</div>';
	vtr = $(vtr).appendTo("#editpoll-voterlist");

	vtr.find(".voter-address").autocomplete({
		minLength : 3,
		source : function(request, response) {
			gSession.calendarUserSearch(request.term, function(results) {
				response(results);
			});
		}
	}).focus(function() {
		$(this).select();
	});
	
	vtr.find(".input-remove").button({
		icons : {
			primary : "ui-icon-close"
		}
	});

	return vtr;
}

// Update UI for this voter
Poll.prototype.setVoterPanel = function(panel, voter) {
	panel.find(".voter-address").val(voter.addressDescription());
	return panel;
}

// Get details of the voter from the UI
Poll.prototype.updateVoterFromPanel = function(panel, voter) {
	voter.addressDescription(panel.find(".voter-address").val());
}

// Add voter button clicked
Poll.prototype.addVoter = function() {
	// Add new list item
	var voter = this.editing_poll.addVoter();
	return this.setVoterPanel(this.addVoterPanel(), voter);
}

// Build the results UI based on the poll details
Poll.prototype.buildResults = function() {
	
	var this_poll = this;
	
	// Sync with any changes from other panels
	this.getPanel();

	var event_details = this.editing_poll.events();
	var voter_details = this.editing_poll.voters();

	var thead = $("#editpoll-resulttable").children("thead").first();
	var th_date = thead.children("tr").eq(0).empty();
	var th_start = thead.children("tr").eq(1).empty();
	var th_end = thead.children("tr").eq(2).empty();
	var tf = $("#editpoll-resulttable").children("tfoot").first();
	var tf_overall = tf.children("tr").first().empty();
	var tf_commit = tf.children("tr").last().empty();
	tf_commit.toggle(this.owned || !this_poll.editing_poll.editable());
	var tbody = $("#editpoll-resulttable").children("tbody").first().empty();
	$('<td>Date:</td>').appendTo(th_date);
	$('<td>Start:</td>').appendTo(th_start);
	$('<td>End:</td>').appendTo(th_end);
	$('<td>Overall:</td>').appendTo(tf_overall);
	$('<td />').appendTo(tf_commit);
	$.each(event_details, function(index, event) {
		var td_date = $('<td />').appendTo(th_date).text(event.dtstart().toDateString()).addClass("center-td");
		var td_start = $('<td />').appendTo(th_start).text(event.dtstart().toLocaleTimeString());
		var td_end = $('<td />').appendTo(th_end).text(event.dtend().toLocaleTimeString());
		$('<td />').appendTo(tf_overall).addClass("center-td");
		$('<td />').appendTo(tf_commit).addClass("center-td");
		if (event.ispollwinner()) {
			td_date.addClass("poll-winner-td");
			td_start.addClass("poll-winner-td");
			td_end.addClass("poll-winner-td");
		}
		td_date.hover(
			function() {
				this_poll.hoverDialogOpen(td_date, thead, event);
			},
			this_poll.hoverDialogClose
		);
	});
	$.each(voter_details, function(index, voter) {
		var active = gSession.currentPrincipal.matchingAddress(voter.cuaddr());
		var tr = $("<tr/>").appendTo(tbody);
		$("<td/>").appendTo(tr).text(voter.nameOrAddress());
		$.each(event_details, function(index, event) {
			var response = event.voter_responses()[voter.cuaddr()];
			var td = $("<td />").appendTo(tr).addClass("center-td");
			if (event.ispollwinner()) {
				td.addClass("poll-winner-td");
			}
			if (active && this_poll.editing_poll.editable()) {
				var radios = $('<div id="response-' + index + '" />').appendTo(td).addClass("response-btns");
				$('<input type="radio" id="respond_no-' + index + '" name="response-' + index + '"/>').appendTo(radios);
				$('<label for="respond_no-' + index + '"/>').appendTo(radios);
				$('<input type="radio" id="respond_maybe-' + index + '" name="response-' + index + '"/>').appendTo(radios);
				$('<label for="respond_maybe-' + index + '"/>').appendTo(radios);
				$('<input type="radio" id="respond_ok-' + index + '" name="response-' + index + '"/>').appendTo(radios);
				$('<label for="respond_ok-' + index + '"/>').appendTo(radios);
				$('<input type="radio" id="respond_best-' + index + '" name="response-' + index + '"/>').appendTo(radios);
				$('<label for="respond_best-' + index + '"/>').appendTo(radios);
				radios.buttonset();
				if (response !== undefined) {
					if (response < 40) {
						$('#respond_no-' + index).click();
					} else if (response < 80) {
						$('#respond_maybe-' + index).click();
					} else if (response < 90) {
						$('#respond_ok-' + index).click();
					} else {
						$('#respond_best-' + index).click();
					}
				}
				$('#respond_no-' + index).button({
					icons : {
						primary : "ui-icon-close"
					},
					text: false
				}).click(this_poll.clickResponse);
				$('#respond_maybe-' + index).button({
					icons : {
						primary : "ui-icon-help"
					},
					text: false
				}).click(this_poll.clickResponse);
				$('#respond_ok-' + index).button({
					icons : {
						primary : "ui-icon-check"
					},
					text: false
				}).click(this_poll.clickResponse);
				$('#respond_best-' + index).button({
					icons : {
						primary : "ui-icon-circle-check"
					},
					text: false
				}).click(this_poll.clickResponse);
			} else {
				td.text(this_poll.textForResponse(response)[0]);
			}
		});
		if (active) {
			tr.addClass("active-voter");
		}
	});

	$.each(event_details, function(index, event) {
		if (this_poll.editing_poll.editable()) {
			$('<button id="winner-' + index + '">Pick Winner</button>').appendTo(tf_commit.children()[index + 1]).button({
				icons : {
					primary : "ui-icon-star"
				},
			}).click(this_poll.clickWinner);
		} else {
			if (event.ispollwinner()) {
				$(tf_commit.children()[index + 1]).addClass("poll-winner-td");
				$('<div id="winner-text"><span id="winner-icon-left" class="ui-icon ui-icon-star" />Winner<span id="winner-icon-right" class="ui-icon ui-icon-star" /></div>').appendTo(tf_commit.children()[index + 1]);
			}
		}
	});

	this.updateOverallResults();
}

Poll.prototype.textForResponse = function(response) {
	var result = [];
	if (response === undefined) {
		result.push("No Response");
		result.push("no-response-td");
	} else if (response < 40) {
		result.push("No");
		result.push("no-td");
	} else if (response < 80) {
		result.push("Maybe");
		result.push("maybe-td");
	} else if (response < 90) {
		result.push("Ok");
		result.push("ok-td");
	} else {
		result.push("Best");
		result.push("best-td");
	}
	return result;
}

Poll.prototype.clickResponse = function() {
	var splits = $(this).attr("id").split("-");
	var response_type = splits[0];
	var index = parseInt(splits[1]);
	var response = 0;
	if (response_type == "respond_maybe") {
		response = 50;
	} else if (response_type == "respond_ok") {
		response = 85;
	} else if (response_type == "respond_best") {
		response = 100;
	}
	
	var event = gViewController.activePoll.editing_poll.events()[index];
	event.changeVoterResponse(response);
	gViewController.activePoll.updateOverallResults();
}

// A winner was chosen, make poll changes and create new event and save everything
Poll.prototype.clickWinner = function() {
	var splits = $(this).attr("id").split("-");
	var event = gViewController.activePoll.editing_poll.events()[parseInt(splits[1])];
	var new_resource = event.pickAsWinner();
	new_resource.saveResource(function() {
		gViewController.activePoll.saveResource(function() {
			gViewController.activatePoll(gViewController.activePoll);
		});
	})
}

// Open the event time-range hover dialog 
Poll.prototype.hoverDialogOpenClassic = function(td_date, thead, event) {
	var dialog_div = $('<div id="hover-cal" />').appendTo(td_date).dialog({
		dialogClass: "no-close",
		position: { my: "left top", at: "right+20 top", of: thead },
		show: "fade",
		title: "Your Events for " + event.dtstart().toDateString(),
		width: 400,
	});
	var start = new Date(event.dtstart().getTime() - 6 * 60 * 60 * 1000);
	var end = new Date(event.dtend().getTime() + 6 * 60 * 60 * 1000);
	gSession.currentPrincipal.eventsForTimeRange(
		start,
		end,
		function(results) {
			var text = "";
			results = $.map(results, function(result) {
				return result.mainComponent();
			});
			results.push(event);
			results.sort(function(a, b) {
				return a.dtstart().getTime() - b.dtstart().getTime();
			});
			var relative_offset = 10;
			var last_end = null;
			$.each(results, function(index, result) {
				text = result.dtstart().toLocaleTimeString() + " - ";
				text += result.dtend().toLocaleTimeString() + " : ";
				text += result.summary();
				if (last_end !== null && last_end.getTime() != result.dtstart().getTime()) {
					relative_offset += 10;
				}
				last_end = result.dtend();
				$('<div class="hover-event ui-corner-all" style="top:' + relative_offset + 'px"/>').appendTo(dialog_div).addClass(result.pollitemid() !== null ? "ui-state-active" : "ui-state-default").text(text);
			});
		}
	);
}

// Open the event time-range hover dialog 
Poll.prototype.hoverDialogOpenFancy = function(td_date, thead, event) {
	var dialog_div = $('<div id="hover-cal" />').appendTo(td_date).dialog({
		dialogClass: "no-close",
		position: { my: "left top", at: "right+20 top", of: thead },
		show: "fade",
		title: "Your Events for " + event.dtstart().toDateString(),
		width: 400,
	});
	
	var start = new Date(event.dtstart().getTime() - 6 * 60 * 60 * 1000);
	start.setMinutes(0, 0, 0);
	var startHour = start.getHours();
	var end = new Date(event.dtend().getTime() + 6 * 60 * 60 * 1000);
	end.setMinutes(0, 0, 0);
	var endHour = end.getHours();
	
	var grid = $('<table id="hover-grid" />').appendTo(dialog_div);
	for(var i = startHour; i < endHour; i++) {
		var text = i > 12 ? i - 12 +":00 pm" : i + (i == 12 ? ":00 pm" : ":00 am");
		$('<tr><td class="hover-grid-td-time">' + text + '</td><td class="hover-grid-td-slot" /></tr>').appendTo(grid);
	}
	gSession.currentPrincipal.eventsForTimeRange(
		start,
		end,
		function(results) {
			results = $.map(results, function(result) {
				return result.mainComponent();
			});
			results.push(event);
			results.sort(function(a, b) {
				return a.dtstart().getTime() - b.dtstart().getTime();
			});
			var last_dtend = null;
			$.each(results, function(index, result) {
				var top_offset = (result.dtstart().getHours() - startHour) * 30;
				var height = ((result.dtend().getTime() - result.dtstart().getTime()) * 30) / (60 * 60 * 1000) - 6;
				var styles = "top:" + top_offset + "px;height:" + height + "px";
				if (last_dtend !== null && last_dtend > result.dtstart()) {
					styles += ";left:206px;width:125px";
				}
				last_dtend = result.dtend();
				$('<div class="hover-event ui-corner-all" style="' + styles + '" />').appendTo(grid).addClass(result.pollitemid() !== null ? "ui-state-focus" : "ui-state-default").text(result.summary());
			});
		}
	);
}

Poll.prototype.hoverDialogOpen = Poll.prototype.hoverDialogOpenFancy;

// Close the event time-range hover dialog 
Poll.prototype.hoverDialogClose = function() {
	$("#hover-cal").dialog("close").remove();
}

Poll.prototype.updateOverallResults = function() {
	var this_poll = this;
	var event_details = this.editing_poll.events();
	var voter_details = this.editing_poll.voters();
	var tds = $("#editpoll-resulttable").children("tfoot").first().children("tr").first().children("td");

	// Update overall items
	$.each(event_details, function(index, event) {
		var overall = [];
		var responses = event.voter_responses();
		$.each(voter_details, function(index, voter) {
			var response = responses[voter.cuaddr()];
			if (response !== undefined) {
				overall.push(response);
			}
		});
		var response_details = this_poll.textForResponse(overall.average());
		var possible_classes = ["best-td", "ok-td", "maybe-td", "no-td", "no-response-td"];
		possible_classes.splice(possible_classes.indexOf(response_details[1]), 1);
		$(tds[index + 1]).text(response_details[0]);
		$(tds[index + 1]).removeClass(possible_classes.join(" "));
		$(tds[index + 1]).addClass(event.ispollwinner() ? "poll-winner-td" : response_details[1]);
	});
}

Poll.prototype.autoFill = function() {
	
	var event_details = this.editing_poll.events();
	$.each(event_details, function(index, event) {
		// Freebusy
		gSession.currentPrincipal.isBusy(
			gSession.currentPrincipal.defaultAddress(),
			event.dtstart(),
			event.dtend(),
			function(result) {
				$((result ? "#respond_no-" : "#respond_ok-") + index).click();
			}
		);
	});
}

