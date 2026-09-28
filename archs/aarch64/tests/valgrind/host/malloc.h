/* Host memalign for systems without <malloc.h> (macOS). */
#ifndef LIRA_VG_HOST_MALLOC_H
#define LIRA_VG_HOST_MALLOC_H
#include <stdlib.h>

static inline void *memalign(size_t align, size_t n) {
  void *p;
  return posix_memalign(&p, align, n) ? 0 : p;
}
#endif
