/* MOPS (FEAT_MOPS) copy and set sequences. The guest build uses CPY*, CPYF*
 * and SET*; the host build (which may lack MOPS) uses memmove, memcpy and
 * memset. Both print the same buffer checksums and final register values.
 * guest-flags: -march=armv8.8-a+mops -DUSE_MOPS
 */
#include "rt.h"

typedef unsigned char u8;

#ifdef USE_MOPS
/* Returns the final destination pointer; checks that the size is consumed. */
static u8 *copy(u8 *d, const u8 *s, u64 n) {
  __asm__ volatile("cpyp [%0]!, [%1]!, %2!\n"
                   "cpym [%0]!, [%1]!, %2!\n"
                   "cpye [%0]!, [%1]!, %2!"
                   : "+r"(d), "+r"(s), "+r"(n)
                   :
                   : "memory", "cc");
  return n == 0 ? d : 0;
}

static u8 *copy_forward(u8 *d, const u8 *s, u64 n) {
  __asm__ volatile("cpyfp [%0]!, [%1]!, %2!\n"
                   "cpyfm [%0]!, [%1]!, %2!\n"
                   "cpyfe [%0]!, [%1]!, %2!"
                   : "+r"(d), "+r"(s), "+r"(n)
                   :
                   : "memory", "cc");
  return n == 0 ? d : 0;
}

static u8 *set(u8 *d, u64 n, u8 v) {
  u64 x = v;
  __asm__ volatile("setp [%0]!, %1!, %2\n"
                   "setm [%0]!, %1!, %2\n"
                   "sete [%0]!, %1!, %2"
                   : "+r"(d), "+r"(n)
                   : "r"(x)
                   : "memory", "cc");
  return n == 0 ? d : 0;
}
#else
/* A CPY sequence ends with Xd past the copied bytes, or at the start when it
 * copies backward: the description does so when the source overlaps the
 * start of the destination (IsMemCpyForward) */
static u8 *copy(u8 *d, const u8 *s, u64 n) {
  memmove(d, s, n);
  return s < d && d < s + n ? d : d + n;
}
static u8 *copy_forward(u8 *d, const u8 *s, u64 n) { return (u8 *)memcpy(d, s, n) + n; }
static u8 *set(u8 *d, u64 n, u8 v) { return (u8 *)memset(d, v, n) + n; }
#endif

static u8 buf[4096];
static u64 rng_state = 0x2545F4914F6CDD1DUL;

static u64 rnd(void) {
  rng_state ^= rng_state << 13;
  rng_state ^= rng_state >> 7;
  rng_state ^= rng_state << 17;
  return rng_state;
}

static u64 checksum(void) {
  u64 h = 1469598103934665603UL;
  for (u64 i = 0; i < sizeof(buf); i++)
    h = (h ^ buf[i]) * 1099511628211UL;
  return h;
}

int main(void) {
  for (u64 i = 0; i < sizeof(buf); i++)
    buf[i] = (u8)(i * 7 + 3);
  i64 ends = 0;
  for (int step = 0; step < 3000; step++) {
    u64 kind = rnd() % 3, n = rnd() % 300;
    u64 d = rnd() % (sizeof(buf) - n), s = rnd() % (sizeof(buf) - n);
    u8 *end;
    if (kind == 0) {
      end = copy(buf + d, buf + s, n);                  /* may overlap */
    } else if (kind == 1) {
      if (d < s + n && s < d + n)                      /* forward copies must not overlap */
        continue;
      end = copy_forward(buf + d, buf + s, n);
    } else {
      end = set(buf + d, n, (u8)rnd());
    }
    ends += end - (buf + d);
    if (step % 250 == 0)
      out_hex("checksum", checksum());
  }
  out_hex("checksum", checksum());
  out_dec("bytes", ends);
  return 0;
}
