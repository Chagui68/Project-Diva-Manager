#include "Pch.h"
#include "Hook.h"

namespace
{
    struct Pool
    {
        uint8_t* base;
        size_t used;
        size_t capacity;
    };

    std::vector<Pool> pools;
    constexpr size_t POOL_SIZE = 0x10000;
    constexpr intptr_t SEARCH_RANGE = 0x40000000; // 1 GB each side; the game image is ~600 MB

    bool fitsRel32(intptr_t value)
    {
        return value >= INT32_MIN && value <= INT32_MAX;
    }

    void writeAbsJump(uint8_t* at, const void* destination)
    {
        // jmp qword ptr [rip+0] ; dq destination
        const uint8_t code[] = { 0xFF, 0x25, 0x00, 0x00, 0x00, 0x00 };
        memcpy(at, code, sizeof(code));
        memcpy(at + sizeof(code), &destination, sizeof(destination));
    }
}

uint8_t* Hook::allocNear(const void* nearAddress, size_t size)
{
    size = (size + 15) & ~size_t(15);
    for (auto& pool : pools)
    {
        if (pool.used + size <= pool.capacity &&
            fitsRel32(reinterpret_cast<intptr_t>(pool.base) - reinterpret_cast<intptr_t>(nearAddress)) &&
            fitsRel32(reinterpret_cast<intptr_t>(pool.base + pool.capacity) - reinterpret_cast<intptr_t>(nearAddress)))
        {
            uint8_t* result = pool.base + pool.used;
            pool.used += size;
            return result;
        }
    }

    SYSTEM_INFO info;
    GetSystemInfo(&info);
    const uintptr_t granularity = info.dwAllocationGranularity;
    const uintptr_t center = reinterpret_cast<uintptr_t>(nearAddress);
    uintptr_t address = center > uintptr_t(SEARCH_RANGE) ? center - SEARCH_RANGE : granularity;
    const uintptr_t end = center + SEARCH_RANGE;

    while (address < end)
    {
        MEMORY_BASIC_INFORMATION mbi;
        if (!VirtualQuery(reinterpret_cast<void*>(address), &mbi, sizeof(mbi)))
            break;

        const uintptr_t regionBase = reinterpret_cast<uintptr_t>(mbi.BaseAddress);
        if (mbi.State == MEM_FREE)
        {
            const uintptr_t aligned = (regionBase + granularity - 1) & ~(granularity - 1);
            if (aligned + POOL_SIZE <= regionBase + mbi.RegionSize)
            {
                void* memory = VirtualAlloc(reinterpret_cast<void*>(aligned), POOL_SIZE,
                                            MEM_RESERVE | MEM_COMMIT, PAGE_EXECUTE_READWRITE);
                if (memory)
                {
                    pools.push_back({ static_cast<uint8_t*>(memory), size, POOL_SIZE });
                    return static_cast<uint8_t*>(memory);
                }
            }
        }
        address = regionBase + mbi.RegionSize;
    }

    LOG("ERROR: no free memory nearAddress %p", nearAddress);
    return nullptr;
}

bool Hook::writeMemory(void* address, const void* data, size_t size)
{
    DWORD oldProtect;
    if (!VirtualProtect(address, size, PAGE_EXECUTE_READWRITE, &oldProtect))
        return false;
    memcpy(address, data, size);
    VirtualProtect(address, size, oldProtect, &oldProtect);
    FlushInstructionCache(GetCurrentProcess(), address, size);
    return true;
}

bool Hook::writeNop(void* address, size_t count)
{
    std::vector<uint8_t> nops(count, 0x90);
    return writeMemory(address, nops.data(), count);
}

bool Hook::writeBranch(void* address, const void* destination, bool call, size_t patchSize)
{
    uint8_t* relay = allocNear(address, 14);
    if (!relay)
        return false;
    writeAbsJump(relay, destination);

    std::vector<uint8_t> patch(std::max<size_t>(patchSize, 5), 0x90);
    patch[0] = call ? 0xE8 : 0xE9;
    const int32_t rel = static_cast<int32_t>(relay - (static_cast<uint8_t*>(address) + 5));
    memcpy(&patch[1], &rel, 4);
    return writeMemory(address, patch.data(), patch.size());
}

