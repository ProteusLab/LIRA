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

/* Floating point formats (%e, %f, %g) of a double, printed exactly as glibc
   does: the exact decimal expansion of the value, rounded half to even.
   Integer arithmetic only. */

/* Big natural number, 32-bit limbs, least significant first */
static unsigned big[100];
static int big_n;

static void big_mul(unsigned k) {
  unsigned long long carry = 0;
  for (int i = 0; i < big_n; i++) {
    carry += (unsigned long long)big[i] * k;
    big[i] = (unsigned)carry;
    carry >>= 32;
  }
  if (carry)
    big[big_n++] = (unsigned)carry;
}

/* Decimal digits of `big` (destroyed) into `out`, most significant first */
static int big_decimal(char *out) {
  char rev[1000];
  int len = 0;
  while (big_n) {
    unsigned long long rem = 0;
    for (int i = big_n - 1; i >= 0; i--) {
      unsigned long long cur = rem << 32 | big[i];
      big[i] = (unsigned)(cur / 1000000000);
      rem = cur % 1000000000;
    }
    while (big_n && big[big_n - 1] == 0)
      big_n--;
    for (int k = 0; k < 9; k++) {
      rev[len++] = (char)('0' + rem % 10);
      rem /= 10;
    }
  }
  while (len > 1 && rev[len - 1] == '0')
    len--;
  for (int i = 0; i < len; i++)
    out[i] = rev[len - 1 - i];
  return len;
}

/* |value| = 0.D[0] D[1] ... * 10^(point); zero has no digits */
struct decimal {
  char d[1100];
  int len;
  int point;
};

static void decimal_of(unsigned long long bits, struct decimal *x) {
  unsigned long long frac = bits & ((1ULL << 52) - 1);
  int exp = (int)((bits >> 52) & 0x7ff);
  unsigned long long mant = exp ? frac | 1ULL << 52 : frac;
  int e2 = exp ? exp - 1075 : -1074;
  x->len = 0;
  x->point = 0;
  if (mant == 0)
    return;
  big[0] = (unsigned)mant;
  big[1] = (unsigned)(mant >> 32);
  big_n = big[1] ? 2 : 1;
  int scale = 0;
  if (e2 >= 0) {
    for (; e2 >= 16; e2 -= 16)
      big_mul(1U << 16);
    big_mul(1U << e2);
  } else {
    scale = -e2;
    int k = scale;
    for (; k >= 13; k -= 13)
      big_mul(1220703125U); /* 5^13 */
    unsigned p5 = 1;
    while (k--)
      p5 *= 5;
    big_mul(p5);
  }
  x->len = big_decimal(x->d);
  x->point = x->len - scale;
}

/* Keep `nd` digits (nd may be <= 0), rounding half to even */
static void decimal_round(struct decimal *x, int nd) {
  if (nd >= x->len)
    return;
  int up = 0;
  if (nd >= 0) {
    char first = x->d[nd];
    int rest = 0;
    for (int i = nd + 1; i < x->len; i++)
      rest |= x->d[i] != '0';
    char prev = nd > 0 ? x->d[nd - 1] : '0';
    up = first > '5' || (first == '5' && (rest || (prev - '0') & 1));
  }
  x->len = nd > 0 ? nd : 0;
  if (!up)
    return;
  int i = x->len - 1;
  for (; i >= 0 && x->d[i] == '9'; i--)
    x->d[i] = '0';
  if (i >= 0) {
    x->d[i]++;
  } else { /* carry out of the top digit (or nothing kept) */
    for (int k = x->len; k > 0; k--)
      x->d[k] = x->d[k - 1];
    x->d[0] = '1';
    x->len++;
    x->point++;
  }
}

static char digit_at(const struct decimal *x, int i) {
  return i >= 0 && i < x->len ? x->d[i] : '0';
}

