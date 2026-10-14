// This file is part of the uutils coreutils package.
// For the full copyright and license information, please view the LICENSE file.

/* MIT-licensed QEMU fixture. Only the unavailable TimeService IPC is replaced.
 */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
int32_t OH_TimeService_GetTimeZone(char *buffer, uint32_t length) {
  const char *zone = getenv("COREUTILS_QEMU_SYSTEM_ZONE");
  if (!zone || strlen(zone) >= length)
    return -1;
  memcpy(buffer, zone, strlen(zone) + 1);
  return 0;
}
