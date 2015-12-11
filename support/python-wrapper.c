//
//  python-wrapper.c
//
//  Copyright © 2015 Apple Inc. All rights reserved.
//

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <pwd.h>
#include <Python.h>

const char * const allowedUsernames[] = {
    "_calendar",
    "_devicemgr",
    "_teamsserver",
    "_xserverdocs"
};

const char* python = "/usr/bin/python2.7";
const char* bin = "/Applications/Server.app/Contents/ServerRoot/Library/CalendarServer/bin";
const char* site = "/Applications/Server.app/Contents/ServerRoot/Library/CalendarServer/lib/python2.7/site-packages";

// Prepend a path to the named environment variable
int prependToPath(const char* name, const char* prepend) {
    const char* old_value = getenv(name);
    char* new_value = NULL;
    if (old_value == NULL) {
        // No existing value - set to the prepend value
        size_t max_length = strlen(prepend) + 1;
        new_value = malloc(max_length);
        strlcpy(new_value, prepend, max_length);
    } else {
        // Existing value - so prepend with a ":" in between
        size_t max_length = strlen(old_value) + strlen(prepend) + 2;
        new_value = malloc(max_length);
        strlcpy(new_value, prepend, max_length);
        strlcat(new_value, ":", max_length);
        strlcat(new_value, old_value, max_length);
    }
    setenv(name, new_value, 1);
    free(new_value);
    return 0;
}

int uidIsAllowed() {
    // Returns 1 if we're root or any of the whitelisted users; 0 otherwise

    int uid = getuid();

    if (uid == 0) {
        // Always allow root
        return 1;

    } else {
        // Check the other whitelisted users
        int i, len;
        struct passwd* passwdInfo;

        len = sizeof(allowedUsernames) / sizeof(allowedUsernames[0]);
        for (i = 0; i < len; i++) {
            passwdInfo = getpwnam(allowedUsernames[i]);
            if (passwdInfo != NULL) {
                if (passwdInfo->pw_uid == uid) {
                    return 1;
                }
            }
        }
    }

    // No match
    return 0;
}

char *getCodeToExecute() {
    char *buffer = NULL;
    const char* filename = getenv("CS_EXECUTE_EMBEDDED");
    if (filename != NULL) {
        FILE *file;
        if ((file = fopen(filename, "r"))) {
            struct stat statbuf;
            if (fstat(fileno(file), &statbuf) == 0) {
                int size = statbuf.st_size;
                buffer = malloc((size+1) * sizeof(char));
                int num = fread(buffer, 1, size, file);
                if (num != size) {
                    free(buffer);
                    buffer = NULL;
                } else {
                    buffer[size] = 0;
                }
            }
            fclose(file);
        }
    }
    return buffer;
}

int main(int argc, const char * argv[]) {

    if (uidIsAllowed()) {
        // Update PATH and PYTHONPATH
        prependToPath("PATH", bin);
        prependToPath("PYTHONPATH", site);

        char *code = getCodeToExecute();
        if (code != NULL) {
            printf("Executing code:\n%s\n", code);
            Py_SetProgramName((char *)argv[0]);
            Py_Initialize();
            PyRun_SimpleString(code);
            Py_Finalize();
            return 0;
        } else {
            // Launch real python
            argv[0] = python;
            return execvp(python, (char* const*)argv);
        }
    } else {
        printf("You are not allowed to run this executable.\n");
        return 1;
    }
}
