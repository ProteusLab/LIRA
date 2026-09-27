"""Encoding checks: LIRA encode/decode/constraint snippets vs. LLVM's disassembler."""
import random
import shutil
import subprocess

import pytest

from .conftest import sample_operands


def test_encode_decode_roundtrip(arch, machine):
    rng = random.Random(1)
    for ins in arch.instructions:
        for _ in range(50):
            ops = sample_operands(machine, ins, rng)
            word = machine.encode(ins, ops)
            assert machine.decode(ins, word) == ops, ins.name
            assert machine.valid_word(ins, word), (ins.name, hex(word))


def test_encodings_do_not_overlap(arch, machine):
    rng = random.Random(2)
    for ins in arch.instructions:
        for _ in range(20):
            word = machine.encode(ins, sample_operands(machine, ins, rng))
            owners = [i.name for i in arch.instructions if machine.valid_word(i, word)]
            assert owners == [ins.name], (hex(word), owners)


def _llvm_disasm(words):
    mc = shutil.which('llvm-mc')
    if mc is None:
        pytest.skip('llvm-mc not found')
    text = '\n'.join(' '.join(f'0x{(w >> (8 * i)) & 0xff:02x}' for i in range(4)) for w in words)
    p = subprocess.run([mc, '--disassemble', '-triple=aarch64', '-M', 'no-aliases'],
                       input=text, capture_output=True, text=True)
    lines = [l.strip() for l in p.stdout.splitlines() if l.strip() and not l.strip().startswith('.')]
    # invalid words produce a warning on stderr and no output line
    return lines, p.stderr.count('invalid instruction encoding')


# LLVM prints these preferred forms even with `-M no-aliases`
LLVM_FORCED_ALIASES = {
    'orr': {'mov'}, 'movz': {'mov'}, 'movn': {'mov'},
    'sbfm': {'sbfx', 'sbfiz', 'asr', 'sxtb', 'sxth', 'sxtw'},
    'ubfm': {'ubfx', 'ubfiz', 'lsl', 'lsr', 'uxtb', 'uxth'},
    'bfm': {'bfi', 'bfxil', 'bfc'},
    'lslv': {'lsl'}, 'lsrv': {'lsr'}, 'asrv': {'asr'}, 'rorv': {'ror'}, 'nop': {'hint'},
}


def _mnemonic(ins):
    return next(a for a in ins.attributes if a.startswith('mnemonic.')).split('.', 1)[1].lower()


def test_valid_encodings_match_llvm(arch, machine):
    rng = random.Random(3)
    words, expected = [], []
    for ins in arch.instructions:
        for _ in range(20):
            words.append(machine.encode(ins, sample_operands(machine, ins, rng)))
            expected.append((ins.name, _mnemonic(ins)))
    lines, invalid = _llvm_disasm(words)
    assert invalid == 0
    assert len(lines) == len(words)
    bad = []
    for (name, mn), line, w in zip(expected, lines, words):
        got = line.split()[0].lower()
        if not (got == mn or got.startswith(mn + '.') or got in LLVM_FORCED_ALIASES.get(mn, ())):
            bad.append((name, hex(w), line))
    assert not bad


def test_constraint_rejects_match_llvm(arch, machine):
    """Words with the fixed bits of an instruction that its constraints reject."""
    rng = random.Random(4)
    words = []
    for ins in arch.instructions:
        e = ins.encoding
        if not e.constraint_decode:
            continue
        found = 0
        for _ in range(2000):
            w = e.const_encoding_part | (rng.getrandbits(32) & ~e.const_mask)
            if not machine.valid_word(ins, w) and not any(machine.valid_word(i, w) for i in arch.instructions):
                words.append(w)
                found += 1
                if found == 10:
                    break
    assert words
    lines, invalid = _llvm_disasm(words)
    assert invalid == len(words), lines