/* Format |value| without the sign; returns the length */
static int format_f(const struct decimal *src, int prec, char *out) {
  struct decimal x = *src;
  decimal_round(&x, x.point + prec);
  int n = 0;
  if (x.point <= 0)
    out[n++] = '0';
  for (int i = 0; i < x.point; i++)
    out[n++] = digit_at(&x, i);
  if (prec > 0) {
    out[n++] = '.';
    for (int i = 0; i < prec; i++)
      out[n++] = digit_at(&x, x.point + i);
  }
  return n;
}

static int format_e(const struct decimal *src, int prec, char *out) {
  struct decimal x = *src;
  decimal_round(&x, prec + 1);
  int e = x.len ? x.point - 1 : 0;
  int n = 0;
  out[n++] = digit_at(&x, 0);
  if (prec > 0) {
    out[n++] = '.';
    for (int i = 1; i <= prec; i++)
      out[n++] = digit_at(&x, i);
  }
  out[n++] = 'e';
  out[n++] = e < 0 ? '-' : '+';
  if (e < 0)
    e = -e;
  char tmp[8];
  int t = 0;
  do {
    tmp[t++] = (char)('0' + e % 10);
    e /= 10;
  } while (e);
  if (t < 2)
    tmp[t++] = '0';
  while (t)
    out[n++] = tmp[--t];
  return n;
}

static int format_g(const struct decimal *src, int prec, char *out) {
  if (prec == 0)
    prec = 1;
  struct decimal x = *src;
  decimal_round(&x, prec);
  int e = x.len ? x.point - 1 : 0;
  int n = (e < prec && e >= -4) ? format_f(src, prec - 1 - e, out)
                                : format_e(src, prec - 1, out);
  /* drop trailing zeros of the fraction (and a trailing point) */
  int epos = n;
  for (int i = 0; i < n; i++)
    if (out[i] == 'e')
      epos = i;
  int dot = -1;
  for (int i = 0; i < epos; i++)
    if (out[i] == '.')
      dot = i;
  if (dot < 0)
    return n;
  int end = epos;
  while (end > dot + 1 && out[end - 1] == '0')
    end--;
  if (end == dot + 1)
    end = dot;
  int k = end;
  for (int i = epos; i < n; i++)
    out[k++] = out[i];
  return k;
}

static void out_double(unsigned long long bits, char conv, int prec, int width,
                       char pad, int left) {
  static char buf[1200];
  int n = 0;
  if (bits >> 63)
    buf[n++] = '-';
  int body = n;
  if (((bits >> 52) & 0x7ff) == 0x7ff) {
    const char *s = bits & ((1ULL << 52) - 1) ? "nan" : "inf";
    while (*s)
      buf[n++] = *s++;
    pad = ' ';
  } else {
    static struct decimal x;
    decimal_of(bits, &x);
    if (prec < 0)
      prec = 6;
    n += conv == 'f'   ? format_f(&x, prec, buf + n)
         : conv == 'e' ? format_e(&x, prec, buf + n)
                       : format_g(&x, prec, buf + n);
  }
  if (!left && pad == '0') {
    for (int i = 0; i < body; i++)
      putchar(buf[i]);
    for (; n < width; width--)
      putchar('0');
    for (int i = body; i < n; i++)
      putchar(buf[i]);
    return;
  }
  if (!left)
    for (; n < width; width--)
      putchar(' ');
  for (int i = 0; i < n; i++)
    putchar(buf[i]);
  if (left)
    for (; n < width; width--)
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
    int prec = -1;
    if (*fmt == '.') {
      fmt++;
      prec = 0;
      if (*fmt == '*') {
        prec = va_arg(ap, int);
        fmt++;
      }
      while (*fmt >= '0' && *fmt <= '9')
        prec = prec * 10 + (*fmt++ - '0');
    }
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
    case 'e':
    case 'f':
    case 'g': {
      union {
        double d;
        unsigned long long u;
      } v;
      v.d = va_arg(ap, double);
      out_double(v.u, *fmt, prec, width, pad, left);
      break;
    }
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
