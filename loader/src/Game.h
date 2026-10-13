#pragma once

// Addresses inside DivaMegaMix.exe. Each one is found by byte pattern (IDA style, "??" = any byte),
// checked first at the address it has in the current Steam build.
// Patterns and hints come from DivaModLoader (MIT) by Skyth/blueskythlikesclouds.
namespace Game
{
    struct Sig
    {
        const char* name;
        uintptr_t hint; // address with image base 0x140000000
        const char* pattern;
        uint8_t* address = nullptr;
    };

    enum SigId
    {
        CrtMain,
        WinMainCall,
        LoadFileFromCpk,
        InitRomDirectoryPaths,
        ResolveFilePathCall,
        InitMdataMgr,
        PvParseStart,
        PvParseLoop,
        PvIfCheck1,
        PvIfCheck2,
        PvIfCheck3,
        PvU16Trunc1,
        PvU16Trunc2,
        PvU16Trunc3,
        PvU16Trunc4,
        RomCheck1,
        RomCheck2,
        PvDbDateCheck,
        ModuleIdLimit1,
        ModuleIdLimit2,
        CosLimit1,
        CosLimit2,
        OperatorNewCall,
        OperatorDelete,
        HeapCMallocAllocate,
        FindOrCreateScore,
        FindScore,
        SigCount
    };

    // Scans every signature. Returns false and fills `missing` if any is not found.
    bool resolveAll(std::string& missing);

    // One-off lookup for optional features; nullptr when the pattern is not in the executable.
    uint8_t* findPattern(const char* pattern, uintptr_t hint);
    uint8_t* at(SigId id);

    // Target of the `call rel32` / operand of the instruction at `instr`.
    uint8_t* readRel32(uint8_t* instr, ptrdiff_t instrOffset, ptrdiff_t instrSize);

    void* operatorNew(size_t size);
    void operatorDelete(void* ptr);
    void* heapCMallocAllocate(size_t type, size_t size, const char* name);
}

// std containers that live in game memory must use the game's heap.
template <class T>
class GameAllocator
{
public:
    using value_type = T;

    GameAllocator() noexcept {}
    template <class U> GameAllocator(const GameAllocator<U>&) noexcept {}

    T* allocate(size_t n) { return static_cast<T*>(Game::operatorNew(n * sizeof(T))); }
    void deallocate(T* p, size_t) noexcept { Game::operatorDelete(p); }

    template <class U> bool operator==(const GameAllocator<U>&) const noexcept { return true; }
    template <class U> bool operator!=(const GameAllocator<U>&) const noexcept { return false; }
};

namespace prj
{
    using string = std::basic_string<char, std::char_traits<char>, GameAllocator<char>>;
    template <class T> using vector = std::vector<T, GameAllocator<T>>;
    template <class T> using list = std::list<T, GameAllocator<T>>;
}
