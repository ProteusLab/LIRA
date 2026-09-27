# AArch64 (A64) in LIRA

LIRA description of the A64 base integer instruction set, generated from the
Arm machine-readable specification (`ISA_A64_xml_A_profile-2026-06_mc`).

```bash
# from the repository root
python -m archs.aarch64.gen [--xml <ISA_A64_xml dir>] [--output archs/aarch64/aarch64.yaml]
python -m pytest archs/aarch64/tests
```

The output is `aarch64.yaml`: 222 encodings, 83 mnemonics.

| Group | Mnemonics |
|---|---|
| add/sub | ADD ADDS SUB SUBS (imm, shifted reg, extended reg), ADC ADCS SBC SBCS |
| logical | AND ANDS ORR EOR (imm, shifted reg), BIC BICS ORN EON |
| move/addr | MOVZ MOVN MOVK ADR ADRP |
| bitfield | SBFM BFM UBFM EXTR |
| dp 1/2/3-src | LSLV LSRV ASRV RORV UDIV SDIV MADD MSUB SMADDL SMSUBL UMADDL UMSUBL SMULH UMULH RBIT REV REV16 REV32 CLZ CLS |
| conditional | CSEL CSINC CSINV CSNEG CCMP CCMN (imm, reg) |
| branches | B BL B.cond CBZ CBNZ TBZ TBNZ BR BLR RET |
| load/store | LDR STR LDRB STRB LDRH STRH LDRSB LDRSH LDRSW (post/pre/unsigned offset, register offset), LDUR/STUR family, LDP STP LDPSW, LDR/LDRSW (literal) |
| system | NOP SVC |

Aliases such as `MOV`, `CMP`, `LSL #imm` and `SXTW` are not separate
instructions. They are the same encodings as the instructions above.

## How an A64 instruction is described

One LIRA `Instruction` corresponds to one XML *encoding*, such as
`ADD_64_addsub_imm`. The 32-bit and 64-bit variants are separate instructions,
because `sf` is a fixed bit.

1. **Encoding** (derived automatically in `xmlspec.py` + `gen.py`)
   * `const_encoding_part` / `const_mask` hold the fixed bits from the
     regdiagram, the encoding's `bitdiffs`, and the should-be bits `(0)`/`(1)`.
   * The operands are the raw encoding fields that the encoding does not fully
     fix, most significant first (`sh imm12 Rn Rd`). `operand_sizes` are the
     field widths.
   * `decode[i]` names a shared snippet `decode_field_<lsb>_<width>`
     (`[32] -> field`).
   * `encode` names a shared snippet `encode_<layout>`. It ORs the fields into
     `dyn_const enc_base`, and the context sets `enc_base` to
     `const_encoding_part`.
   * `constraint_decode` / `constraint_encode` return 1 when the encoding is
     *allocated*. They include `field != pattern` from the XML, the
     `EndOfDecode(Decode_UNDEF)` conditions from the ASL, and, for
     `constraint_encode`, the fixed bits of partially fixed fields. They are
     `''` when there is no condition. Identical snippets are shared, so one
     name can serve several instructions.
2. **Semantics** (hand-written in `insns.py`). The ASL `decode` + `execute`
   is translated into a flat SSA sequence:
   * Every `if` becomes a `select`, or a `cond_env` for effects (conditional
     branches).
   * Loops (`RBIT`, `REV`) and integer arithmetic become bit-vector
     expressions. `SMULH` computes in 128 bits.
   * Shared ASL functions are pure `Operation`s whose `semantic_func` is a
     snippet: `add_with_carry_N`, `shift_reg_N`, `extend_reg_N`,
     `decode_bit_masks_N`, `logic_imm_valid`, `condition_holds`,
     `rev_bytes_N_in_C` and `cls_N`.

An example is `ADDS <Xd>, <Xn|SP>, #imm{, LSL #12}` (`ADDS_64S_addsub_imm`), as generated:

```
1 1 _t1 = input 0;                                  # sh
1 12 _t2 = input 1;                                 # imm12
1 5 _t3 = input 2;                                  # Rn
1 5 _t4 = input 3;                                  # Rd
1 64 _t5 = read X _t3;                              # Rn == 31 reads SP
1 64 _t6 = op extend_zero_12_to_64 _t2;
1 64 _t7 = const 12;
1 64 _t8 = op lsl_64 _t6 _t7;
1 64 _t9 = op select_64 _t1 _t8 _t6;                # sh ? imm << 12 : imm
1 1 _t10 = const 0;
1 64 _t11 4 _t12 = op add_with_carry_64 _t5 _t9 _t10;   # (result, nzcv)
1 64 _t13 = read X _t4;
1 5 _t14 = const 31;
1 1 _t15 = op eq_5 _t4 _t14;
1 64 _t16 = op select_64 _t15 _t13 _t11;            # Rd == 31 is XZR: keep SP
1 = write X _t4 _t16;
1 1 _t17 = const 0;
1 = write NZCV _t17 _t12;
```

