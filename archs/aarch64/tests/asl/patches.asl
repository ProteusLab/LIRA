// Replacements (`aslref --patch`) of shared pseudocode functions for the
// machine of machine.asl.

// No address translation (the identity, Normal memory); an address outside the
// memory window is a data abort, see PhysMemRead/PhysMemWrite.
func AArch64_TranslateAddress(va : bits(64), accdesc : AccessDescriptor,
                              aligned : boolean, size : integer) => AddressDescriptor
begin
    let off : integer = LIRA_Offset(va, size);
    var full_addr : FullAddress;
    full_addr.address = va[NUM_PABITS-1:0];
    return CreateAddressDescriptor(va, full_addr, LIRA_NormalMemory, accdesc);
end;

// Taking an exception ends the instruction with its syndrome (ESR_ELx).
noreturn func AArch64_TakeException(target_el : bits(2), exception_in : ExceptionRecord,
                                    preferred_exception_return : bits(64),
                                    vect_offset_in : integer)
begin
    let (ec, il) = AArch64_ExceptionClass(exception_in.exceptype, target_el);
    throw LIRA_Exception {
        esr = Zeros{8} :: exception_in.syndrome.iss2 :: ec[5:0] :: il :: exception_in.syndrome.iss
    };
end;
