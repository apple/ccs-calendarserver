##
# Copyright (c) 2006-2014 Apple Inc. All rights reserved.
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
    Utilities to converting a Record to a vCard
"""

__all__ = [
    "vCardFromRecord"
]

from pycalendar.vcard.adr import Adr
from pycalendar.vcard.n import N
from twext.python.log import Logger
from twext.who.idirectory import FieldName, RecordType
from twisted.internet.defer import inlineCallbacks, returnValue
from twistedcaldav.config import config
from twistedcaldav.vcard import Component, Property, vCardProductID
from txdav.who.idirectory import FieldName as CalFieldName, \
    RecordType as CalRecordType
from txweb2.dav.util import joinURL

log = Logger()


recordTypeToVCardKindMap = {
   RecordType.user: "individual",
   RecordType.group: "group",
   CalRecordType.location: "location",
   CalRecordType.resource: "device",
}

vCardKindToRecordTypeMap = {
   "individual" : RecordType.user,
   "group": RecordType.group,
   "org": RecordType.group,
   "location": CalRecordType.location,
   "device": CalRecordType.resource,
}


# all possible generated parameters.
vCardPropToParamMap = {
    #"PHOTO": {"ENCODING": ("B",), "TYPE": ("JPEG",), },
    "ADR": {"TYPE": ("WORK", "PREF", "POSTAL", "PARCEL",),
            "LABEL": None, "GEO": None, },
    #"LABEL": {"TYPE": ("POSTAL", "PARCEL",)},
    #"TEL": {"TYPE": None, },  # None means param can contain can be anything
    "EMAIL": {"TYPE": None, },
    #"KEY": {"ENCODING": ("B",), "TYPE": ("PGPPUBILICKEY", "USERCERTIFICATE", "USERPKCS12DATA", "USERSMIMECERTIFICATE",)},
    #"URL": {"TYPE": ("WEBLOG", "HOMEPAGE",)},
    #"IMPP": {"TYPE": ("PREF",), "X-SERVICE-TYPE": None, },
    #"X-ABRELATEDNAMES": {"TYPE": None, },
    #"X-AIM": {"TYPE": ("PREF",), },
    #"X-JABBER": {"TYPE": ("PREF",), },
    #"X-MSN": {"TYPE": ("PREF",), },
    #"X-ICQ": {"TYPE": ("PREF",), },
}


vCardConstantProperties = {
    #===================================================================
    # 3.6 EXPLANATORY TYPES http://tools.ietf.org/html/rfc2426#section-3.6
    #===================================================================
    # 3.6.3 PRODID
    "PRODID": vCardProductID,
    # 3.6.9 VERSION
    "VERSION": "3.0",
}


@inlineCallbacks
def vCardFromRecord(record, forceKind=None, addProps=None, parentURI=None):

    def isUniqueProperty(newProperty, ignoredParameters={}):
        existingProperties = vcard.properties(newProperty.name())
        for existingProperty in existingProperties:
            if ignoredParameters:
                existingProperty = existingProperty.duplicate()
                for paramName, paramValues in ignoredParameters.iteritems():
                    for paramValue in paramValues:
                        existingProperty.removeParameterValue(paramName, paramValue)
            if existingProperty == newProperty:
                return False
        return True


    def addUniqueProperty(newProperty, ignoredParameters=None):
        if isUniqueProperty(newProperty, ignoredParameters):
            vcard.addProperty(newProperty)
        else:
            log.info(
                "Ignoring property {prop!r} it is a duplicate",
                prop=newProperty
            )

    #=======================================================================
    # start
    #=======================================================================

    log.debug("vCardFromRecord: record={record}, forceKind={forceKind}, addProps={addProps}, parentURI={parentURI}",
                   record=record, forceKind=forceKind, addProps=addProps, parentURI=parentURI)

    if forceKind is None:
        kind = recordTypeToVCardKindMap.get(record.recordType, "individual")
    else:
        kind = forceKind

    constantProperties = vCardConstantProperties.copy()
    if addProps:
        for key, value in addProps.iteritems():
            if key not in constantProperties:
                constantProperties[key] = value

    # create vCard
    vcard = Component("VCARD")

    # add constant properties
    for key, value in constantProperties.items():
        vcard.addProperty(Property(key, value))

    #===========================================================================
    # 2.1 Predefined Type Usage
    #===========================================================================
    # 2.1.4 SOURCE Type http://tools.ietf.org/html/rfc2426#section-2.1.4
    if parentURI:
        uri = joinURL(parentURI, record.fields[FieldName.uid].encode("utf-8") + ".vcf")

        # seems like this should be in some standard place.
        if config.EnableSSL and config.SSLPort:
            if config.SSLPort == 443:
                source = "https://{server}{uri}".format(server=config.ServerHostName, uri=uri)
            else:
                source = "https://{server}:{port}{uri}".format(server=config.ServerHostName, port=config.SSLPort, uri=uri)
        else:
            if config.HTTPPort == 80:
                source = "https://{server}{uri}".format(server=config.ServerHostName, uri=uri)
            else:
                source = "https://{server}:{port}{uri}".format(server=config.ServerHostName, port=config.HTTPPort, uri=uri)
        vcard.addProperty(Property("SOURCE", source))

    #===================================================================
    # 3.1 IDENTIFICATION TYPES http://tools.ietf.org/html/rfc2426#section-3.1
    #===================================================================
    # 3.1.1 FN
    vcard.addProperty(Property("FN", record.fields[FieldName.fullNames][0].encode("utf-8")))

    # 3.1.2 N
    # TODO: Better parsing
    fullNameParts = record.fields[FieldName.fullNames][0].split()
    first = fullNameParts[0] if len(fullNameParts) >= 2 else None
    last = fullNameParts[len(fullNameParts) - 1]
    middle = fullNameParts[1] if len(fullNameParts) == 3 else None
    prefix = None
    suffix = None

    nameObject = N(
        first=first.encode("utf-8") if first else None,
        last=last.encode("utf-8") if last else None,
        middle=middle.encode("utf-8") if middle else None,
        prefix=prefix.encode("utf-8") if prefix else None,
        suffix=suffix.encode("utf-8") if suffix else None,
    )
    vcard.addProperty(Property("N", nameObject))

    # 3.1.3 NICKNAME
    nickname = record.fields.get(CalFieldName.abbreviatedName)
    if nickname:
        vcard.addProperty(Property("NICKNAME", nickname.encode("utf-8")))

    # UNIMPLEMENTED
    #     3.1.4 PHOTO
    #     3.1.5 BDAY

    #===========================================================================
    # 3.2 Delivery Addressing Types http://tools.ietf.org/html/rfc2426#section-3.2
    #===========================================================================
    # 3.2.1 ADR
    #
    # Experimental:
    #     Use vCard 4.0 ADR: http://tools.ietf.org/html/rfc6350#section-6.3.1
    params = {}
    geo = record.fields.get(CalFieldName.geographicLocation)
    if geo:
        params["GEO"] = geo.encode("utf-8")
    label = record.fields.get(CalFieldName.streetAddress)
    if label:
        params["LABEL"] = label.encode("utf-8")

    #
    extended = record.fields.get(CalFieldName.floor)

    # TODO: Parse?
    street = record.fields.get(CalFieldName.streetAddress)
    city = None
    region = None
    postalcode = None
    country = None

    if extended or street or city or region or postalcode or country or params:
        params["TYPE"] = ("WORK", "PREF", "POSTAL", "PARCEL",)
        vcard.addProperty(
            Property(
                "ADR", Adr(
                    #pobox = box,
                    extended=extended.encode("utf-8") if extended else None,
                    street=street.encode("utf-8") if street else None,
                    locality=city.encode("utf-8") if city else None,
                    region=region.encode("utf-8") if region else None,
                    postalcode=postalcode.encode("utf-8") if postalcode else None,
                    country=country.encode("utf-8") if country else None,
                ),
                params=params
            )
        )

    # UNIMPLEMENTED
    #     3.2.2 LABEL

    #===================================================================
    # 3.3 TELECOMMUNICATIONS ADDRESSING TYPES http://tools.ietf.org/html/rfc2426#section-3.3
    #===================================================================
    #
    # UNIMPLEMENTED
    #     3.3.1 TEL

    # 3.3.2 EMAIL
    preferredWorkParams = {"TYPE": ("WORK", "PREF", "INTERNET",), }
    workParams = {"TYPE": ("WORK", "INTERNET",), }
    params = preferredWorkParams
    for emailAddress in record.fields.get(FieldName.emailAddresses, []):
        addUniqueProperty(Property("EMAIL", emailAddress.encode("utf-8"), params=params), ignoredParameters={"TYPE": ("PREF",)})
        params = workParams

    # UNIMPLEMENTED:
    #     3.3.3 MAILER
    #
    #===================================================================
    # 3.4 GEOGRAPHICAL TYPES http://tools.ietf.org/html/rfc2426#section-3.4
    #===================================================================
    #
    # UNIMPLEMENTED:
    #     3.4.1 TZ
    #
    # 3.4.2 GEO
    geographicLocation = record.fields.get(CalFieldName.geographicLocation)
    if geographicLocation:
        vcard.addProperty(Property("GEO", geographicLocation.encode("utf-8")))

    #===================================================================
    # 3.5 ORGANIZATIONAL TYPES http://tools.ietf.org/html/rfc2426#section-3.5
    #===================================================================
    #
    # UNIMPLEMENTED:
    #     3.5.1 TITLE
    #     3.5.2 ROLE
    #     3.5.3 LOGO
    #     3.5.4 AGENT
    #     3.5.5 ORG
    #
    #===================================================================
    # 3.6 EXPLANATORY TYPES http://tools.ietf.org/html/rfc2426#section-3.6
    #===================================================================
    #
    # UNIMPLEMENTED:
    #     3.6.1 CATEGORIES
    #     3.6.2 NOTE
    #
    # ADDED WITH CONTSTANT PROPERTIES:
    #     3.6.3 PRODID
    #
    # UNIMPLEMENTED:
    #     3.6.5 SORT-STRING
    #     3.6.6 SOUND

    # 3.6.7 UID
    vcard.addProperty(Property("UID", record.fields[FieldName.uid].encode("utf-8")))

    # UNIMPLEMENTED:
    #     3.6.8 URL

    # ADDED WITH CONTSTANT PROPERTIES:
    #     3.6.9 VERSION

    #===================================================================
    # 3.7 SECURITY TYPES http://tools.ietf.org/html/rfc2426#section-3.7
    #===================================================================
    # UNIMPLEMENTED:
    #     3.7.1 CLASS
    #     3.7.2 KEY

    #===================================================================
    # X Properties
    #===================================================================
    # UNIMPLEMENTED:
    #    X-<instant messaging type> such as:
    #        "AIM", "FACEBOOK", "GAGU-GAGU", "GOOGLE TALK", "ICQ", "JABBER", "MSN", "QQ", "SKYPE", "YAHOO",
    #    X-MAIDENNAME
    #    X-PHONETIC-FIRST-NAME
    #    X-PHONETIC-MIDDLE-NAME
    #    X-PHONETIC-LAST-NAME
    #    X-ABRELATEDNAMES

    # X-ADDRESSBOOKSERVER-KIND
    if kind == "group":
        vcard.addProperty(Property("X-ADDRESSBOOKSERVER-KIND", kind))

    # add members
    # FIXME:  members() is a deferred, so all of vCardFromRecord is deferred.
    for memberRecord in (yield record.members()):
        if memberRecord:
            vcard.addProperty(Property("X-ADDRESSBOOKSERVER-MEMBER", memberRecord.canonicalCalendarUserAddress().encode("utf-8")))

    #===================================================================
    # vCard 4.0  http://tools.ietf.org/html/rfc6350
    #===================================================================
    # UNIMPLEMENTED:
    #     6.4.3 IMPP http://tools.ietf.org/html/rfc6350#section-6.4.3
    #
    # 6.1.4 KIND http://tools.ietf.org/html/rfc6350#section-6.1.4
    #
    # see also: http://www.iana.org/assignments/vcard-elements/vcard-elements.xml
    #
    vcard.addProperty(Property("KIND", kind))

    # one more X- related to kind
    if kind == "org":
        vcard.addProperty(Property("X-ABShowAs", "COMPANY"))

    log.debug("vCardFromRecord: vcard=\n{vcard}", vcard=vcard)
    returnValue(vcard)