To add an instruction, add its XML file stem to a `@sem(...)` handler in
`insns.py`, or write a new handler, plus an `undef=` predicate if its ASL
decode has UNDEFINED cases. Then regenerate the YAML and run the tests.

## State model

| ASL | LIRA |
|---|---|
| `X[0..30]`, `SP` | register file `X`: 32 x 64-bit, `x0..x30`, and `sp` at index 31 |
| `XZR` (index 31 where `X{}(n)` is used) | expressed in the semantics: a read is `select(n == 31, 0, X[n])`, a write is `X[n] = select(n == 31, X[n], v)` (a no-op) |
| `X{32}(d) = v` | the value is zero-extended to 64 bits before the write |
| `PSTATE.{N,Z,C,V}` | register file `NZCV`: one 4-bit register (N = bit 3) |
| `PC64()` / `BranchTo` | env `pc_read` / `pc_write`. Without a `pc_write`, the environment advances PC by 4 |
| `Mem{n}` | env `mem_read_<n>` / `mem_write_<n>`, n in 8..128, little-endian |
| `SVC` | env `supervisor_call(imm16)` |

## Decisions and simplifications

* Semantics never shift by `>= width`, so the result does not depend on how a
  LIRA backend defines oversized shifts. `SDIV` relies on `div_s` truncating
  toward zero and wrapping, so `INT_MIN / -1 = INT_MIN` (same as SMT-LIB
  `bvsdiv`). Division by zero uses the `div_*` default operand, which is 0 here.
* CONSTRAINED UNPREDICTABLE cases follow the ASL statement order, with no
  special handling. For example, a load with writeback where `Rn == Rt`
  ends up holding the written-back address.
* Should-be bits (`(0)`/`(1)`) count as fixed, so non-canonical encodings are
  not decoded.
* Not modeled: SP alignment checks, MTE tag checking, BTI/`BTYPE`, GCS,
  big-endian data, and the Arm-mandated behavior of `SVC` beyond calling the
  environment.
* Not yet covered: FP/SIMD, SVE/SME, atomics and exclusives, system registers
  (`MRS`/`MSR`), and hints other than `NOP`.

## Verification (`tests/`)

* `lira_interp.py` is a small reference interpreter for scalar LIRA.
* `test_encoding.py` checks the encode/decode roundtrip, that no two
  encodings overlap, and that every sampled valid word disassembles in
  `llvm-mc -M no-aliases` to the expected mnemonic. It also checks that the
  words the constraints reject are rejected by LLVM too.
* `test_semantics_hw.py` (AArch64 host only) runs about 1,200 encoded
  instructions with random register, flag and memory states on the host CPU,
  and compares the results with the interpreter. It covers all non-branch
  instructions.
* `test_semantics.py` covers branches, index 31 (SP vs XZR), literal loads,
  `SVC` and `NOP`.

### Generated simulator ([lira-simgen-lib](https://github.com/ProteusLab/lira-simgen-lib), `ARCH_TARGET=AArch64`)

Copy `aarch64.yaml` to `lira-simgen-lib/data/AArch64/`, then build the
`build-interp` and `a64-capi` targets. By default the tests look in
`../lira-simgen-lib/build/a64/interpreter/`; `$LIRA_A64_SIM` and
`$LIRA_A64_CAPI` override that.

* `test_simgen.py` loads `liba64-capi` (the generated C++ decoder and
  interpreter, one instruction at a time):
  * The decoder maps every sampled valid word to its own opcode and rejects
    invalid words.
  * The generated C++ matches the host CPU on the same cases as
    `test_semantics_hw.py`.
  * The generated C++ matches the reference interpreter on all encodings,
    with random fields including register 31, branches and literal loads.
* `test_programs.py` cross-compiles `programs/*.c` (integer algorithms,
  division, `__int128`, bit manipulation, bitfields, jump tables, function
  pointers, narrow loads, struct copies) at `-O0`, `-O1`, `-O2`, `-O3` and
  `-Os` for `aarch64-linux` with `-mgeneral-regs-only`. Each binary runs in
  the generated simulator and must print exactly what the natively compiled
  program prints. The programs use 67 distinct mnemonics.
