//
//  python-wrapper.c
//
//  Copyright © 2015 Apple Inc. All rights reserved.
//

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

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

int main(int argc, const char * argv[]) {
    
    // Update PATH and PYTHONPATH
    prependToPath("PATH", bin);
    prependToPath("PYTHONPATH", site);
    
    // Launch real python
    argv[0] = python;
    return execvp(python, (char* const*)argv);
}
