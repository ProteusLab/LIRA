"""The Arm ASL as the reference: run A64 instruction words in aslref.

The ASL is the one of LIRA's source, the 2026-06 machine-readable release,
extracted by herdtools7's bundler (herd/libdir/asl-pseudocode of
https://github.com/herd/herdtools7). With ISA_A64_xml_A_profile-2026-06 there
linked to LIRA's ISA_A64 XML directory:

    make features.asl all_system_registers.asl shared_pseudocode.asl \\
         all_instructions.asl pmu_event_types.asl

gives one function `instr_<file>[_<iclass>](instruction)` per encoding class
and the shared pseudocode. asl/machine.asl and asl/patches.asl set up the
machine LIRA describes (see machine.asl); the MRS/MSR accessors of the system
registers LIRA describes are taken from the SysReg XML of the same release.

A run is one aslref program: a function per case sets the state, executes the
word and prints the state after it (or the exception taken).

$ASLREF names aslref (default: `aslref` on PATH), $LIRA_ASL_BUNDLE the
asl-pseudocode directory with the generated files and the SysReg XML.
"""
import html
import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List, Tuple

HERE = Path(__file__).resolve().parent
XML = HERE.parents[2] / 'ISA_A64_xml_A_profile-2026-06_mc' / 'ISA_A64_xml_A_profile-2026-06_mc'
ASLREF = os.environ.get('ASLREF') or shutil.which('aslref')
BUNDLE = Path(os.environ['LIRA_ASL_BUNDLE']) if os.environ.get('LIRA_ASL_BUNDLE') else None
SPEC = ['features.asl', 'all_system_registers.asl', 'all_instructions.asl', 'shared_pseudocode.asl',
        'pmu_event_types.asl']
SYSREG_XML = 'SysReg_xml_A_profile_FAT-2026-06'
# The system registers LIRA describes (MRS/MSR accessors)
SYSREGS = ('nzcv', 'fpcr', 'fpsr', 'svcr')
MAX_WIN = 4096                       # bytes of the memory window (machine.asl)


def available() -> bool:
    return bool(ASLREF) and BUNDLE is not None and all((BUNDLE / f).exists() for f in SPEC)


# -----------------------------------------------------------------------------
# LIRA instruction -> ASL function
# -----------------------------------------------------------------------------
def _encodings(xml_dir: Path) -> Dict[str, str]:
    """Encoding name -> the function of its encoding class. An alias runs the
    function of the instruction it is an alias of."""
    funcs: Dict[str, str] = {}
    aliases: Dict[str, Tuple[str, List[str]]] = {}
    for path in sorted(xml_dir.glob('*.xml')):
        root = ET.parse(path).getroot()
        if root.tag != 'instructionsection':
            continue
        iclasses = root.findall('./classes/iclass')
        names = {}
        for ic in iclasses:
            fn = f'instr_{path.stem}' + (f'_{ic.get("id")}' if len(iclasses) > 1 else '')
            for enc in ic.findall('encoding'):
                names[enc.get('name').rstrip('_')] = fn
        if root.get('type') == 'alias':
            target = root.find('.//aliasto').get('refiform')[:-len('.xml')]
            aliases[path.stem] = (target, list(names))
        elif root.get('type') == 'instruction':
            funcs.update(names)
    for stem, (target, encs) in aliases.items():
        base = {f for f in funcs.values() if f == f'instr_{target}' or f.startswith(f'instr_{target}_iclass')}
        if len(base) == 1:                                 # else: not needed yet
            funcs.update({e: next(iter(base)) for e in encs})
    return funcs


class Functions:
    def __init__(self, xml_dir: Path = XML):
        self.encodings = _encodings(xml_dir)

    def of(self, ins_name: str) -> str:
        """The function of a LIRA instruction: its XML encoding, maybe with a
        specialization suffix."""
        name = ins_name
        while name not in self.encodings:
            assert '_' in name, ins_name
            name = name.rsplit('_', 1)[0]
        return self.encodings[name]