void* Hook::install(void* target, const void* detour, size_t stolen, std::initializer_list<RelFix> fixes)
{
    auto* source = static_cast<uint8_t*>(target);
    uint8_t* trampoline = allocNear(source, stolen + 28);
    if (!trampoline || stolen < 5)
        return nullptr;

    memcpy(trampoline, source, stolen);
    for (const auto& fix : fixes)
    {
        int32_t disp;
        memcpy(&disp, source + fix.dispOffset, 4);
        const intptr_t absolute = reinterpret_cast<intptr_t>(source) + fix.instrEnd + disp;
        const intptr_t moved = absolute - (reinterpret_cast<intptr_t>(trampoline) + fix.instrEnd);
        if (!fitsRel32(moved))
            return nullptr;
        const int32_t newDisp = static_cast<int32_t>(moved);
        memcpy(trampoline + fix.dispOffset, &newDisp, 4);
    }
    writeAbsJump(trampoline + stolen, source + stolen);

    uint8_t* relay = trampoline + stolen + 14;
    writeAbsJump(relay, detour);

    std::vector<uint8_t> patch(stolen, 0x90);
    patch[0] = 0xE9;
    const int32_t rel = static_cast<int32_t>(relay - (source + 5));
    memcpy(&patch[1], &rel, 4);
    if (!writeMemory(source, patch.data(), patch.size()))
        return nullptr;
    return trampoline;
}

Hook::Code& Hook::Code::b(std::initializer_list<uint8_t> values)
{
    bytes.insert(bytes.end(), values);
    return *this;
}

Hook::Code& Hook::Code::u32(uint32_t value)
{
    const auto* p = reinterpret_cast<const uint8_t*>(&value);
    bytes.insert(bytes.end(), p, p + 4);
    return *this;
}

Hook::Code& Hook::Code::u64(uint64_t value)
{
    const auto* p = reinterpret_cast<const uint8_t*>(&value);
    bytes.insert(bytes.end(), p, p + 8);
    return *this;
}

Hook::Code& Hook::Code::movRax(const void* value)
{
    return b({ 0x48, 0xB8 }).u64(reinterpret_cast<uint64_t>(value));
}

Hook::Code& Hook::Code::callRax()
{
    return b({ 0xFF, 0xD0 });
}

Hook::Code& Hook::Code::jmpRax()
{
    return b({ 0xFF, 0xE0 });
}

Hook::Code& Hook::Code::pushVolatileAndSaved()
{
    // rbx rcx rdx rsi rdi r8 r9 r10 r11 r12 r13 r14 r15
    return b({ 0x53, 0x51, 0x52, 0x56, 0x57, 0x41, 0x50, 0x41, 0x51, 0x41, 0x52, 0x41, 0x53,
               0x41, 0x54, 0x41, 0x55, 0x41, 0x56, 0x41, 0x57 });
}

Hook::Code& Hook::Code::popVolatileAndSaved()
{
    return b({ 0x41, 0x5F, 0x41, 0x5E, 0x41, 0x5D, 0x41, 0x5C, 0x41, 0x5B, 0x41, 0x5A, 0x41, 0x59,
               0x41, 0x58, 0x5F, 0x5E, 0x5A, 0x59, 0x5B });
}

uint8_t* Hook::Code::finish(const void* nearAddress)
{
    uint8_t* memory = allocNear(nearAddress, bytes.size());
    if (memory)
    {
        memcpy(memory, bytes.data(), bytes.size());
        FlushInstructionCache(GetCurrentProcess(), memory, bytes.size());
    }
    return memory;
}

uint8_t* Hook::makePreservingThunk(const void* nearAddress, const void* function)
{
    Code c;
    c.pushVolatileAndSaved()
     .b({ 0x49, 0x89, 0xE7 })             // mov r15, rsp
     .b({ 0x48, 0x83, 0xEC, 0x20 })       // sub rsp, 20h
     .b({ 0x48, 0x83, 0xE4, 0xF0 })       // and rsp, -16
     .movRax(function).callRax()
     .b({ 0x4C, 0x89, 0xFC })             // mov rsp, r15
     .popVolatileAndSaved()
     .b({ 0xC3 });
    return c.finish(nearAddress);
}
