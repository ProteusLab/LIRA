/* Integer workload exercising the A64 base instructions described in LIRA.
 * Output must be identical when run natively and in the generated simulator. */
#include "rt.h"

typedef signed char i8;
typedef short i16;
typedef unsigned char u8;
typedef unsigned short u16;

static u64 rng_state = 0x9E3779B97F4A7C15UL;
static u64 xorshift(void) {
  u64 x = rng_state;
  x ^= x << 13;
  x ^= x >> 7;
  x ^= x << 17;
  return rng_state = x;
}

__attribute__((noinline)) static u64 fib(u64 n) { return n < 2 ? n : fib(n - 1) + fib(n - 2); }

static u64 sieve(void) {
  static u8 comp[20000];
  u64 count = 0;
  for (u64 i = 2; i < sizeof(comp); i++) {
    if (comp[i])
      continue;
    count++;
    for (u64 j = i * i; j < sizeof(comp); j += i)
      comp[j] = 1;
  }
  return count;
}

static void quicksort(i64 *a, i64 lo, i64 hi) {
  while (lo < hi) {
    i64 p = a[(lo + hi) / 2], i = lo, j = hi;
    while (i <= j) {
      while (a[i] < p) i++;
      while (a[j] > p) j--;
      if (i <= j) {
        i64 t = a[i];
        a[i++] = a[j];
        a[j--] = t;
      }
    }
    if (j - lo < hi - i) {
      quicksort(a, lo, j);
      lo = i;
    } else {
      quicksort(a, i, hi);
      hi = j;
    }
  }
}

static u32 crc32(const u8 *p, u64 n) {
  static u32 table[256];
  if (!table[1])
    for (u32 i = 0; i < 256; i++) {
      u32 c = i;
      for (int k = 0; k < 8; k++)
        c = c & 1 ? 0xEDB88320u ^ (c >> 1) : c >> 1;
      table[i] = c;
    }
  u32 crc = ~0u;
  while (n--)
    crc = table[(crc ^ *p++) & 0xff] ^ (crc >> 8);
  return ~crc;
}

static void division(void) {
  static const i64 vals[] = {0, 1, -1, 7, -7, 1000000007, -123456789012345L,
                             0x7fffffffffffffffL, (i64)0x8000000000000000UL, 3};
  u64 acc = 0;
  for (int i = 0; i < 10; i++)
    for (int j = 0; j < 10; j++) {
      i64 a = vals[i], b = vals[j];
      if (b == 0 || (b == -1 && a == (i64)0x8000000000000000UL))
        continue;
      acc = acc * 31 + (u64)(a / b) + (u64)(a % b) * 7;
      acc ^= (u64)a / (u64)b + (u64)a % (u64)b;
      i32 a32 = (i32)a, b32 = (i32)b;
      if (b32 != 0 && !(b32 == -1 && a32 == (i32)0x80000000))
        acc += (u32)(a32 / b32) ^ (u32)(a32 % b32) ^ ((u32)a32 / (u32)b32);
    }
  out_hex("division", acc);
}

static void mul_high(void) {
  u64 acc = 0;
  for (int i = 0; i < 64; i++) {
    u64 a = xorshift(), b = xorshift();
    unsigned __int128 u = (unsigned __int128)a * b;
    __int128 s = (__int128)(i64)a * (i64)b;
    acc += (u64)(u >> 64) ^ (u64)(s >> 64) ^ (u64)u;
    acc += (u64)((i64)(i32)a * (i64)(i32)b) + (u64)(u32)a * (u32)b;  /* smull / umull */
  }
  out_hex("mulhigh", acc);
}

static void bits(void) {
  u64 acc = 0;
  for (int i = 0; i < 200; i++) {
    u64 x = xorshift() >> (i % 64);
    u32 w = (u32)x;
    acc += x ? (u64)__builtin_clzl(x) : 64;
    acc += x ? (u64)__builtin_ctzl(x) : 64;
    acc += (u64)__builtin_popcountl(x) + __builtin_popcount(w);
    acc ^= __builtin_bswap64(x) + __builtin_bswap32(w) + __builtin_bswap16((u16)w);
    acc += (x << (i % 63)) | (x >> (64 - i % 63 - 1));      /* rotates */
    acc += (u64)(w >> 3 & 0x7ff) + (u64)((i64)(x << 11) >> 40);  /* ubfx / sbfx */
    acc += __builtin_clrsbl((i64)x) + __builtin_clrsb((i32)w);
    acc = (acc & ~0xff0UL) | ((x & 0xff) << 4);                /* bfi */
  }
  out_hex("bits", acc);
}

struct packed {
  unsigned a : 3;
  signed b : 7;
  unsigned c : 13;
  signed d : 9;
};

static void bitfields(void) {
  struct packed p[16];
  u64 acc = 0;
  for (int i = 0; i < 16; i++) {
    u64 r = xorshift();
    p[i].a = r;
    p[i].b = r >> 3;
    p[i].c = r >> 10;
    p[i].d = r >> 23;
  }
  for (int i = 0; i < 16; i++)
    acc = acc * 131 + p[i].a + (u64)(i64)p[i].b + p[i].c + (u64)(i64)p[i].d;
  out_hex("bitfields", acc);
}

