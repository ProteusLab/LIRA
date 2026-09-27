/* Host runtime: the same program compiled natively gives the reference output. */
#include "rt.h"
#include <stdlib.h>
#include <unistd.h>

void rt_write(const char *s, u64 n) { write(1, s, n); }
void rt_exit(int code) { exit(code); }
