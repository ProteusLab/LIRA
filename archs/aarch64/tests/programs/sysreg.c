/* System registers and operations a Linux EL0 process may use: TPIDR_EL0,
 * CTR_EL0, DCZID_EL0 with DC ZVA, the virtual counter, PSTATE.DIT/SSBS, cache
 * maintenance. The guest build uses the instructions; the host build
 * (whose OS may reserve or trap them) emulates the same effects. Only
 * facts that do not depend on the CPU are printed.
 * guest-flags: -march=armv8.5-a+ssbs -DUSE_SYSREGS
 */
#include "rt.h"

typedef unsigned char u8;

#ifdef USE_SYSREGS
#define MRS(reg)                                                               \
  ({                                                                           \
    u64 v_;                                                                    \
    __asm__ volatile("mrs %0, " reg : "=r"(v_));                               \
    v_;                                                                        \
  })
#define MSR(reg, v) __asm__ volatile("msr " reg ", %0" : : "r"((u64)(v)))

static u64 tpidr_roundtrip(u64 v) {
  MSR("tpidr_el0", v);
  return MRS("tpidr_el0");
}
static u64 zva_bytes(void) { return 4UL << (MRS("dczid_el0") & 15); }
static u64 dline_bytes(void) { return 4UL << ((MRS("ctr_el0") >> 16) & 15); }
static void zva(void *p) { __asm__ volatile("dc zva, %0" : : "r"(p) : "memory"); }
static u64 counter(void) { return MRS("cntvct_el0"); }
static u64 dit(u64 on) {
  if (on)
    __asm__ volatile("msr dit, #1");
  else
    __asm__ volatile("msr dit, #0");
  return (MRS("dit") >> 24) & 1;
}
static u64 ssbs(u64 on) {
  MSR("ssbs", on << 12);
  return (MRS("ssbs") >> 12) & 1;
}
static void clean(void *p) {
  __asm__ volatile("dc cvau, %0\n dc civac, %0\n ic ivau, %0\n dsb ish\n isb"
                   :
                   : "r"(p)
                   : "memory");
}
#else
static u64 tpidr;
static u64 tpidr_roundtrip(u64 v) { return tpidr = v; }
static u64 zva_bytes(void) { return 64; }
static u64 dline_bytes(void) { return 64; }
static void zva(void *p) { memset((void *)((u64)p & ~63UL), 0, 64); }
static u64 ticks;
static u64 counter(void) { return ticks += 1000; }
static u64 dit(u64 on) { return on; }
static u64 ssbs(u64 on) { return on; }
static void clean(void *p) { (void)p; }
#endif

static u8 buf[1024] __attribute__((aligned(256)));

int main(void) {
  u64 ok = 0;
  for (u64 i = 0; i < 100; i++)
    ok += tpidr_roundtrip(i * 0x9E3779B97F4A7C15UL) == i * 0x9E3779B97F4A7C15UL;
  out_dec("tpidr", ok);

  /* DC ZVA zeroes exactly the naturally aligned block of DCZID_EL0's size */
  u64 zb = zva_bytes(), zeroed = 0, kept = 0;
  for (u64 i = 0; i < sizeof(buf); i++)
    buf[i] = (u8)(i | 1);
  zva(buf + 256 + zb / 2);
  for (u64 i = 0; i < sizeof(buf); i++) {
    int in_block = i >= 256 && i < 256 + zb;
    zeroed += in_block && buf[i] == 0;
    kept += !in_block && buf[i] == (u8)(i | 1);
  }
  out_dec("zva_exact", zeroed == zb && kept == sizeof(buf) - zb);
  out_dec("zva_block_ok", zb >= 16 && zb <= 2048);
  out_dec("dline_ok", dline_bytes() >= 16);

  u64 t0 = counter();
  volatile u64 sink = 0;
  for (int i = 0; i < 1000; i++)
    sink += i;
  out_dec("counter_increases", counter() > t0);

  out_dec("dit", dit(1) * 2 + dit(0));
  out_dec("ssbs", ssbs(1) * 2 + ssbs(0));
  clean(buf);
  out_dec("done", 1);
  return 0;
}
