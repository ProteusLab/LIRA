/* Tiny runtime shared by the guest (simulator) and host builds. */
#ifndef RT_H
#define RT_H

typedef unsigned long u64;
typedef long i64;
typedef unsigned int u32;
typedef int i32;

void rt_write(const char *s, u64 n);
void *memcpy(void *d, const void *s, u64 n);
void *memmove(void *d, const void *s, u64 n);
void *memset(void *d, int c, u64 n);
int memcmp(const void *a, const void *b, u64 n);
void rt_exit(int code);

static inline u64 rt_strlen(const char *s) {
  u64 n = 0;
  while (s[n])
    n++;
  return n;
}

static inline void out_str(const char *s) { rt_write(s, rt_strlen(s)); }

static inline void out_hex(const char *label, u64 v) {
  char buf[64];
  int n = 0;
  while (label[n]) {
    buf[n] = label[n];
    n++;
  }
  buf[n++] = '=';
  buf[n++] = '0';
  buf[n++] = 'x';
  for (int i = 60; i >= 0; i -= 4)
    buf[n++] = "0123456789abcdef"[(v >> i) & 15];
  buf[n++] = '\n';
  rt_write(buf, n);
}

static inline void out_dec(const char *label, i64 v) {
  char tmp[24];
  int n = 0;
  u64 u = v < 0 ? -(u64)v : (u64)v;
  do {
    tmp[n++] = '0' + u % 10;
    u /= 10;
  } while (u);
  out_str(label);
  out_str("=");
  if (v < 0)
    out_str("-");
  char rev[24];
  for (int i = 0; i < n; i++)
    rev[i] = tmp[n - 1 - i];
  rt_write(rev, n);
  out_str("\n");
}

int main(void);

#endif
