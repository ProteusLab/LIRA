/* Minimal libc for valgrind's arm64 tests in the LIRA AArch64 simulator:
   Linux write/exit via SVC; float formats use integer arithmetic only. */
#ifndef LIRA_RT_H
#define LIRA_RT_H
#include <stddef.h>
#include <stdarg.h>
int printf(const char *fmt, ...);
int vprintf(const char *fmt, va_list ap);
int putchar(int c);
int puts(const char *s);
int fflush(void *f);
void *memset(void *d, int c, size_t n);
void *memcpy(void *d, const void *s, size_t n);
int memcmp(const void *a, const void *b, size_t n);
int strcmp(const char *a, const char *b);
size_t strlen(const char *s);
void *malloc(size_t n);
void *calloc(size_t n, size_t m);
void *memalign(size_t align, size_t n);
void free(void *p);
_Noreturn void exit(int code);
_Noreturn void abort(void);
_Noreturn void __assert_fail(const char *e, const char *f, int l);
#define stdout ((void *)1)
#define stderr ((void *)2)
#endif
