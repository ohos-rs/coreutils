/* MIT-licensed test fixture. See the repository LICENSE. */
/* Observe real C stdio buffering through a pipe or a regular input file. */
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <time.h>
#include <utmpx.h>

int main(int argc, char **argv)
{
    if (argc != 2 || getuid() == 0) {
        return 70;
    }
    if (strcmp(argv[1], "uptime") == 0) {
        struct timespec startup;
        if (clock_gettime(CLOCK_BOOTTIME, &startup) != 0) {
            return 74;
        }
        printf("%lld\n", (long long)startup.tv_sec);
        return 0;
    }
    if (strcmp(argv[1], "utmpx-size") == 0) {
        printf("%zu\n", sizeof(struct utmpx));
        return 0;
    }
    if (strcmp(argv[1], "input") == 0) {
        if (fgetc(stdin) == EOF) {
            return 71;
        }
        off_t offset = lseek(STDIN_FILENO, 0, SEEK_CUR);
        if (offset < 0) {
            return 72;
        }
        printf("%lld\n", (long long)offset);
        return 0;
    }
    FILE *stream;
    if (strcmp(argv[1], "stdout") == 0 || strcmp(argv[1], "stdout-buffered") == 0) {
        stream = stdout;
        if (strcmp(argv[1], "stdout-buffered") == 0
            && setvbuf(stream, NULL, _IOFBF, BUFSIZ) != 0) {
            return 75;
        }
    } else if (strcmp(argv[1], "stderr") == 0) {
        stream = stderr;
    } else {
        return 73;
    }
    fputs("first\n", stream);
    usleep(1000000);
    fputs("second\n", stream);
    return 0;
}