# -----------------------------------------------------------------------------
# MRS/MSR of the described system registers
# -----------------------------------------------------------------------------
def _access(path: Path):
    """[(kind, encoding bits op0:op1:CRn:CRm:op2, pseudocode)] of MRS / MSRregister."""
    out = []
    for am in ET.parse(path).getroot().iter('access_mechanism'):
        kind = am.get('accessor', '').split()[0]
        if kind not in ('MRS', 'MSRregister'):
            continue
        enc = {e.get('n'): e.get('v')[2:] for e in am.iter('enc')}
        bits = ''.join(enc[k] for k in ('op0', 'op1', 'CRn', 'CRm', 'op2'))
        text = html.unescape(''.join(am.find('.//pstext').itertext())).strip()
        out.append((kind, bits, text))
    return out


def sysreg_dispatch(sysreg_dir: Path) -> str:
    """AArch64_SysRegRead/Write for the registers in SYSREGS; any other is
    UNDEFINED (LIRA leaves them to its environment)."""
    funcs = {'MRS': [], 'MSRregister': []}
    for reg in SYSREGS:
        for kind, bits, text in _access(sysreg_dir / f'AArch64-{reg}.xml'):
            funcs[kind].append((bits, text))
    out = []
    for kind, name in (('MRS', 'AArch64_SysRegRead'), ('MSRregister', 'AArch64_SysRegWrite')):
        out.append(f'implementation func {name}(op0 : bits(2), op1 : bits(3), crn : bits(4),\n'
                   f'        crm : bits(4), op2 : bits(3), t : integer)\nbegin')
        for i, (bits, text) in enumerate(funcs[kind]):
            out.append(f"    {'if' if i == 0 else 'elsif'} op0::op1::crn::crm::op2 == '{bits}' then")
            out.append('\n'.join('        ' + line for line in text.splitlines()))
        out.append('    else\n        Undefined();\n    end;\nend;\n')
    return '\n'.join(out)


# -----------------------------------------------------------------------------
# Cases
# -----------------------------------------------------------------------------
def _bits(v: int, n: int) -> str:
    return f'{v & ((1 << n) - 1):#x}[{n - 1}:0]'


