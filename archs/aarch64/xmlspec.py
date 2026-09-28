"""Extract A64 instruction encodings from the Arm machine-readable XML.

Only the encoding part (bit layout, fixed bits, operand fields, encoding
conditions) is taken from XML; semantics are written by hand in `insns.py`.
"""
import html
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass
class Field:
    name: str
    lo: int
    width: int

    @property
    def mask(self) -> int:
        return ((1 << self.width) - 1) << self.lo


@dataclass
class Encoding:
    name: str             # e.g. ADD_64_addsub_imm
    file: str             # e.g. add_addsub_imm
    mnemonic: str
    iclass: str
    asm: str
    const_value: int      # fixed bits of the 32-bit word
    const_mask: int
    operands: List[Field]                     # fields that are (partially) free
    fields: Dict[str, Field]                  # every named field
    ne: List[Tuple[str, str]] = field(default_factory=list)  # (field, pattern) must not match
    docvars: Dict[str, str] = field(default_factory=dict)

    def fixed(self, name: str) -> Optional[int]:
        """Value of a named field if it is fully fixed by the encoding."""
        f = self.fields[name]
        if (self.const_mask & f.mask) != f.mask:
            return None
        return (self.const_value & f.mask) >> f.lo

    def fixed_bits(self, name: str) -> Tuple[int, int]:
        """(mask, value) of the fixed bits inside a field, relative to its lsb."""
        f = self.fields[name]
        return (self.const_mask & f.mask) >> f.lo, (self.const_value & f.mask) >> f.lo


def _text(e) -> str:
    return html.unescape(''.join(e.itertext())) if e is not None else ''


def _apply(bits: List[str], hibit: int, pattern: str):
    for i, ch in enumerate(pattern):
        if ch in '01':
            bits[31 - (hibit - i)] = ch


def _parse_cells(box) -> Tuple[str, Optional[str]]:
    """Return (bit pattern, '!=' pattern or None) for a regdiagram box."""
    width = int(box.get('width', '1'))
    out, ne = '', None
    for c in box.findall('c'):
        span = int(c.get('colspan', '1'))
        t = (c.text or '').strip()
        if t.startswith('!='):
            ne = t[2:].strip()
            out += '?' * span
        elif t == '':
            out += '?' * span
        else:
            t = t.replace('(0)', '0').replace('(1)', '1')  # should-be bits: canonical value
            if len(t) != span or any(ch not in '01x' for ch in t):
                raise ValueError(f'unsupported regdiagram cell {t!r}')
            out += t.replace('x', '?')
    assert len(out) == width, (box.attrib, out)
    return out, ne


def parse_file(path: Path) -> List[Encoding]:
    root = ET.parse(path).getroot()
    result = []
    for ic in root.iter('iclass'):
        bits = ['?'] * 32
        fields: Dict[str, Field] = {}
        ne_base = []
        for box in ic.find('regdiagram').findall('box'):
            hibit, width = int(box.get('hibit')), int(box.get('width', '1'))
            pattern, ne = _parse_cells(box)
            _apply(bits, hibit, pattern)
            name = box.get('name')
            if name:
                fields[name] = Field(name, hibit - width + 1, width)
                if ne:
                    ne_base.append((name, ne))
            elif ne:
                raise ValueError('unnamed box with != constraint')
        for enc in ic.findall('encoding'):
            ebits = list(bits)
            ne = list(ne_base)
            bitdiffs = enc.get('bitdiffs') or ''
            if bitdiffs.startswith('!('):
                bitdiffs = ''     # negated: overlaps with more specific encodings, see gen.py
            for cond in bitdiffs.split('&&'):
                cond = cond.strip()
                if not cond or cond.startswith('!('):
                    # `!(...)` excludes more specific encodings (e.g. MSR (immediate)
                    # vs. CFINV); gen.py resolves overlaps generically
                    continue
                # `(...)` marks should-be bits; like in regdiagrams they are fixed
                m = re.fullmatch(r'(\w+) (==|!=) \(?([01x]+)\)?', cond)
                name, op, pat = m.groups()
                f = fields[name]
                assert len(pat) == f.width, cond
                if op == '==':
                    _apply(ebits, f.lo + f.width - 1, pat)
                else:
                    ne.append((name, pat))
            word = ''.join(ebits)
            value = int(word.replace('?', '0'), 2)
            mask = int(''.join('0' if ch == '?' else '1' for ch in word), 2)
            operands = [f for f in fields.values() if (mask & f.mask) != f.mask]
            dv = {d.get('key'): d.get('value') for d in enc.iter('docvar')}
            result.append(Encoding(
                name=enc.get('name'), file=path.stem, mnemonic=dv.get('mnemonic', ''),
                iclass=ic.get('name'), asm=_text(enc.find('asmtemplate')).strip(),
                const_value=value, const_mask=mask, operands=operands,
                fields=fields, ne=ne, docvars=dv))
    return result


def load(xml_dir: Path, files: List[str]) -> Dict[str, Encoding]:
    encs: Dict[str, Encoding] = {}
    for name in files:
        for e in parse_file(xml_dir / f'{name}.xml'):
            assert e.name not in encs, e.name
            encs[e.name] = e
    return encs


def specialize(e: Encoding, suffix: str, assignments: Dict[str, int]) -> Encoding:
    """Copy of `e` with some operand fields fixed (e.g. a system register or a
    SIMD arrangement), named `<name>_<suffix>`."""
    value, mask = e.const_value, e.const_mask
    for name, v in assignments.items():
        f = e.fields[name]
        vm = (1 << f.width) - 1
        if isinstance(v, tuple):                   # (value, mask): fix some bits only
            v, vm = v
        fm, fv = e.fixed_bits(name)
        assert (v & fm & vm) == (fv & vm), f'{e.name}: {name}={v} contradicts fixed bits'
        value = (value & ~(vm << f.lo)) | ((v & vm) << f.lo)
        mask |= vm << f.lo
    operands = [f for f in e.operands if (mask & f.mask) != f.mask]
    return Encoding(name=f'{e.name}_{suffix}', file=e.file, mnemonic=e.mnemonic,
                    iclass=e.iclass, asm=e.asm, const_value=value, const_mask=mask,
                    operands=operands, fields=e.fields, ne=list(e.ne), docvars=dict(e.docvars))
