/* Guest runtime: Linux AArch64 syscalls via SVC, served by the simulator. */
#include "rt.h"

static long sys3(long n, long a, long b, long c) {
  register long x8 __asm__("x8") = n;
  register long x0 __asm__("x0") = a;
  register long x1 __asm__("x1") = b;
  register long x2 __asm__("x2") = c;
  __asm__ volatile("svc #0" : "+r"(x0) : "r"(x8), "r"(x1), "r"(x2) : "memory");
  return x0;
}

void rt_write(const char *s, u64 n) { sys3(64, 1, (long)s, (long)n); }

void rt_exit(int code) {
  sys3(93, code, 0, 0);
  for (;;) {
  }
}

void *memcpy(void *d, const void *s, u64 n) {
  unsigned char *dd = d;
  const unsigned char *ss = s;
  for (u64 i = 0; i < n; i++)
    dd[i] = ss[i];
  return d;
}

void *memmove(void *d, const void *s, u64 n) {
  unsigned char *dd = d;
  const unsigned char *ss = s;
  if (dd < ss)
    for (u64 i = 0; i < n; i++)
      dd[i] = ss[i];
  else
    for (u64 i = n; i > 0; i--)
      dd[i - 1] = ss[i - 1];
  return d;
}

void *memset(void *d, int c, u64 n) {
  unsigned char *dd = d;
  for (u64 i = 0; i < n; i++)
    dd[i] = (unsigned char)c;
  return d;
}

int memcmp(const void *a, const void *b, u64 n) {
  const unsigned char *x = a, *y = b;
  for (u64 i = 0; i < n; i++)
    if (x[i] != y[i])
      return x[i] < y[i] ? -1 : 1;
  return 0;
}

void _start(void) { rt_exit(main()); }