def case_function(k: int, func: str, word: int, st: dict, vq: int) -> str:
    """A function that runs one case. `st`: X (x0.., at most 31), Z, P, FFR,
    NZCV, FPCR, FPSR, SVCR, ZA (VL / 8 rows), MEM (with W0)."""
    vl, pl = 128 * vq, 16 * vq
    s = [f'func LIRA_Case{k}()', 'begin', f'    LIRA_Reset({vq});']
    s += [f'    _R[[{i}]] = {_bits(v, 64)};' for i, v in enumerate(st['X']) if v]
    s += [f'    _Z[[{i}]] = ZeroExtend{{MAX_VL}}({_bits(v, vl)});' for i, v in enumerate(st['Z']) if v]
    s += [f'    _P[[{i}]] = ZeroExtend{{MAX_PL}}({_bits(v, pl)});' for i, v in enumerate(st['P']) if v]
    s += [f'    _FFR = ZeroExtend{{MAX_PL}}({_bits(st["FFR"], pl)});',
          f'    PSTATE.[N,Z,C,V] = {_bits(st["NZCV"], 4)};',
          f'    FPCR() = ZeroExtend{{64}}({_bits(st["FPCR"], 32)});',
          f'    FPSR() = ZeroExtend{{64}}({_bits(st["FPSR"], 32)});',
          f'    PSTATE.SM = {_bits(st.get("SVCR", 0), 1)};',
          f'    PSTATE.ZA = {_bits(st.get("SVCR", 0) >> 1, 1)};']
    za = st.get('ZA', 0)
    s += [f'    _ZA[[{r}]] = ZeroExtend{{MAX_VL}}({_bits(za >> (r * vl), vl)});'
          for r in range(vl // 8) if za >> (r * vl) & ((1 << vl) - 1)]
    if 'MEM' in st:
        win = len(st['MEM'])
        assert win <= MAX_WIN
        image = int.from_bytes(st['MEM'], 'little')
        s.append(f'    LIRA_SetMemory({_bits(st["W0"], 64)}, {win}, {_bits(image, 8 * MAX_WIN)});')
    s += [f'    println("CASE {k}");',
          f'    LIRA_Instr = {_bits(word, 32)};',
          '    try',
          f'        {func}(LIRA_Instr);',
          f'        LIRA_Dump({vl});',
          '    catch',
          '        when LIRA_DataAbort => println("FAULT");',
          '        when e : LIRA_Exception => print("EXCEPTION "); println(e.esr);',
          '    end;',
          'end;', '']
    return '\n'.join(s)


def parse(out: str, n: int, win: List[int]) -> List[object]:
    """States after the cases: dict, 'fault' or ('exception', ESR)."""
    res: List[object] = []
    for line in out.splitlines():
        if line.startswith('CASE '):
            assert int(line[5:]) == len(res), line
            res.append({'X': [0] * 31, 'Z': [0] * 32, 'P': [0] * 16, 'ZA': 0})
            continue
        st = res[-1]
        key, _, value = line.partition(' ')
        if key == 'FAULT':
            res[-1] = 'fault'
        elif key == 'EXCEPTION':
            res[-1] = ('exception', int(value, 16))
        else:
            m = re.fullmatch(r'(X|Z|P|ZA)(\d+)', key)
            if m and m.group(1) == 'ZA':
                st['ZA'] |= int(value, 16) << (int(m.group(2)) * st['vl'])
            elif m:
                st[m.group(1)][int(m.group(2))] = int(value, 16)
            elif key == 'MEM':
                st['MEM'] = int(value, 16).to_bytes(MAX_WIN, 'little')[:win[len(res) - 1]]
            else:
                st[key] = int(value, 16)
            if key == 'Z0':
                st['vl'] = (len(value) - 2) * 4
    assert len(res) == n, (len(res), n, out[-2000:])
    for st in res:
        if isinstance(st, dict):
            st.pop('vl', None)
    return res


def run(cases, vq: int, workdir: Path, functions: Functions) -> List[object]:
    """cases: [(LIRA instruction name, word, state)] -> states after them."""
    sysregs = workdir / 'sysregs.asl'
    sysregs.write_text(sysreg_dispatch(BUNDLE / SYSREG_XML))
    prog = [case_function(k, functions.of(name), word, st, vq) for k, (name, word, st) in enumerate(cases)]
    prog += ['func main() => integer', 'begin']
    prog += [f'    LIRA_Case{k}();' for k in range(len(cases))]
    prog += ['    return 0;', 'end;', '']
    main = workdir / 'cases.asl'
    main.write_text('\n'.join(prog))
    cmd = [ASLREF, '--version-eac1', *[str(BUNDLE / f) for f in SPEC], str(HERE / 'asl' / 'machine.asl'),
           str(sysregs), str(main), '--patch', str(HERE / 'asl' / 'patches.asl')]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode and 'unreachable' in p.stdout[-500:] + p.stderr[-500:]:
        raise AssertionError(_name_impdef(cmd, workdir) or p.stdout[-3000:] + p.stderr[-3000:])
    assert p.returncode == 0, p.stdout[-3000:] + p.stderr[-3000:]
    return parse(p.stdout, len(cases), [len(st.get('MEM', b'')) for _, _, st in cases])


def _name_impdef(cmd, workdir: Path):
    """Rerun with the ImpDef* hooks throwing the name of the choice (a readonly
    function cannot throw: type errors are warnings in this run)."""
    machine = (HERE / 'asl' / 'machine.asl').read_text()
    debug = machine.replace('    unreachable;\n', '    throw LIRA_ImpDefChoice { name = s };\n')
    debug = 'type LIRA_ImpDefChoice of exception { name : string };\n' + debug
    (workdir / 'machine_debug.asl').write_text(debug)
    main = (workdir / 'cases.asl').read_text().replace(
        '        when e : LIRA_Exception',
        '        when e : LIRA_ImpDefChoice => print("IMPDEF "); println(e.name);\n'
        '        when e : LIRA_Exception')
    (workdir / 'cases_debug.asl').write_text(main)
    cmd = [c.replace(str(HERE / 'asl' / 'machine.asl'), str(workdir / 'machine_debug.asl'))
           .replace(str(workdir / 'cases.asl'), str(workdir / 'cases_debug.asl')) for c in cmd]
    p = subprocess.run([cmd[0], '--type-check-warn'] + cmd[1:], capture_output=True, text=True)
    case = None
    for line in p.stdout.splitlines():
        if line.startswith('CASE '):
            case = line[5:]
        elif line.startswith('IMPDEF '):
            return f'case {case}: IMPLEMENTATION DEFINED choice not made by asl/machine.asl: {line[7:]}'
    return None
