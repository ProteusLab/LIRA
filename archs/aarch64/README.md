# AArch64 (A64) in LIRA

LIRA description of the A64 base integer instructions, the mandatory ARMv8.x
general-purpose and system extensions, scalar floating point, and Advanced SIMD
(integer and crypto). It is generated from the Arm machine-readable
specification (`ISA_A64_xml_A_profile-2026-06_mc`).

```bash
# from the repository root
python -m archs.aarch64.gen [--xml <ISA_A64_xml dir>] [--output archs/aarch64/aarch64.yaml]
python -m pytest archs/aarch64/tests
```

The output is `aarch64.yaml`: 2706 instructions (676 mnemonics) from 578 XML
files, one LIRA instruction per encoding and arrangement:

| Module | XML files | Instructions | Content |
|---|---|---|---|
| `insns.py` | 129 | 252 | base integer |
| `insns_fp.py` | 61 | 295 | scalar FP, SIMD&FP loads/stores, MRS/MSR |
| `insns_simd.py` | 158 | 1291 | Advanced SIMD integer, part 1 |
| `insns_simd2.py` | 64 | 428 | Advanced SIMD integer, part 2, and crypto |
| `insns_v8.py` | 166 | 440 | ARMv8.1–v8.9 general-purpose and system instructions |

The description uses 72 float operations, 35 environment functions and 361
operations. `insns_vfp.py` (vector FP, FHM, FCMA, BF16, …) is a draft that is
not imported yet.

### Base integer

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
| system | NOP SVC, MRS/MSR for NZCV, FPCR, FPSR (other system registers through `sysreg_read`/`sysreg_write`) |

### Floating point (`insns_fp.py`, H/S/D forms)

