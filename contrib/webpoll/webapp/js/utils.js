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

/**
 * Utility classes.
 */

// XML processing utilities
// Make it easier to use namespaces by allowing the following "NS:" prefixes on
// element names
var gNamespaceShortcuts = {
	"D" : "DAV:",
	"C" : "urn:ietf:params:xml:ns:caldav",
	"CS" : "http://calendarserver.org/ns/"
};

// Add a shortcut namespace for use in an xmlns map
function addNamespace(shortcut, xmlnsmap) {
	xmlnsmap[gNamespaceShortcuts[shortcut]] = shortcut;
}

function buildXMLNS(xmlnsmap) {
	var xmlnstr = "";
	$.each(xmlnsmap, function(ns, nsprefix) {
		xmlnstr += ' xmlns:' + nsprefix + '="' + ns + '"';
	});
	return xmlnstr;
}

function addElements(elements, xmlnsmap) {
	var propstr = "";
	$.each(elements, function(index, element) {
		var segments = element.split(":");
		addNamespace(segments[0], xmlnsmap);
		propstr += '<' + element + ' />';
	});
	return propstr;
}

// Find XML elements matching the specified xpath
function findElementPath(node, path) {
	return findElementPathSegments(node, path.split("/"));
}

// Find XML elements matching the specified path segments
function findElementPathSegments(root, segments) {
	var elements = findElementNS(root, segments[0]);
	if (segments.length == 1) {
		return elements;
	}
	var results = [];
	$.each(elements, function(index, name) {
		var next = findElementPathSegments($(this), segments.slice(1));
		$.each(next, function(index, item) {
			results.push(item);
		});
	});
	return results;
}

// Find immediate children of node matching the XML {NS}name
function findElementNS(node, nsname) {
	var segments = nsname.split(":");
	var namespace = gNamespaceShortcuts[segments[0]];
	var name = segments[1];
	var results = [];
	node.children().each(function() {
		if (this.localName == name && this.namespaceURI == namespace) {
			results.push($(this));
		}
	});
	return results;
}

// Get text of target element from an xpath
function getElementText(node, path) {
	var items = findElementPath(node, path);
	return (items.length == 1) ? items[0].text() : null;
}

// Check for the existence of an element
function hasElementPath(node, path) {
	var elements = findElementPath(node, path);
	return elements.length != 0;
}

function xmlEncode(text)
{
	return text.replace(/&(?!\w+([;\s]|$))/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// URL helpers

// Removing any trailing slash from a URL
function removeTrailingSlash(url) {
	return (url[url.length - 1] == "/") ? url.substr(0, url.length - 1) : url;
}

// Removing any trailing slash from a URL
function removeLeadingSlash(url) {
	return (url[0] == "/") ? url = url.substr(1) : url;
}

// Compare two URLs ignoring trailing slash
function compareURLs(url1, url2) {
	return removeTrailingSlash(url1) == removeTrailingSlash(url2);
}

// Join two URLs
function joinURLs(url1, url2) {
	return removeTrailingSlash(url1) + "/" + removeLeadingSlash(url2);
}

// Get last path segment
function basenameURL(url) {
	return removeTrailingSlash(url).split("/").pop();
}

// UUID

function generateUUID() {
	var result = "";
	for ( var i = 0; i < 32; i++) {
		if (i == 8 || i == 12 || i == 16 || i == 20)
			result = result + '-';
		result += Math.floor(Math.random() * 16).toString(16).toUpperCase();
	}
	return result;
}

// Addresses

function addressDescription(cn, addr) {
	return addr ? (cn ? cn + " " : "") + "<" + addr + ">" : "";
}

function splitAddressDescription(desc) {
	results = ["", ""];
	if (desc.indexOf("<") == -1) {
		results[1] = desc;
	} else {
		var splits = desc.split("<");
		results[0] = splits[0].substr(0, splits[0].length - 1);
		results[1] = splits[1].substr(0, splits[1].length - 1);
	}
	
	return results;
}

// JSString extensions

if (typeof String.prototype.startsWith != 'function') {
	String.prototype.startsWith = function(str) {
		return this.slice(0, str.length) == str;
	};
}
if (typeof String.prototype.endsWith != 'function') {
	String.prototype.endsWith = function(str) {
		return this.slice(-str.length) == str;
	};
}

if (typeof String.prototype.strtoul != 'function') {

	String.prototype.strtoul = function(offset) {
		if (offset === undefined) {
			offset = 0;
		}
		var matches = this.substring(offset).match(/^[0-9]+/);
		if (matches.length == 1) {
			return {
				num : parseInt(matches[0]),
				offset : offset + matches[0].length
			}
		} else {
			throw "ValueError";
		}
	}
}

// JSArray extensions

if (typeof Array.prototype.average != 'function') {
	Array.prototype.average = function() {
		return this.sum() / this.length;
	};
}
if (typeof Array.prototype.sum != 'function') {
	Array.prototype.sum = function() {
		var result = 0;
		$.each(this, function(index, num) {
			result += num;
		});
		return result;
	};
}
