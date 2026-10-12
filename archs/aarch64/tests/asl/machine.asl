// The machine LIRA's AArch64 description models, for running the Arm ASL in
// aslref (see archs/aarch64/tests/asl_oracle.py): a Linux EL0 process with
// FP/SIMD, SVE and SME enabled, the streaming vector length equal to the
// vector length, FEAT_SME_FA64 enabled, no EL2/EL3. Memory is a window of
// bytes; any access outside it is a data abort.
//
// The IMPLEMENTATION DEFINED hooks and the types the published XML leaves
// undefined follow herdtools7's type-checking-implementations.asl
// (Copyright 2022-2023 Arm Limited, BSD-3-Clause).

// -----------------------------------------------------------------------------
// Features and IMPLEMENTATION DEFINED choices
// -----------------------------------------------------------------------------
// A choice not made here is `unreachable`; asl_oracle.py then reruns the case
// to name it
readonly func IsFeatureImplemented(f : Feature) => boolean
begin
    case f of
        when FEAT_AA64, FEAT_AA64EL0, FEAT_AA64EL1, FEAT_FP, FEAT_AdvSIMD, FEAT_FP16,
             FEAT_SVE, FEAT_SME, FEAT_SME_FA64 =>
            return TRUE;
        otherwise =>
            return FALSE;
    end;
end;

readonly func ImpDefInt(s : string) => integer
begin
    if s == "Max implemented SVL" || s == "Max implemented VL" then
        return 2048;                                // ZCR/SMCR.LEN select the length
    elsif s == "Number of watchpoints" then
        return 2;                                   // none enabled
    end;
    unreachable;
end;

readonly func ImpDefBool(s : string) => boolean
begin
    if s == "Secure-only implementation" then
        return FALSE;                               // Non-secure
    elsif s == "No tag checking of SME LDR & STR instructions" then
        return FALSE;                               // no FEAT_MTE: no tag checks anyway
    elsif s == "Support trapping of floating-point exceptions" then
        return FALSE;                               // as LIRA's float operations
    elsif (s == "GPF, GPC, Data SyncExternal Aborts, TagChecks prioritized over Watchpoints" ||
           s == "Instruction SyncExternal Aborts prioritized over Breakpoints") then
        return TRUE;                                // no watchpoints or breakpoints
    end;
    unreachable;
end;

readonly func ImpDefBits{N}(s : string) => bits(N)
begin
    unreachable;
end;

readonly func ImpDefBit(s : string) => bits(1)
begin
    return ImpDefBits{1}(s);
end;

readonly func ImpDefMemoryAttributes(s : string) => MemoryAttributes
begin
    unreachable;
end;

type IMPLEMENTATION_DEFINED of exception {-};

func ImpDef(s : string)
begin
    throw IMPLEMENTATION_DEFINED {-};
end;

type UNIMPLEMENTED of exception {-};

noreturn func Unimplemented()
begin
    throw UNIMPLEMENTED {-};
end;

noreturn func ReservedEncoding()
begin
    Unimplemented();
end;

func See(s : string)
begin
    Unimplemented();
end;

constant NUM_PMU_COUNTERS = 123456789;

type TRBSRType of TRBSR_EL1_Type;
type PMBSRType of PMBSR_EL1_Type;
type S1PIRType of PIR_EL1_Type;
type S2PIRType of PIR_EL2_Type;
type MAIRType of bits(64);
type S1PORType of POR_EL1_Type;
type SCTLRType of SCTLR_EL1_Type;
type ESRType of ESR_EL1_Type;

var EDPCSRhi : bits(32) {
    [26:3] PC,
    [2:1] EL,
    [0] NS,
};

constant NUM_VMIDBITS = 16;
constant NUM_ASIDBITS = 16;

// The SysReg access pseudocode reads FGDTState.E0 (FEAT_S1POE2, at EL3); the
// shared pseudocode does not define it
type LIRA_FGDTState of record { E0 : bit };
var FGDTState : LIRA_FGDTState;

// -----------------------------------------------------------------------------
// The instruction, exceptions: a taken exception ends the instruction (see
// patches.asl)
// -----------------------------------------------------------------------------
var LIRA_Instr : bits(32);

