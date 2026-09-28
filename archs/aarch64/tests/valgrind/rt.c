#include "rt.h"

__asm__(".globl _start\n"
        "_start:\n"
        "  mov x29, #0\n"
        "  mov x30, #0\n"
        "  bl main\n"
        "  b exit\n");

static long sys3(long n, long a, long b, long c) {
  register long x8 __asm__("x8") = n;
  register long x0 __asm__("x0") = a;
  register long x1 __asm__("x1") = b;
  register long x2 __asm__("x2") = c;
  __asm__ __volatile__("svc #0" : "+r"(x0) : "r"(x8), "r"(x1), "r"(x2) : "memory");
  return x0;
}

/* Buffered stdout, flushed when full and at exit. */
static char obuf[4096];
static size_t olen;

int fflush(void *f) {
  (void)f;
  if (olen)
    sys3(64, 1, (long)obuf, (long)olen);
  olen = 0;
  return 0;
}

int putchar(int c) {
  if (olen == sizeof obuf)
    fflush(0);
  obuf[olen++] = (char)c;
  return c;
}

int puts(const char *s) {
  while (*s)
    putchar(*s++);
  putchar('\n');
  return 0;
}

_Noreturn void exit(int code) {
  fflush(0);
  sys3(93, code, 0, 0);
  for (;;) {}
}

_Noreturn void abort(void) { exit(134); }

_Noreturn void __assert_fail(const char *e, const char *f, int l) {
  printf("assertion failed: %s (%s:%d)\n", e, f, l);
  exit(134);
}

static void out_num(unsigned long long v, int base, int upper, int width,
                    char pad, int left, int neg) {
  char tmp[24];
  int n = 0;
  const char *digits = upper ? "0123456789ABCDEF" : "0123456789abcdef";
  do {
    tmp[n++] = digits[v % base];
    v /= base;
  } while (v);
  int len = n + neg;
  if (neg && pad == '0')
    putchar('-');
  if (!left)
    for (; len < width; width--)
      putchar(pad);
  if (neg && pad != '0')
    putchar('-');
  while (n)
    putchar(tmp[--n]);
  if (left)
    for (; len < width; width--)
      putchar(' ');
}

int vprintf(const char *fmt, va_list ap) {
  for (; *fmt; fmt++) {
    if (*fmt != '%') {
      putchar(*fmt);
      continue;
    }
    fmt++;
    int left = 0, width = 0, lng = 0;
    char pad = ' ';
    for (;; fmt++) {
      if (*fmt == '-')
        left = 1;
      else if (*fmt == '0')
        pad = '0';
      else
        break;
    }
    if (*fmt == '*') {
      width = va_arg(ap, int);
      fmt++;
    }
    while (*fmt >= '0' && *fmt <= '9')
      width = width * 10 + (*fmt++ - '0');
    while (*fmt == 'l' || *fmt == 'z') {
      lng++;
      fmt++;
    }
    switch (*fmt) {
    case 'd':
    case 'i': {
      long long v = lng ? va_arg(ap, long long) : va_arg(ap, int);
      int neg = v < 0;
      out_num(neg ? -(unsigned long long)v : (unsigned long long)v, 10, 0,
              width, pad, left, neg);
      break;
    }
    case 'u':
    case 'x':
    case 'X': {
      unsigned long long v =
          lng ? va_arg(ap, unsigned long long) : va_arg(ap, unsigned);
      out_num(v, *fmt == 'u' ? 10 : 16, *fmt == 'X', width, pad, left, 0);
      break;
    }
    case 'p':
      putchar('0');
      putchar('x');
      out_num((unsigned long long)va_arg(ap, void *), 16, 0, 0, ' ', 0, 0);
      break;
    case 'c':
      putchar(va_arg(ap, int));
      break;
    case 's': {
      const char *s = va_arg(ap, const char *);
      int len = (int)strlen(s);
      if (!left)
        for (; len < width; width--)
          putchar(' ');
      while (*s)
        putchar(*s++);
      if (left)
        for (; len < width; width--)
          putchar(' ');
      break;
    }
    case '%':
      putchar('%');
      break;
    default:
      putchar('%');
      putchar(*fmt);
    }
  }
  return 0;
}

int printf(const char *fmt, ...) {
  va_list ap;
  va_start(ap, fmt);
  vprintf(fmt, ap);
  va_end(ap);
  return 0;
}

void *memset(void *d, int c, size_t n) {
  unsigned char *p = d;
  while (n--)
    *p++ = (unsigned char)c;
  return d;
}

void *memcpy(void *d, const void *s, size_t n) {
  unsigned char *p = d;
  const unsigned char *q = s;
  while (n--)
    *p++ = *q++;
  return d;
}

int memcmp(const void *a, const void *b, size_t n) {
  const unsigned char *p = a, *q = b;
  for (; n; n--, p++, q++)
    if (*p != *q)
      return *p - *q;
  return 0;
}

int strcmp(const char *a, const char *b) {
  for (; *a && *a == *b; a++, b++) {
  }
  return (unsigned char)*a - (unsigned char)*b;
}

size_t strlen(const char *s) {
  size_t n = 0;
  while (s[n])
    n++;
  return n;
}

/* Bump allocator over a static heap; free is a no-op. */
static unsigned char heap[16 << 20] __attribute__((aligned(4096)));
static size_t heap_top;

void *memalign(size_t align, size_t n) {
  size_t p = (heap_top + align - 1) & ~(align - 1);
  if (p + n > sizeof heap)
    return 0;
  heap_top = p + n;
  return heap + p;
}

void *malloc(size_t n) { return memalign(16, n); }

void *calloc(size_t n, size_t m) { return memset(malloc(n * m), 0, n * m); }

void free(void *p) { (void)p; }
