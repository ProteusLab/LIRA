#include <stdint.h>

uint64_t add_32(uint64_t i0, uint64_t i1) { return (i0 + i1) & 4294967295ul; }
uint64_t lsr_32(uint64_t i0, uint64_t i1) { return (i1 >= 32 ? 0 : (i0 >> i1)) & 4294967295ul; }
uint64_t extract_low_32_to_5(uint64_t i0) { return (i0) & 31ul; }
uint64_t extend_zero_5_to_32(uint64_t i0) { return (i0) & 4294967295ul; }
uint64_t extend_zero_1_to_32(uint64_t i0) { return (i0) & 4294967295ul; }
uint64_t lsl_32(uint64_t i0, uint64_t i1) { return (i1 >= 32 ? 0 : (i0 << i1)) & 4294967295ul; }
uint64_t orr_32(uint64_t i0, uint64_t i1) { return (i0 | i1) & 4294967295ul; }
uint64_t and_32(uint64_t i0, uint64_t i1) { return (i0 & i1) & 4294967295ul; }
uint64_t eq_32(uint64_t i0, uint64_t i1) { return (i0 == i1 ? 1 : 0) & 4294967295ul; }
uint64_t select_32(uint64_t i0, uint64_t i1, uint64_t i2) { return (i0 == 1 ? i1 : i2) & 4294967295ul; }
uint64_t extract_low_32_to_1(uint64_t i0) { return (i0) & 1ul; }
uint64_t extend_zero_1_to_13(uint64_t i0) { return (i0) & 8191ul; }
uint64_t extend_zero_13_to_32(uint64_t i0) { return (i0) & 4294967295ul; }
uint64_t extract_low_32_to_6(uint64_t i0) { return (i0) & 63ul; }
uint64_t extend_zero_6_to_13(uint64_t i0) { return (i0) & 8191ul; }
uint64_t extract_low_32_to_4(uint64_t i0) { return (i0) & 15ul; }
uint64_t extend_zero_4_to_13(uint64_t i0) { return (i0) & 8191ul; }
uint64_t extract_low_32_to_13(uint64_t i0) { return (i0) & 8191ul; }
uint64_t extend_sign_13_to_32(uint64_t i0) { return (uint64_t)((int64_t)(i0 << 51) >> 19) >> 32; }
uint64_t extract_low_32_to_12(uint64_t i0) { return (i0) & 4095ul; }
uint64_t extend_sign_12_to_32(uint64_t i0) { return (uint64_t)((int64_t)(i0 << 52) >> 20) >> 32; }
uint64_t extract_low_32_to_16(uint64_t i0) { return (i0) & 65535ul; }
uint64_t extract_low_32_to_7(uint64_t i0) { return (i0) & 127ul; }
uint64_t extend_zero_7_to_12(uint64_t i0) { return (i0) & 4095ul; }
uint64_t extend_zero_12_to_32(uint64_t i0) { return (i0) & 4294967295ul; }
uint64_t extend_zero_5_to_12(uint64_t i0) { return (i0) & 4095ul; }
uint64_t extend_sign_16_to_32(uint64_t i0) { return (uint64_t)((int64_t)(i0 << 48) >> 16) >> 32; }
uint64_t extend_zero_16_to_32(uint64_t i0) { return (i0) & 4294967295ul; }
