/*
 * Copyright (c) 2010 Apple Inc. All rights reserved.
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

#include <Python.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <signal.h>

PyObject *sendmsg_socket_error;

static PyObject *sendmsg_sendmsg(PyObject *self, PyObject *args, PyObject *keywds);
static PyObject *sendmsg_recvmsg(PyObject *self, PyObject *args, PyObject *keywds);

static PyMethodDef sendmsg_methods[] = {
    {"sendmsg", (PyCFunction) sendmsg_sendmsg, METH_VARARGS | METH_KEYWORDS,
     NULL},
    {"recvmsg", (PyCFunction) sendmsg_recvmsg, METH_VARARGS | METH_KEYWORDS,
     NULL},
    {NULL, NULL, 0, NULL}
};


PyMODINIT_FUNC initsendmsg(void) {
    PyObject *module;

    sendmsg_socket_error = NULL; /* Make sure that this has a known value
                                    before doing anything that might exit. */

    module = Py_InitModule("sendmsg", sendmsg_methods);

    if (!module) {
        return;
    }

    /*
      The following is the only value mentioned by POSIX:
      http://www.opengroup.org/onlinepubs/9699919799/basedefs/sys_socket.h.html
    */

    if (-1 == PyModule_AddIntConstant(module, "SCM_RIGHTS", SCM_RIGHTS)) {
        return;
    }


    /* BSD, Darwin, Hurd */
#if defined(SCM_CREDS)
    if (-1 == PyModule_AddIntConstant(module, "SCM_CREDS", SCM_CREDS)) {
        return;
    }
#endif

    /* Linux */
#if defined(SCM_CREDENTIALS)
    if (-1 == PyModule_AddIntConstant(module, "SCM_CREDENTIALS", SCM_CREDENTIALS)) {
        return;
    }
#endif

    /* Apparently everywhere, but not standardized. */
#if defined(SCM_TIMESTAMP)
    if (-1 == PyModule_AddIntConstant(module, "SCM_TIMESTAMP", SCM_TIMESTAMP)) {
        return;
    }
#endif

    module = PyImport_ImportModule("socket");
    if (!module) {
        return;
    }

    sendmsg_socket_error = PyObject_GetAttrString(module, "error");
    if (!sendmsg_socket_error) {
        return;
    }
}

static PyObject *sendmsg_sendmsg(PyObject *self, PyObject *args, PyObject *keywds) {

    int fd;
    int flags = 0;
    int sendmsg_result;
    struct msghdr message_header;
    struct iovec iov[1];
    PyObject *ancillary = NULL;
    static char *kwlist[] = {"fd", "data", "flags", "ancillary", NULL};

    if (!PyArg_ParseTupleAndKeywords(
            args, keywds, "it#|iO:sendmsg", kwlist,
            &fd,
            &iov[0].iov_base,
            &iov[0].iov_len,
            &flags,
            &ancillary)) {
        return NULL;
    }

    message_header.msg_name = NULL;
    message_header.msg_namelen = 0;

    message_header.msg_iov = iov;
    message_header.msg_iovlen = 1;

    message_header.msg_control = NULL;
    message_header.msg_controllen = 0;

    message_header.msg_flags = 0;

    if (ancillary) {

        if (!PyList_Check(ancillary)) {
            PyErr_Format(PyExc_TypeError,
                         "sendmsg argument 3 expected list, got %s",
                         ancillary->ob_type->tp_name);
            return NULL;
        }

        PyObject *iterator = PyObject_GetIter(ancillary);
        PyObject *item = NULL;

        if (iterator == NULL) {
            return NULL;
        }

        int all_data_len = 0;

        /* First we need to know how big the buffer needs to be in order to
           have enough space for all of the messages. */
        while ( (item = PyIter_Next(iterator)) ) {
            int data_len, type, level;
            char *data;
            if (!PyArg_ParseTuple(item, "iit#:sendmsg ancillary data (level, type, data)",
                                  &level,
                                  &type,
                                  &data,
                                  &data_len)) {
                Py_DECREF(item);
                Py_DECREF(iterator);
                return NULL;
            }
            all_data_len += CMSG_SPACE(data_len);

            Py_DECREF(item);
        }

        Py_DECREF(iterator);
        iterator = NULL;

        /* Allocate the buffer for all of the ancillary elements, if we have
         * any.  */
        if (all_data_len) {
            message_header.msg_control = malloc(all_data_len);
            if (!message_header.msg_control) {
                PyErr_NoMemory();
                return NULL;
            }
        } else {
            message_header.msg_control = NULL;
        }
        message_header.msg_controllen = all_data_len;

        iterator = PyObject_GetIter(ancillary); /* again */
        item = NULL;

        if (!iterator) {
            free(message_header.msg_control);
            return NULL;
        }

        /* Unpack the tuples into the control message. */
        struct cmsghdr *control_message = CMSG_FIRSTHDR(&message_header);
        while ( (item = PyIter_Next(iterator)) ) {
            int data_len, type, level;
            unsigned char *data, *cmsg_data;

            /* We explicitly allocated enough space for all ancillary data
               above; if there isn't enough room, all bets are off. */
            assert(control_message);

            if (!PyArg_ParseTuple(item,
                                  "iit#:sendmsg ancillary data (level, type, data)",
                                  &level,
                                  &type,
                                  &data,
                                  &data_len)) {
                Py_DECREF(item);
                Py_DECREF(iterator);
                free(message_header.msg_control);
                return NULL;
            }

            control_message->cmsg_level = level;
            control_message->cmsg_type = type;
            control_message->cmsg_len = CMSG_LEN(data_len);

            cmsg_data = CMSG_DATA(control_message);
            memcpy(cmsg_data, data, data_len);

            Py_DECREF(item);

            control_message = CMSG_NXTHDR(&message_header, control_message);
        }
        
        Py_DECREF(iterator);
        
        if (PyErr_Occurred()) {
            free(message_header.msg_control);
            return NULL;
        }
    }

    sendmsg_result = sendmsg(fd, &message_header, flags);

    if (sendmsg_result < 0) {
        PyErr_SetFromErrno(sendmsg_socket_error);
        if (message_header.msg_control) {
            free(message_header.msg_control);
        }
        return NULL;
    }

    return Py_BuildValue("i", sendmsg_result);
}

