/* Host replacement for valgrind's tests/malloc.h. */
#include "../malloc.h"
#include <assert.h>

static void *memalign16(size_t n) {
  void *x = memalign(16, n);
  assert(x);
  return x;
}
