##
# Copyright (c) 2005-2008 Apple Inc. All rights reserved.
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

"""
Localization module

How to use:

    from __future__ import with_statement
    from localization import translationTo

    with translationTo('de'):
        print _("Hello")
        print _("The event will last %(days)d days") % { 'days' : 4 }

    ... Hallo
    ... Die Veranstaltung dauert 4 Tage

Before you can actually get translated text, you need to:

    1) Choose a "domain" for your code, such as 'calendarserver'
    2) Run pygettext.py on your source to generate a <domain>.pot file.
       pygettext.py scans the source for _( ) and copies those strings to the
       .pot.
    3) For each language, copy the .pot file to .po and give it to the person
       who is doing the translation for editing
    4) Run msgfmt.py on the translated .po to generate a binary .mo
    5) Put the .mo into locales/<lang>/LC_MESSAGES/<domain>.mo

The German .po file for the above example would look like:

    msgid "Hello"
    msgstr "Hallo"

    msgid "The event will last %(days)d days"
    msgstr "Die Veranstaltung dauert %(days)d Tage"

The transationTo class automatically binds '_' to the appropriate translation
function for the duration of the "with" context.  It's smart enough to allow
nesting of "with" contexts, as in:

    with translationTo('de'):
        print _("Hello") # in German

        with translationTo('fr'):
            print _("Hello") # in French

        print _("Hello") # in German

If a translation file cannot be found for the specified language, it will fall
back to 'en'.  If 'en' can't be found, gettext will raise IOError.

If you use the with/as form, you will get an object that implements some
helper methods for date formatting:

    with translationTo('en') as trans:
        print trans.date(datetime.today())

    ... Thursday, October 23, 2008

    with translationTo('fr') as trans:
        print trans.date(datetime.today())

    ... Jeudi, Octobre 23, 2008

The .po files contain localizable strings for month and day names, as well as
date format strings, in case a locale likes these values in a different order
or with different punctuation.

"""


import gettext
import inspect




class translationTo(object):

    translations = {}

    def __init__(self, lang, domain='calendarserver', localedir='locales'):

        # Cache gettext translation objects in class.translations
        key = (lang, domain, localedir)
        self.translation = self.translations.get(key, None)
        if self.translation is None:
            self.translation = gettext.translation(domain=domain,
                localedir=localedir, languages=[lang, 'en'])
            self.translations[key] = self.translation

    def __enter__(self):
        # Get the caller's locals so we can rebind their '_' to our translator
        caller_locals = inspect.stack()[-1][0].f_locals

        # Store whatever '_' is already bound to so we can restore it later
        if caller_locals.has_key('_'):
            self.prev = caller_locals['_']

        # Rebind '_' to our translator
        caller_locals['_'] = self.translation.gettext

        # What we return here is accessible to the caller via the 'as' clause
        return self

    def __exit__(self, type, value, traceback):
        # Restore '_' if it previously had a value
        if hasattr(self, 'prev'):
            inspect.stack()[-1][0].f_locals['_'] = self.prev

        # Don't swallow exceptions
        return False

    def date(self, val):
        # val is either a date (allday) or datetime

        # Bind to '_' so pygettext.py will pick this up for translation
        _ = self.translation.gettext

        return (
            _("%(dayName)s, %(monthName)s %(dayNumber)d, %(yearNumber)d")
            % {
                'dayName'    : _(daysFull[val.weekday()]),
                'monthName'  : _(monthsFull[val.month]),
                'dayNumber'  : val.day,
                'yearNumber' : val.year,
            }
        )


# The strings below are wrapped in _( ) for the benefit of pygettext.  We don't
# actually want them translated until they're used.

_ = lambda x: x

daysFull = [
    _("Monday"),
    _("Tuesday"),
    _("Wednesday"),
    _("Thursday"),
    _("Friday"),
    _("Saturday"),
    _("Sunday"),
]

daysAbrev = [
    _("Mon"),
    _("Tue"),
    _("Wed"),
    _("Thu"),
    _("Fri"),
    _("Sun"),
    _("Sat"),
]

monthsFull = [
    "datetime.month is 1-based",
    _("January"),
    _("February"),
    _("March"),
    _("April"),
    _("May"),
    _("June"),
    _("July"),
    _("August"),
    _("September"),
    _("October"),
    _("November"),
    _("December"),
]

monthsAbbrev = [
    "datetime.month is 1-based",
    _("Jan"),
    _("Feb"),
    _("Mar"),
    _("Apr"),
    _("May"),
    _("Jun"),
    _("Jul"),
    _("Aug"),
    _("Sep"),
    _("Oct"),
    _("Nov"),
    _("Dec"),
]
