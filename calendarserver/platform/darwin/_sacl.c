/*
 * Copyright (c) 2006-2013 Apple Inc. All rights reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include "Python.h"
#include <Security/Security.h>
#include <membership.h>

int mbr_check_service_membership(const uuid_t user, const char* servicename, int* ismember);
int mbr_user_name_to_uuid(const char* name, uuid_t uu);
int mbr_group_name_to_uuid(const char* name, uuid_t uu);

/*
    CheckSACL(userOrGroupName, service)
    Checks user or group membership in a service.
*/
static PyObject *appleauth_CheckSACL(PyObject *self, PyObject *args) {
    char *username;
    int usernameSize;
    char *serviceName;
    int serviceNameSize;

    char *prefix = "com.apple.access_";
    char groupName[256];
    uuid_t group_uu;

    // get the args
    if (!PyArg_ParseTuple(args, "s#s#", &username,
                          &usernameSize, &serviceName, &serviceNameSize)) {
        return NULL;
    }

    // If the username is empty, see if there is a com.apple.access_<service>
    // group
    if ( usernameSize == 0 ) {
        if ( strlen(serviceName) > 255 - strlen(prefix) ) {
            return Py_BuildValue("i", (-3));
        }
        memcpy(groupName, prefix, strlen(prefix));
        strcpy(groupName + strlen(prefix), serviceName);
        if ( mbr_group_name_to_uuid(groupName, group_uu) == 0 ) {
            // com.apple.access_<serviceName> group does exist, so
            // unauthenticated users are not allowed
            return Py_BuildValue("i", (-1));
        } else {
            // com.apple.access_<serviceName> group doesn't exist, so
            // unauthenticated users are allowed
            return Py_BuildValue("i", 0);
        }
    }

    // get a uuid for the user
    uuid_t user;
    int result = mbr_user_name_to_uuid(username, user);
    int isMember = 0;

    if ( result != 0 ) {
        // no uuid for the user, we might be a group.
        result = mbr_group_name_to_uuid(username, user);
    }

    if ( result != 0 ) {
        return Py_BuildValue("i", (-1));
    }

    result = mbr_check_service_membership(user, serviceName, &isMember);

    if ( ( result == 0 && isMember == 1 ) || ( result == ENOENT ) ) {
        // passed
        return Py_BuildValue("i", 0);
    }

    return Py_BuildValue("i", (-2));
}

/* Method definitions. */
static struct PyMethodDef _sacl_methods[] = {
    {"CheckSACL", appleauth_CheckSACL},
    {NULL, NULL} /* Sentinel */
};

void init_sacl(void) {
    Py_InitModule("_sacl", _sacl_methods);
}