static void narrow_loads(void) {
  static i8 s8[64];
  static u8 u8a[64];
  static i16 s16[64];
  static u16 u16a[64];
  static i32 s32[64];
  for (int i = 0; i < 64; i++) {
    u64 r = xorshift();
    s8[i] = (i8)r;
    u8a[i] = (u8)(r >> 8);
    s16[i] = (i16)(r >> 16);
    u16a[i] = (u16)(r >> 24);
    s32[i] = (i32)(r >> 32);
  }
  i64 acc = 0;
  for (int i = 0; i < 64; i++)
    acc = acc * 3 + s8[i] + u8a[i] + s16[i] + u16a[i] + s32[i] + s32[63 - i] * (i64)s8[i];
  out_hex("narrow", (u64)acc);
}

static i64 op_add(i64 a, i64 b) { return a + b; }
static i64 op_sub(i64 a, i64 b) { return a - b; }
static i64 op_mul(i64 a, i64 b) { return a * b; }
static i64 op_xor(i64 a, i64 b) { return a ^ b; }

__attribute__((noinline)) static i64 dispatch(int k, i64 a, i64 b) {
  switch (k) {  /* dense switch: jump table + BR */
  case 0: return a + 1;
  case 1: return b - 3;
  case 2: return a * 5 + b;
  case 3: return a >> 7;
  case 4: return (u64)b >> 9;
  case 5: return a < b ? a : b;
  case 6: return a > b ? a - b : b - a;
  case 7: return a == 0 ? 17 : a;
  case 8: return ~a & b;
  case 9: return a | 0x5555;
  default: return 42;
  }
}

static void control(void) {
  i64 (*ops[4])(i64, i64) = {op_add, op_sub, op_mul, op_xor};
  i64 acc = 0;
  for (int i = 0; i < 300; i++) {
    i64 a = (i64)xorshift(), b = (i64)xorshift() >> (i % 60);
    acc = ops[i & 3](acc, dispatch(i % 12, a, b));  /* BLR */
    acc += a < 0 ? -a : a;                           /* cneg */
    acc += (u32)a > (u32)b;                          /* cset */
    acc += (a & 0x100) ? 1 : 0;                      /* tbz / tbnz */
    if ((i32)b == 0)                                 /* cbz */
      acc++;
  }
  out_hex("control", (u64)acc);
}

struct big {
  u64 v[7];
  u32 w;
  u16 h;
  u8 b;
};

__attribute__((noinline)) static struct big mix(struct big x, int k) {
  for (int i = 0; i < 7; i++)
    x.v[i] = x.v[i] * 3 + (u64)k;
  x.w += k;
  x.h ^= k;
  x.b -= k;
  return x;
}

static void structs(void) {
  struct big a;
  memset(&a, 0, sizeof(a));
  for (int i = 0; i < 7; i++)
    a.v[i] = xorshift();
  for (int k = 0; k < 20; k++)
    a = mix(a, k);
  struct big c;
  memcpy(&c, &a, sizeof(c));
  u64 acc = c.w + c.h + c.b;
  for (int i = 0; i < 7; i++)
    acc = acc * 7 ^ c.v[i];
  out_hex("structs", acc);
}

static void strings(void) {
  char buf[128];
  const char *msg = "The quick brown fox jumps over the lazy dog";
  u64 n = rt_strlen(msg);
  for (u64 i = 0; i < n; i++)
    buf[i] = msg[n - 1 - i];
  buf[n] = 0;
  u64 h = 5381;
  for (u64 i = 0; buf[i]; i++)
    h = h * 33 + (u8)buf[i];
  out_hex("strings", h);
  out_dec("strcmp", memcmp(msg, buf, n));
}

static void arith32(void) {
  u32 a = 0xdeadbeef, b = 0x12345678;
  i32 s = -100;
  u64 acc = 0;
  for (int i = 0; i < 500; i++) {
    a = a * 1664525u + 1013904223u;
    b ^= a >> 7;
    s = s * 3 - (i32)b;
    acc += a + (u64)b * 3 + (u64)(i64)s + (u64)(a < b) + (u64)(s < 0);
    acc += (u64)(i64)(i32)(a >> (i & 31)) + (u32)(b << (i & 31));
  }
  out_hex("arith32", acc);
}

int main(void) {
  out_str("integer workload\n");
  out_dec("fib", (i64)fib(24));
  out_dec("primes", (i64)sieve());

  static i64 arr[500];
  for (int i = 0; i < 500; i++)
    arr[i] = (i64)xorshift() >> (i % 40);
  quicksort(arr, 0, 499);
  u64 sorted = 1, sum = 0;
  for (int i = 1; i < 500; i++) {
    sorted &= arr[i - 1] <= arr[i];
    sum = sum * 7 + (u64)arr[i];
  }
  out_dec("sorted", (i64)sorted);
  out_hex("sortsum", sum);

  static u8 data[4096];
  for (int i = 0; i < 4096; i++)
    data[i] = (u8)xorshift();
  out_hex("crc32", crc32(data, sizeof(data)));

  division();
  mul_high();
  bits();
  bitfields();
  narrow_loads();
  control();
  structs();
  strings();
  arith32();
  return (int)(sum & 0x7f);
}