| Group | Mnemonics |
|---|---|
| arithmetic | FADD FSUB FMUL FDIV FNMUL FMAX FMIN FMAXNM FMINNM FSQRT FABS FNEG FMOV |
| fused | FMADD FMSUB FNMADD FNMSUB |
| compare/select | FCMP FCMPE (register, #0.0) FCCMP FCCMPE FCSEL |
| rounding | FRINTN FRINTP FRINTM FRINTZ FRINTA FRINTI FRINTX |
| conversion | FCVT (H/S/D), FCVT{N,A,P,M,Z}{S,U} (to W/X), FCVTZS/FCVTZU (fixed-point), SCVTF UCVTF (integer, fixed-point), FMOV (general, `V.D[1]`, immediate) |
| load/store | LDR STR (B/H/S/D/Q: post/pre/unsigned offset, register offset, literal), LDUR STUR, LDP STP LDNP STNP (S/D/Q) |

### Advanced SIMD (`insns_simd.py`, vector and scalar forms)

| Group | Mnemonics |
|---|---|
| three same | ADD SUB MUL MLA MLS AND BIC ORR ORN EOR BSL BIT BIF CMEQ CMGE CMGT CMHI CMHS CMTST SMAX SMIN UMAX UMIN SABD UABD SABA UABA SHADD UHADD SRHADD URHADD SHSUB UHSUB SQADD UQADD SQSUB UQSUB SSHL USHL SRSHL URSHL SQDMULH SQRDMULH PMUL ADDP SMAXP SMINP UMAXP UMINP |
| two-reg misc | ABS NEG CLS CLZ CNT NOT RBIT REV16 REV32 REV64 CMEQ/CMGE/CMGT/CMLE/CMLT (#0) SQABS SQNEG XTN SQXTN UQXTN SQXTUN SADDLP UADDLP SADALP UADALP SHLL |
| across lanes | ADDV SMAXV SMINV UMAXV UMINV SADDLV UADDLV, ADDP (scalar) |
| shift immediate | SHL SLI SRI SSHR USHR SRSHR URSHR SSRA USRA SRSRA URSRA SHRN RSHRN SSHLL USHLL |
| long/wide/narrow | SADDL UADDL SSUBL USUBL SADDW UADDW SSUBW USUBW SMULL UMULL SMLAL UMLAL SMLSL UMLSL SABDL UABDL SABAL UABAL ADDHN RADDHN SUBHN RSUBHN PMULL (8B, 1D) |
| by element | MUL MLA MLS SMULL UMULL SMLAL UMLAL SMLSL UMLSL |
| permute | ZIP1 ZIP2 UZP1 UZP2 TRN1 TRN2 EXT TBL TBX (1-4 registers) |
| copy/immediate | DUP (element, general) INS (element, general) UMOV SMOV MOVI MVNI ORR BIC (immediate) |
| load/store | LD1-LD4 ST1-ST4 (multiple structures, post-index), LD1R |

### Advanced SIMD, part 2, and crypto (`insns_simd2.py`)

| Group | Mnemonics |
|---|---|
| saturating shifts | SQSHL UQSHL SQRSHL UQRSHL (register), SQSHL UQSHL SQSHLU (immediate), SQSHRN UQSHRN SQRSHRN UQRSHRN SQSHRUN SQRSHRUN |
| saturating multiply | SQDMULL SQDMLAL SQDMLSL (vector, element), SQDMULH SQRDMULH (element), SQRDMLAH SQRDMLSH (FEAT_RDM) |
| misc | SUQADD USQADD URECPE URSQRTE |
| load/store | LD1-LD4 ST1-ST4 (single structure), LD2R LD3R LD4R |
| dot product | SDOT UDOT (FEAT_DotProd), USDOT SUDOT SMMLA UMMLA USMMLA (FEAT_I8MM) |
| crypto | AESE AESD AESMC AESIMC, SHA1C SHA1P SHA1M SHA1H SHA1SU0 SHA1SU1, SHA256H SHA256H2 SHA256SU0 SHA256SU1 |

### ARMv8.1–v8.9 general purpose and system (`insns_v8.py`)

| Group | Mnemonics |
|---|---|
| load/store | LDTR/STTR family (unprivileged), LDNP STNP, LDAPUR/STLUR family (FEAT_LRCPC2), PRFM PRFUM (no-op) |
| ordered | LDAR LDAPR LDLAR STLR STLLR (all sizes) |
| exclusives | LDXR LDAXR STXR STLXR LDXP LDAXP STXP STLXP CLREX |
| atomics (FEAT_LSE) | CAS CASP SWP LDADD LDCLR LDEOR LDSET LDSMAX LDSMIN LDUMAX LDUMIN (all sizes and orderings) |
| CRC32 | CRC32B/H/W/X CRC32CB/H/W/X |
| FEAT_CSSC | ABS CNT CTZ SMAX SMIN UMAX UMIN (register, immediate) |
| flags (FEAT_FlagM/2) | CFINV AXFLAG XAFLAG RMIF SETF8 SETF16 |
| branches | BC.cond (FEAT_HBC) |
| FEAT_MOPS | CPYP/CPYM/CPYE and CPYFP/CPYFM/CPYFE (all read/write options), SETP/SETM/SETE (all options); SETG* needs MTE and is not included |
| FEAT_PAuth | PACIA PACIB PACDA PACDB (+Z, SP, 1716 forms), AUTIA…, XPACI XPACD XPACLRI, PACGA, BRAA BRAB BLRAA BLRAB (+Z), RETAA RETAB, LDRAA LDRAB |
| hints | HINT (generic), YIELD WFE WFI SEV SEVL, WFET WFIT (FEAT_WFxT), BTI, ESB CSDB CLRBHB |
| barriers | DMB DSB ISB SB, DSB nXS (FEAT_XS) |
| exceptions | BRK HLT HVC SMC UDF DCPS1-3 ERET ERETAA ERETAB DRPS |
| system | SYS SYSL MSR (immediate) MRS/MSR (any system register) |

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
`insns*.py`, or write a new handler, plus an `undef=` predicate if its ASL
decode has UNDEFINED cases. Then regenerate the YAML and run the tests.

**Specializations.** `spec=` splits an XML encoding into several LIRA
instructions by fixing more fields (`xmlspec.specialize`), either fully or
as `(value, mask)`:

* SIMD arrangements: `size`/`Q`, `immh` for shifts, `imm5` for DUP/INS/UMOV,
  `cmode`/`op` for modified immediates. Statement shapes are static, so
  `ADD_asimdsame_only` becomes `..._8B`, `..._16B`, …, `..._2D`. Reserved
  arrangements are simply not generated.
* System registers for MRS/MSR (`MRS_RS_systemmove_FPCR`, …).

**Floating point** uses `fop` statements with the standard float operations
from LIRA `docs/float_ops.md`. For example, `FADD Dd, Dn, Dm` (`FADD_D_floatdp2`; operands Rm, Rn, Rd) is:

```
1 5 _t1 = input 0;                                  # Rm
1 5 _t2 = input 1;                                  # Rn
1 5 _t3 = input 2;                                  # Rd
1 128 _t4 = read V _t2;
1 64 _t5 = op extract_low_128_to_64 _t4;            # Dn
1 128 _t6 = read V _t1;
1 64 _t7 = op extract_low_128_to_64 _t6;            # Dm
1 3 _t8 = const 7;                                  # rounding mode: from FPCR
1 64 _t9 = fop fadd_64 _t5 _t7 _t8;                 # reads FPCR, sets FPSR flags
1 128 _t10 = op extend_zero_64_to_128 _t9;
1 = write V _t3 _t10;
```

**SIMD** uses vector shapes. `ADD Vd.4S, Vn.4S, Vm.4S` (`ADD_asimdsame_only_4S`) is:

```
1 5 _t1 = input 0;                                  # Rm
1 5 _t2 = input 1;                                  # Rn
1 5 _t3 = input 2;                                  # Rd
4 32 _t4 = read V _t2;                              # V[n] as 4 x 32-bit lanes
4 32 _t5 = read V _t1;
4 32 _t6 = op add_32 _t4 _t5;
4 = write V _t3 _t6;
```

The other SIMD statements are used as follows:

* Permutes (ZIP/UZP/TRN/EXT/REV), TBL/TBX and lane extraction use `index`
  arithmetic and `gather`.
* Across-lane reductions use `fold`.
* 64-bit arrangements use `extract_first` and `extend_zero`.
* Structure loads/stores are shaped `mem_read`/`mem_write` accesses, one per
  lane, with the (de)interleaving in the address computation.

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
| alignment (ordered, atomic, exclusive) | env `check_alignment(addr, bytes, exclusive)` |
| exclusive monitor | env `exclusive_mark`, `exclusive_check -> pass`, `exclusive_clear` |
| MOPS copy/set | env `mem_copy(dst, src, n, may_overlap)`, `mem_set(dst, n, byte)` (whole operation in the prologue) |
| PAC keys and algorithm | env `pac_add`, `pac_auth`, `pac_strip`, `pac_generic` |
| barriers, hints, BTI | env `barrier(kind, CRm)`, `hint(CRm:op2)`, `wait_timeout`, `branch_target` |
| exceptions | env `exception_call(kind, imm16)`, `exception_return`, `debug_state` |
| system registers and ops | env `sysreg_read`, `sysreg_write`, `sys_op`, `sys_op_read`, `pstate_write` |
| `V[0..31]` (Q/D/S/H/B views) | register file `V`: 32 x 128-bit; scalar writes clear the upper bits |
| `FPCR`, `FPSR` | register files `FPCR`, `FPSR` (32-bit). Attributes bind them to the FPU state of `fop`. MSR writes the architected fields only (`0x07FF9F00`, `0x0800009F`) |

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
  environment. Exception levels, the MMU and exception entry belong to the
  environment: the semantics only call the hooks listed above.
* MOPS: the prologue (`CPYP`, `SETP`, …) performs the whole operation and
  leaves the registers in the "option B" end state; the main and epilogue
  forms then do nothing. Overlapping register operands are UNDEFINED.
* The LRCPC3 writeback forms of LDAPR/STLR are excluded.
* FP: FEAT_AFP (FPCR.AH/FIZ/NEP), FPCR.AHP and trapped FP exceptions are
  not modeled; they are treated as 0 and disabled. Loads/stores of a Q-register
  pair use two 128-bit accesses.
* Not yet covered:
  * vector FP, FRECPE/FRSQRTE/FRECPX, FRINT32/64, FJCVTZS, FHM, FCMA, BF16
    (the float operations exist in `lira/float_ops.py`; the semantics are the
    `insns_vfp.py` draft);
  * FEAT_AFP (FPCR.AH/FIZ/NEP);
  * optional extensions: SVE/SME, MTE, GCS, FP8, SHA3/SHA512/SM3/SM4, LS64,
    LRCPC3, THE, D128 and others.

## Verification (`tests/`)

* `lira_interp.py` is a small reference interpreter. It handles vector
  shapes, `index`/`gather`/`replicate`/`extract_first`/`extend_zero`/`fold`,
  and `fop` through `lira.float_ops`.
* `test_encoding.py` checks the encode/decode roundtrip, that no two
  encodings overlap, and that every sampled valid word disassembles in
  `llvm-mc -M no-aliases` to the expected mnemonic. It also checks that the
  words the constraints reject are rejected by LLVM too.
* `test_semantics_hw.py` (AArch64 host only) runs about 14,900 encoded
  words (6 per instruction, about 2,490 instructions), 12 random states each,
  on the host CPU and compares the results with the interpreter.
  * It skips branches and literal loads (covered by `test_semantics.py`),
    instructions whose effect belongs to the environment (PAuth, hints,
    exceptions, SYS, system registers), and CSSC/HBC/MOPS, which Apple M1
    lacks.
  * Instructions that raise SIGILL on the host are found by a forked probe and
    reported as skipped. On an M1 Pro these are DCPS1-3, DSB nXS and the I8MM
    instructions.
  * Ordered/atomic accesses use offsets that stay inside 16 bytes (the host
    faults otherwise; LIRA models this with `check_alignment`).
  * The state includes x0–x7, v0–v7, NZCV, FPCR (random rounding mode,
    FZ, FZ16, DN), FPSR and memory.
  * Random FP operands include zeros, subnormals, infinities, quiet and
    signalling NaNs, and rounding-boundary values in every format.
* `test_semantics.py` covers branches, index 31 (SP vs XZR), literal loads,
  `SVC` and `NOP`. It also checks the instructions the host cannot compare:
  CSSC, BC.cond, exclusive pairs, MOPS and PAuth/system instructions (the
  environment hooks they call, with which arguments).

### Generated simulator ([lira-simgen-lib](https://github.com/ProteusLab/lira-simgen-lib), `ARCH_TARGET=AArch64`)

Copy `aarch64.yaml` to `lira-simgen-lib/data/AArch64/`, then build the
`build-interp` and `a64-capi` targets. By default the tests look in
`../lira-simgen-lib/build/a64/interpreter/`; `$LIRA_A64_SIM` and
`$LIRA_A64_CAPI` override that.

The simulator is checked against the description it was generated from
(`lira-simgen-lib/data/AArch64/aarch64.yaml`, or `$LIRA_A64_SIM_YAML`).
simgen does not support `fop` or vector shapes yet, so it still uses the
integer description.

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