implementation func ThisInstr() => bits(32)
begin
    return LIRA_Instr;
end;

implementation func ThisInstrLength() => integer
begin
    return 32;
end;

type LIRA_Exception of exception { esr : bits(64) };
type LIRA_DataAbort of exception {-};

// -----------------------------------------------------------------------------
// Memory: the bytes [LIRA_W0, LIRA_W0 + LIRA_WIN)
// -----------------------------------------------------------------------------
constant LIRA_MAX_WIN = 4096;
var LIRA_W0 : bits(64);
var LIRA_WIN : integer;
var LIRA_MEM : array [[LIRA_MAX_WIN]] of bits(8);

var LIRA_NormalMemory : MemoryAttributes = MemoryAttributes {
    memtype = MemType_Normal,
    inner = MemAttrHints { attrs = MemAttr_WB, hints = MemHint_RWA, transient = FALSE },
    outer = MemAttrHints { attrs = MemAttr_WB, hints = MemHint_RWA, transient = FALSE },
    shareability = Shareability_ISH,
    tags = MemTag_Untagged,
    device = DeviceType_GRE,
    notagaccess = TRUE,
    xs = '0'
};

func LIRA_InWindow(va : bits(64), bytes : integer) => boolean
begin
    return UInt(va - LIRA_W0) + bytes <= LIRA_WIN;
end;

func LIRA_Offset(va : bits(64), bytes : integer) => integer
begin
    if !LIRA_InWindow(va, bytes) then
        throw LIRA_DataAbort {-};
    end;
    return UInt(va - LIRA_W0);
end;

// A non-fault access of SVE (LDNF1, LDFF1 after the first active element)
// outside the window is not performed: MemNF returns fault = TRUE
var LIRA_NFFaulted : boolean;

func LIRA_IsNonFault(accdesc : AccessDescriptor) => boolean
begin
    return accdesc.acctype == AccessType_SVE && (accdesc.nonfault || (accdesc.firstfault && !accdesc.first));
end;

// The CONSTRAINED UNPREDICTABLE data of an SVE non-fault load after an FFR
// element is FALSE: the loaded data until an access was not performed, zero
// from then on (LIRA's choice). The other choices are the shared defaults.
implementation func ConstrainUnpredictableBool(which : Unpredictable) => boolean
begin
    if which == Unpredictable_SVELDNFDATA then
        return !LIRA_NFFaulted;
    end;
    let c : Constraint = ConstrainUnpredictable(which);
    assert c IN {Constraint_TRUE, Constraint_FALSE};
    return (c == Constraint_TRUE);
end;

func LIRA_MemStatus() => PhysMemRetStatus
begin
    var st : PhysMemRetStatus;
    st.statuscode = Fault_None;
    return st;
end;

implementation func PhysMemRead{size : integer{8, 16, 32, 64, 128, 256, 512}}(
        desc : AddressDescriptor, accdesc : AccessDescriptor) => (PhysMemRetStatus, bits(size))
begin
    let off : integer = LIRA_Offset(desc.vaddress, size DIV 8);
    var value : bits(size);
    for i = 0 to (size DIV 8) - 1 do
        value[8*i+:8] = LIRA_MEM[[off + i]];
    end;
    return (LIRA_MemStatus(), value);
end;

implementation func PhysMemWrite{size : integer{8, 16, 32, 64, 128, 256, 512}}(
        desc : AddressDescriptor, accdesc : AccessDescriptor, value : bits(size)) => PhysMemRetStatus
begin
    let off : integer = LIRA_Offset(desc.vaddress, size DIV 8);
    for i = 0 to (size DIV 8) - 1 do
        LIRA_MEM[[off + i]] = value[8*i+:8];
    end;
    return LIRA_MemStatus();
end;

func LIRA_SetMemory(w0 : bits(64), win : integer, image : bits(8 * LIRA_MAX_WIN))
begin
    LIRA_W0 = w0;
    LIRA_WIN = win;
    for i = 0 to win - 1 do
        LIRA_MEM[[i]] = image[8*i+:8];
    end;
end;

