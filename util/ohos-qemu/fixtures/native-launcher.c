// This file is part of the uutils coreutils package.
// For the full copyright and license information, please view the LICENSE file.

/* MIT-licensed QEMU exec adapter. Static: foreign LD_PRELOAD cannot load here.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
static char *setting(const char *name) {
  const char *value = getenv(name);
  if (!value)
    value = "";
  char *arg = malloc(strlen(name) + strlen(value) + 2);
  if (!arg)
    _exit(70);
  sprintf(arg, "%s=%s", name, value);
  unsetenv(name);
  return arg;
}
int main(int argc, char **argv) {
  if (argc < 4)
    return 64;
  char **args = calloc((size_t)argc + 8, sizeof(char *));
  if (!args)
    return 70;
  args[0] = argv[1];
  args[1] = "-L";
  args[2] = argv[2];
  args[3] = "-E";
  args[4] = setting("LD_PRELOAD");
  args[5] = "-E";
  args[6] = setting("LD_LIBRARY_PATH");
  for (int i = 3; i < argc; ++i)
    args[i + 4] = argv[i];
  execv(args[0], args);
  perror("native QEMU launcher");
  return 71;
}
