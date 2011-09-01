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

#define PY_SSIZE_T_CLEAN 1
#include <Python.h>

#if PY_VERSION_HEX < 0x02050000 && !defined(PY_SSIZE_T_MIN)
/* This may cause some warnings, but if you want to get rid of them, upgrade
 * your Python version.  */
typedef int Py_ssize_t;
#endif

#include <sys/types.h>
#include <sys/socket.h>
#include <signal.h>

/*
 * As per
 * <http://pubs.opengroup.org/onlinepubs/007904875/basedefs/sys/socket.h.html
 * #tag_13_61_05>:
 *
 *     "To forestall portability problems, it is recommended that applications
 *     not use values larger than (2**31)-1 for the socklen_t type."
 */

#define SOCKLEN_MAX 0x7FFFFFFF

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
    Py_ssize_t sendmsg_result;
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

        size_t all_data_len = 0;

        /* First we need to know how big the buffer needs to be in order to
           have enough space for all of the messages. */
        while ( (item = PyIter_Next(iterator)) ) {
            int type, level;
            Py_ssize_t data_len;
            size_t prev_all_data_len;
            char *data;
            if (!PyArg_ParseTuple(
                        item, "iit#:sendmsg ancillary data (level, type, data)",
                        &level, &type, &data, &data_len)) {
                Py_DECREF(item);
                Py_DECREF(iterator);
                return NULL;
            }

            prev_all_data_len = all_data_len;
            all_data_len += CMSG_SPACE(data_len);

            Py_DECREF(item);

            if (all_data_len < prev_all_data_len) {
                Py_DECREF(iterator);
                PyErr_Format(PyExc_OverflowError,
                             "Too much msg_control to fit in a size_t: %zu",
                             prev_all_data_len);
                return NULL;
            }
        }

        Py_DECREF(iterator);
        iterator = NULL;

        /* Allocate the buffer for all of the ancillary elements, if we have
         * any.  */
        if (all_data_len) {
            if (all_data_len > SOCKLEN_MAX) {
                PyErr_Format(PyExc_OverflowError,
                             "Too much msg_control to fit in a socklen_t: %zu",
                             all_data_len);
                return NULL;
            }
            message_header.msg_control = malloc(all_data_len);
            if (!message_header.msg_control) {
                PyErr_NoMemory();
                return NULL;
            }
        } else {
            message_header.msg_control = NULL;
        }
        message_header.msg_controllen = (socklen_t) all_data_len;

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
            size_t data_size;
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
            data_size = CMSG_LEN(data_len);

            if (data_size > SOCKLEN_MAX) {
                Py_DECREF(item);
                Py_DECREF(iterator);
                free(message_header.msg_control);

                PyErr_Format(PyExc_OverflowError,
                             "CMSG_LEN(%d) > SOCKLEN_MAX", data_len);

                return NULL;
            }

            control_message->cmsg_len = (socklen_t) data_size;

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

    return Py_BuildValue("n", sendmsg_result);
}

static PyObject *sendmsg_recvmsg(PyObject *self, PyObject *args, PyObject *keywds) {
    int fd = -1;
    int flags = 0;
    int maxsize = 8192;
    int cmsg_size = 4*1024;
    size_t cmsg_space;
    Py_ssize_t recvmsg_result;

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

    cmsg_space = CMSG_SPACE(cmsg_size);

    /* overflow check */
    if (cmsg_space > SOCKLEN_MAX) {
        PyErr_Format(PyExc_OverflowError,
                     "CMSG_SPACE(cmsg_size) greater than SOCKLEN_MAX: %d",
                     cmsg_size);
        return NULL;
    }

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

    cmsgbuf = malloc(cmsg_space);

    if (!cmsgbuf) {
        free(iov[0].iov_base);
        PyErr_NoMemory();
        return NULL;
    }

    memset(cmsgbuf, 0, cmsg_space);
    message_header.msg_control = cmsgbuf;
    /* see above for overflow check */
    message_header.msg_controllen = (socklen_t) cmsg_space;

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
            (Py_ssize_t) (control_message->cmsg_len - sizeof(struct cmsghdr)));

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