func LIRA_Memory() => bits(8 * LIRA_MAX_WIN)
begin
    var image : bits(8 * LIRA_MAX_WIN) = Zeros{8 * LIRA_MAX_WIN};
    for i = 0 to LIRA_WIN - 1 do
        image[8*i+:8] = LIRA_MEM[[i]];
    end;
    return image;
end;

// -----------------------------------------------------------------------------
// The state before an instruction
// -----------------------------------------------------------------------------
func LIRA_Reset(vq : integer{1..16})
begin
    PSTATE.EL = EL0;
    PSTATE.nRW = '0';
    PSTATE.SP = '0';
    PSTATE.BTYPE = '00';
    PSTATE.[D,A,I,F] = '0000';
    PSTATE.[PAN,UAO,DIT,TCO,SSBS,IL,SS,PACM] = '00000000';
    // FP/SIMD, SVE and SME do not trap at EL0
    CPACR_EL1() = Zeros{64};
    CPACR_EL1().FPEN = '11';
    CPACR_EL1().ZEN = '11';
    CPACR_EL1().SMEN = '11';
    // the same vector length in both modes; full A64 in streaming mode
    ZCR_EL1() = Zeros{64};
    ZCR_EL1().LEN = (vq - 1)[3:0];
    SMCR_EL1() = Zeros{64};
    SMCR_EL1().LEN = (vq - 1)[3:0];
    SMCR_EL1().FA64 = '1';
    // Linux EL0: no alignment checks, SP alignment checked
    SCTLR_EL1() = Zeros{64};
    SCTLR_EL1().SA0 = '1';
    for i = 0 to 30 do
        _R[[i]] = Zeros{64};
    end;
    SP_EL0() = Zeros{64};
    for i = 0 to 31 do
        _Z[[i]] = Zeros{MAX_VL};
    end;
    for i = 0 to 15 do
        _P[[i]] = Zeros{MAX_PL};
    end;
    _FFR = Zeros{MAX_PL};
    for i = 0 to 16 * vq - 1 do                     // the ZA vectors of VL / 8 bytes
        _ZA[[i]] = Zeros{MAX_VL};
    end;
    LIRA_WIN = 0;
    LIRA_NFFaulted = FALSE;
    _PC = Zeros{64};
end;

// -----------------------------------------------------------------------------
// TRBMPAM_EL1 (bundler.py cannot generate it): the FEAT_MPAM layout, which the
// shared pseudocode reads (PMG is a PMGType)
// -----------------------------------------------------------------------------
type TRBMPAM_EL1_Type of bits(64) {
    [26] EN,
    [25:24] MPAM_SP,
    [23:16] PMG,
    [15:0] PARTID,
};

var _TRBMPAM_EL1 : TRBMPAM_EL1_Type;

accessor TRBMPAM_EL1() <=> v : TRBMPAM_EL1_Type
begin
    readonly getter
        return _TRBMPAM_EL1;
    end;

    setter
        _TRBMPAM_EL1 = v;
    end;
end;

// -----------------------------------------------------------------------------
// The state after an instruction, one `<name> <value>` line per item
// -----------------------------------------------------------------------------
func LIRA_Dump(vl : integer{128..2048})
begin
    for i = 0 to 30 do
        print("X"); print(i); print(" "); println(_R[[i]]);
    end;
    print("SP "); println(SP_EL0());
    for i = 0 to 31 do
        print("Z"); print(i); print(" "); println(_Z[[i]][vl-1:0]);
    end;
    for i = 0 to 15 do
        print("P"); print(i); print(" "); println(_P[[i]][(vl DIV 8)-1:0]);
    end;
    print("FFR "); println(_FFR[(vl DIV 8)-1:0]);
    print("NZCV "); println(PSTATE.[N,Z,C,V]);
    print("FPCR "); println(FPCR()[31:0]);
    print("FPSR "); println(FPSR()[31:0]);
    print("SVCR "); println(PSTATE.ZA :: PSTATE.SM);
    for r = 0 to (vl DIV 8) - 1 do
        print("ZA"); print(r); print(" "); println(_ZA[[r]][vl-1:0]);
    end;
    if LIRA_WIN > 0 then
        print("MEM "); println(LIRA_Memory());
    end;
end;
