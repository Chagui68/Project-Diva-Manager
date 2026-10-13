#pragma once

#include <cstdint>
#include <initializer_list>
#include <vector>

// Minimal x64 hooking engine. The caller states how many bytes to steal at the target (whole
// instructions only) and where rel32 fields sit inside them, so no disassembler is needed.
namespace Hook
{
    struct RelFix
    {
        uint8_t dispOffset; // offset of the rel32/disp32 field inside the stolen bytes
        uint8_t instrEnd;   // offset where that instruction ends (rel32 base)
    };

    // Executable memory within +-2 GB of `nearAddress`.
    uint8_t* allocNear(const void* nearAddress, size_t size);

    bool writeMemory(void* address, const void* data, size_t size);
    bool writeNop(void* address, size_t count);

    template <typename... Bytes>
    bool writeBytes(void* address, Bytes... bytes)
    {
        const uint8_t data[] = { static_cast<uint8_t>(bytes)... };
        return writeMemory(address, data, sizeof(data));
    }

    // Writes E8/E9 rel32 at `address` towards `destination` (via a near relay), NOP-filling up to patchSize.
    bool writeBranch(void* address, const void* destination, bool call, size_t patchSize = 5);

    // Detours `target` to `detour`. Returns a trampoline that runs the original function.
    void* install(void* target, const void* detour, size_t stolen, std::initializer_list<RelFix> fixes = {});

    // Byte emitter for hand-written stubs; finish() copies the code next to `nearAddress`.
    class Code
    {
    public:
        Code& b(std::initializer_list<uint8_t> bytes);
        Code& u32(uint32_t value);
        Code& u64(uint64_t value);
        Code& movRax(const void* value);   // mov rax, imm64
        Code& callRax();                    // call rax
        Code& jmpRax();                     // jmp rax
        Code& pushVolatileAndSaved();       // push rbx, rcx, rdx, rsi, rdi, r8..r15
        Code& popVolatileAndSaved();
        size_t size() const { return bytes.size(); }
        uint8_t* finish(const void* nearAddress);

        std::vector<uint8_t> bytes;
    };

    // Stub that saves every register except rax, aligns the stack and calls `function` with the
    // incoming rcx/rdx/r8/r9. For game functions whose callers rely on registers being preserved.
    uint8_t* makePreservingThunk(const void* nearAddress, const void* function);
}
