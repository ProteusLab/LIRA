/* Pointer authentication (FEAT_PAuth). The guest build signs and
 * authenticates with PAC*, AUT*, XPAC*, PACGA, BLRAA and LDRAA, and signs
 * every return address (-mbranch-protection=pac-ret); the host build uses
 * plain pointers. Only key-independent facts are printed.
 * guest-flags: -march=armv8.3-a -mbranch-protection=pac-ret -DUSE_PAUTH
 */
#include "rt.h"

#ifdef USE_PAUTH
#define SIGN(insn)                                                             \
  static u64 insn(u64 p, u64 m) {                                              \
    __asm__(#insn " %0, %1" : "+r"(p) : "r"(m));                               \
    return p;                                                                  \
  }
SIGN(pacia)
SIGN(pacib)
SIGN(pacda)
SIGN(pacdb)
SIGN(autia)
SIGN(autib)
SIGN(autda)
SIGN(autdb)

static u64 xpaci(u64 p) {
  __asm__("xpaci %0" : "+r"(p));
  return p;
}

static u64 xpacd(u64 p) {
  __asm__("xpacd %0" : "+r"(p));
  return p;
}

static u64 pacga(u64 a, u64 b) {
  u64 r;
  __asm__("pacga %0, %1, %2" : "=r"(r) : "r"(a), "r"(b));
  return r;
}

/* Call fn(x) through a pointer signed with key IA and modifier m */
static u64 call_signed(u64 (*fn)(u64), u64 x, u64 m) {
  register u64 x0 __asm__("x0") = x;
  u64 target = pacia((u64)fn, m);
  __asm__ volatile("blraa %1, %2"
                   : "+r"(x0)
                   : "r"(target), "r"(m)
                   : "x1", "x2", "x3", "x4", "x5", "x6", "x7", "x8", "x9", "x10",
                     "x11", "x12", "x13", "x14", "x15", "x16", "x17", "x30",
                     "memory", "cc");
  return x0;
}

/* Load through a data pointer signed with key DA and modifier 0 */
static u64 load_signed(const u64 *p) {
  u64 signed_p = pacda((u64)p, 0), v;
  __asm__("ldraa %0, [%1]" : "=r"(v) : "r"(signed_p) : "memory");
  return v;
}
#else
static u64 same(u64 p, u64 m) { return (void)m, p; }
#define pacia same
#define pacib same
#define pacda same
#define pacdb same
#define autia same
#define autib same
#define autda same
#define autdb same
static u64 xpaci(u64 p) { return p; }
static u64 xpacd(u64 p) { return p; }
static u64 pacga(u64 a, u64 b) { return (a ^ b) << 32; }
static u64 call_signed(u64 (*fn)(u64), u64 x, u64 m) { return (void)m, fn(x); }
static u64 load_signed(const u64 *p) { return *p; }
#endif

static u64 rng_state = 0x9E3779B97F4A7C15UL;

static u64 rnd(void) {
  rng_state ^= rng_state << 13;
  rng_state ^= rng_state >> 7;
  rng_state ^= rng_state << 17;
  return rng_state;
}

__attribute__((noinline)) static u64 square_plus_one(u64 x) { return x * x + 1; }

__attribute__((noinline)) static u64 depth(u64 n) {
  return n == 0 ? 0 : 1 + depth(n - 1); /* signed return addresses */
}

int main(void) {
  u64 roundtrip = 0, stripped = 0, tags = 0, generic = 0, calls = 0, loads = 0;
  static u64 cells[64];
  for (u64 i = 0; i < 64; i++)
    cells[i] = i * 0x0101010101010101UL;
  for (int i = 0; i < 2000; i++) {
    u64 p = rnd() & 0x0000fffffffffffcUL; /* user-space address */
    u64 m = rnd();
    u64 tag = rnd() & 0xff00000000000000UL; /* top-byte tag of a data pointer */
    roundtrip += autia(pacia(p, m), m) == p;
    roundtrip += autib(pacib(p, m), m) == p;
    roundtrip += autda(pacda(p | tag, m), m) == (p | tag);
    roundtrip += autdb(pacdb(p | tag, m), m) == (p | tag);
    stripped += xpaci(pacia(p, m)) == p;
    stripped += xpacd(pacdb(p | tag, m)) == (p | tag);
    tags += pacda(p | tag, m) >> 56 == tag >> 56;
    generic += (pacga(p, m) & 0xffffffffUL) == 0;
    calls += call_signed(square_plus_one, i, m) == (u64)i * i + 1;
    loads += load_signed(&cells[i % 64]) == (u64)(i % 64) * 0x0101010101010101UL;
  }
  out_dec("roundtrip", roundtrip);
  out_dec("stripped", stripped);
  out_dec("tags", tags);
  out_dec("generic", generic);
  out_dec("calls", calls);
  out_dec("loads", loads);
  out_dec("depth", depth(100));
  return 0;
}
