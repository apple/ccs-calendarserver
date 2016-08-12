
#include <string.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <stdio.h>

int main(int argc, char** argv) {
    int skt;
    struct sockaddr_un addr;
    char* pathname = argv[1];

    skt = socket(AF_UNIX, SOCK_STREAM, 0);
    if (-1 == skt) {
        perror("socket");
        return 1;
    }

    memset(&addr, 0, sizeof(struct sockaddr_un));

    int pathlen = strlen(pathname);
    if (pathlen >= sizeof(addr.sun_path)) {
        fprintf(stderr, "Path too long.\n");
        return 2;
    }
    addr.sun_family = AF_UNIX;
    addr.sun_len = pathlen + 1;
    strcpy(addr.sun_path, pathname);

    if (bind(skt, (struct sockaddr*) &addr, sizeof(addr))) {
        perror("bind");
        return 4;
    }

    return 0;
}
