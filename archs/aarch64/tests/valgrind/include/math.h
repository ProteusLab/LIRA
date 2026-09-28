#include "rt.h"
#define isnan(x) __builtin_isnan(x)
#define isinf(x) __builtin_isinf(x)
#define isnormal(x) __builtin_isnormal(x)
#define isfinite(x) __builtin_isfinite(x)
#define signbit(x) __builtin_signbit(x)
#define fabs(x) __builtin_fabs(x)
#define INFINITY __builtin_inf()
#define NAN __builtin_nan("")