static PyObject *sendmsg_recvmsg(PyObject *self, PyObject *args, PyObject *keywds) {
    int fd = -1;
    int flags = 0;
    size_t maxsize = 8192;
    size_t cmsg_size = 4*1024;
    int recvmsg_result;
    struct msghdr message_header;
    struct cmsghdr *control_message;
    struct iovec iov[1];
    char *cmsgbuf;
    PyObject *ancillary;
    PyObject *final_result = NULL;

    static char *kwlist[] = {"fd", "flags", "maxsize", "cmsg_size", NULL};

    if (!PyArg_ParseTupleAndKeywords(args, keywds, "i|iii:recvmsg", kwlist,
                                     &fd, &flags, &maxsize, &cmsg_size)) {
        return NULL;
    }

    cmsg_size = CMSG_SPACE(cmsg_size);

    message_header.msg_name = NULL;
    message_header.msg_namelen = 0;

    iov[0].iov_len = maxsize;
    iov[0].iov_base = malloc(maxsize);

    if (!iov[0].iov_base) {
        PyErr_NoMemory();
        return NULL;
    }

    message_header.msg_iov = iov;
    message_header.msg_iovlen = 1;

    cmsgbuf = malloc(cmsg_size);

    if (!cmsgbuf) {
        free(iov[0].iov_base);
        PyErr_NoMemory();
        return NULL;
    }

    memset(cmsgbuf, 0, cmsg_size);
    message_header.msg_control = cmsgbuf;
    message_header.msg_controllen = cmsg_size;

    recvmsg_result = recvmsg(fd, &message_header, flags);
    if (recvmsg_result < 0) {
        PyErr_SetFromErrno(sendmsg_socket_error);
        goto finished;
    }

    ancillary = PyList_New(0);
    if (!ancillary) {
        goto finished;
    }

    for (control_message = CMSG_FIRSTHDR(&message_header);
         control_message;
         control_message = CMSG_NXTHDR(&message_header,
                                       control_message)) {
        PyObject *entry;

        /* Some platforms apparently always fill out the ancillary data
           structure with a single bogus value if none is provided; ignore it,
           if that is the case. */

        if ((!(control_message->cmsg_level)) &&
            (!(control_message->cmsg_type))) {
            continue;
        }

        entry = Py_BuildValue(
            "(iis#)",
            control_message->cmsg_level,
            control_message->cmsg_type,
            CMSG_DATA(control_message),
            control_message->cmsg_len - sizeof(struct cmsghdr));

        if (!entry) {
            Py_DECREF(ancillary);
            goto finished;
        }

        if (PyList_Append(ancillary, entry) < 0) {
            Py_DECREF(ancillary);
            Py_DECREF(entry);
            goto finished;
        } else {
            Py_DECREF(entry);
        }
    }

    final_result = Py_BuildValue(
        "s#iO",
        iov[0].iov_base,
        recvmsg_result,
        message_header.msg_flags,
        ancillary);

    Py_DECREF(ancillary);

  finished:
    free(iov[0].iov_base);
    free(cmsgbuf);
    return final_result;
}

