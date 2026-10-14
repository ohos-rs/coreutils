// This file is part of the uutils coreutils package.
// For the full copyright and license information, please view the LICENSE file.

/* MIT-licensed native SDK ABI and C stdio test fixture. */
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/statfs.h>
#include <time.h>
#include <unistd.h>
#include <utmpx.h>

int main(int argc, char **argv) {
  if (argc < 2 || getuid() == 0)
    return 70;
  if (!strcmp(argv[1], "abi")) {
    printf("{\"pointer\":%zu,\"utmpx\":%zu,\"time_t\":%zu,\"timeval\":%zu,"
           "\"timespec\":%zu,\"stat\":%zu,\"statfs\":%zu,\"ut_tv\":%zu,\"ut_"
           "user\":%zu}\n",
           sizeof(void *), sizeof(struct utmpx), sizeof(time_t),
           sizeof(struct timeval), sizeof(struct timespec), sizeof(struct stat),
           sizeof(struct statfs), offsetof(struct utmpx, ut_tv),
           offsetof(struct utmpx, ut_user));
    return 0;
  }
  if (!strcmp(argv[1], "clock")) {
    struct timespec boot;
    if (clock_gettime(CLOCK_BOOTTIME, &boot))
      return 71;
    printf("%lld %lld\n", (long long)time(NULL), (long long)boot.tv_sec);
    return 0;
  }
  if (!strcmp(argv[1], "record") && argc == 5) {
    struct timespec boot;
    if (clock_gettime(CLOCK_BOOTTIME, &boot))
      return 71;
    FILE *file = fopen(argv[2], "wb");
    if (!file)
      return 72;
    if (fchmod(fileno(file), 0600))
      return 73;
    struct utmpx records[2] = {0};
    records[0].ut_type = BOOT_TIME;
    records[0].ut_tv.tv_sec = time(NULL) - boot.tv_sec;
    records[1].ut_type = USER_PROCESS;
    records[1].ut_pid = (pid_t)strtol(argv[3], NULL, 10);
    records[1].ut_tv.tv_sec = time(NULL);
    snprintf(records[1].ut_user, sizeof(records[1].ut_user), "qemu-user");
    const char *tty = !strncmp(argv[4], "/dev/", 5) ? argv[4] + 5 : argv[4];
    snprintf(records[1].ut_line, sizeof(records[1].ut_line), "%s", tty);
    int valid = fwrite(records, sizeof(records[0]), 2, file) == 2;
    return fclose(file) || !valid ? 74 : 0;
  }
  if (!strcmp(argv[1], "input")) {
    if (fgetc(stdin) == EOF)
      return 75;
    off_t offset = lseek(STDIN_FILENO, 0, SEEK_CUR);
    if (offset < 0)
      return 76;
    printf("%lld\n", (long long)offset);
    return 0;
  }
  FILE *stream;
  if (!strcmp(argv[1], "stdout") || !strcmp(argv[1], "stdout-buffered")) {
    stream = stdout;
    if (!strcmp(argv[1], "stdout-buffered") &&
        setvbuf(stream, NULL, _IOFBF, BUFSIZ))
      return 77;
  } else if (!strcmp(argv[1], "stderr")) {
    stream = stderr;
  } else {
    return 78;
  }
  fputs("first\n", stream);
  const char *ready = getenv("COREUTILS_PROBE_READY_FD");
  if (!ready || write(atoi(ready), "R", 1) != 1)
    return 79;
  sleep(10);
  fputs("second\n", stream);
  return 0;
}
