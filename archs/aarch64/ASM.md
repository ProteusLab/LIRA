# AArch64 formatter fixture

[`aarch64-asm.yaml`](aarch64-asm.yaml) is a generated A64 subset for
[lira-simgen-lib](https://github.com/ProteusLab/lira-simgen-lib)'s assembly
formatter. It uses the syntax-capable inline-semantics schema from LIRA
[`9462267`](https://github.com/ProteusLab/LIRA/commit/946226771f6df5f970113e28ae6df7e60e9a6cff).
The AArch64 generator on this branch uses its historical schema for
`aarch64.yaml` and emits the syntax subset separately.

Regenerate from the LIRA checkout with its Python dependencies available.
Pass the June 2026 XML directory from Arm's A64 ISA archive, which may also
contain an earlier release. [Arm ISA downloads](https://developer.arm.com/Architectures/A-Profile%20Architecture#Downloads)

```sh
python -m archs.aarch64.gen \
  --xml /path/to/ISA_A64_xml_A_profile-2026-06 \
  --asm archs/aarch64/aarch64-asm.yaml
```

The generator reuses the base instruction encodings, semantics, and raw
operand field ordering. Each syntax entry points to a predicate snippet and
a formatting snippet. The formatter tries the entries in order. The subset
covers scalar integer arithmetic, bitfields, conditional selects, branches,
addressing modes, and selected Advanced SIMD arrangements, lane operands,
and register lists. Preferred spelling follows LLVM 14, including `bfi` for
the `bfc` encoding. Only the covered XML syntax forms are emitted.
