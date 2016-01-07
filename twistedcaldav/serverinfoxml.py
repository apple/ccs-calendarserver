##
# Copyright (c) 2015-2016 Apple Inc. All rights reserved.
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

from txdav.xml.element import WebDAVElement, dav_namespace, registerElement, \
    WebDAVTextElement, WebDAVEmptyElement, Bind, \
    SyncCollection, AddMember

@registerElement
class ServerInfo (WebDAVElement):
    namespace = dav_namespace
    name = "server-info"
    allowed_children = {
        (dav_namespace, "token"): (1, 1),
        (dav_namespace, "features"): (0, 1),
        (dav_namespace, "services"): (0, 1),
    }



@registerElement
class Token (WebDAVTextElement):
    namespace = dav_namespace
    name = "token"



@registerElement
class Features (WebDAVElement):
    namespace = dav_namespace
    name = "features"
    allowed_children = {}



@registerElement
class Applications (WebDAVElement):
    namespace = dav_namespace
    name = "applications"
    allowed_children = {
        (dav_namespace, "application"): (0, None),
    }



@registerElement
class Application (WebDAVElement):
    namespace = dav_namespace
    name = "application"
    allowed_children = {
        (dav_namespace, "name"): (1, 1),
        (dav_namespace, "features"): (1, 1),
    }



@registerElement
class Name_Service (WebDAVTextElement):
    namespace = dav_namespace
    name = "name"



@registerElement
class Class1_Feature (WebDAVEmptyElement):
    namespace = dav_namespace
    name = "class-1"



@registerElement
class Class2_Feature (WebDAVEmptyElement):
    namespace = dav_namespace
    name = "class-2"



@registerElement
class Class3_Feature (WebDAVEmptyElement):
    namespace = dav_namespace
    name = "class-3"



@registerElement
class AccessControl_Feature (WebDAVEmptyElement):
    namespace = dav_namespace
    name = "access-control"



@registerElement
class VersionControl_Feature (WebDAVEmptyElement):
    namespace = dav_namespace
    name = "version-control"



@registerElement
class ExtendedMkcol_Feature (WebDAVEmptyElement):
    namespace = dav_namespace
    name = "extended-mkcol"



@registerElement
class Quota_Feature (WebDAVEmptyElement):
    namespace = dav_namespace
    name = "quota"



Bind_Feature = Bind



@registerElement
class Search_Feature (WebDAVEmptyElement):
    namespace = dav_namespace
    name = "search"



SyncCollection_Feature = SyncCollection



AddMember_Feature = AddMember
