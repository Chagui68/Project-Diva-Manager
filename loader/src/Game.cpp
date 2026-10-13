#include "Pch.h"
#include "Game.h"

namespace
{
    Game::Sig sigs[] =
    {
        { "CrtMain", 0x140978288, "48 89 5C 24 08 57 48 83 EC 30 B9" },
        { "WinMainCall", 0x140978389, "E8 ?? ?? ?? ?? 8B D8 E8 ?? ?? ?? ?? 84 C0 74 50" },
        { "LoadFileFromCpk", 0x1401717C0, "48 89 5C 24 10 48 89 74 24 18 48 89 7C 24 20 55 41 54 41 55 41 56 41 57 48 8D 6C 24 C9 48 81 EC E0 00 00 00 48 8B 05 ?? ?? ?? ?? 48 33 C4 48 89 45 27 45" },
        { "InitRomDirectoryPaths", 0x1402A23E0, "48 89 5C 24 08 48 89 74 24 10 48 89 7C 24 18 55 41 54 41 55 41 56 41 57 48 8B EC 48 81 EC 80 00 00 00 48 8B 05 ?? ?? ?? ?? 48 33 C4 48 89 45 F0 48" },
        { "ResolveFilePathCall", 0x14026745B, "E8 ?? ?? ?? ?? 4C 8B 65 F0" },
        { "InitMdataMgr", 0x14043E050, "48 89 5C 24 08 48 89 6C 24 10 48 89 74 24 18 48 89 7C 24 20 41 54 41 56 41 57 48 83 EC 60 48 8B 44" },
        { "PvParseStart", 0x1404BB3C1, "49 BD EB 68 F3 3E C5 25 43 00 0F 1F 44 00 00" },
        { "PvParseLoop", 0x1404BB5D6, "49 FF C6 49 81 FE E8 03 00 00" },
        { "PvIfCheck1", 0x1405807C2, "80 BC 02 40 03 00 00 00" },
        { "PvIfCheck2", 0x1405807F0, "44 38 08 75 11" },
        { "PvIfCheck3", 0x1405811E0, "80 38 00 75 4C" },
        { "PvU16Trunc1", 0x1406DE563, "66 44 89 B1 88 0A 00 00" },
        { "PvU16Trunc2", 0x1406DEA21, "66 89 91 88 0A 00 00" },
        { "PvU16Trunc3", 0x1406DF6F4, "0F BF 91 88 0A 00 00" },
        { "PvU16Trunc4", 0x1406DF748, "66 83 B9 88 0A 00 00 FF" },
        { "RomCheck1", 0x14016BFB6, "48 8B 43 10 48 89 B4 24 A8 00 00 00 48 83 F8 04 72 41" },
        { "RomCheck2", 0x151C9BACC, "48 8D 15 ?? ?? ?? ?? 48 89 F1 E8" },
        { "PvDbDateCheck", 0x1404B152D, "0F 8D D1 6E 00 00" },
        { "ModuleIdLimit1", 0x14E7DCDB0, "8B 11 31 C0 8D" },
        { "ModuleIdLimit2", 0x14E810860, "8D 42 0C 45 31" },
        { "CosLimit1", 0x14067F443, "76 03 41 8B DE" },
        { "CosLimit2", 0x1587FCBA4, "44 0F 47 C9 41 0F 10 02" },
        { "OperatorNewCall", 0x14014B889, "E8 ?? ?? ?? ?? 4C 8D 45 01" },
        { "OperatorDelete", 0x1409B1E90, "48 85 C9 74 37 53 48 83 EC 20 4C 8B" },
        { "HeapCMallocAllocate", 0x1404402B0, "48 89 6C 24 10 48 89 74 24 18 57 48 83 EC 20 0F B6 05" },
        { "FindOrCreateScore", 0x14E589750, "48 83 EC 28 49 89 CA 85" },
        { "FindScore", 0x14E5A32F0, "85 D2 0F 88 7E" },
    };
    static_assert(_countof(sigs) == Game::SigCount, "signature table out of sync");

    struct Pattern
    {
        std::vector<uint8_t> bytes;
        std::vector<bool> wild;
    };

    Pattern parse(const char* text)
    {
        Pattern p;
        for (const char* c = text; *c;)
        {
            if (*c == ' ')
            {
                c++;
                continue;
            }
            if (c[0] == '?')
            {
                p.bytes.push_back(0);
                p.wild.push_back(true);
                c += c[1] == '?' ? 2 : 1;
                continue;
            }
            p.bytes.push_back(static_cast<uint8_t>(strtoul(std::string(c, 2).c_str(), nullptr, 16)));
            p.wild.push_back(false);
            c += 2;
        }
        return p;
    }

    bool matches(const uint8_t* at, const Pattern& p)
    {
        for (size_t i = 0; i < p.bytes.size(); i++)
            if (!p.wild[i] && at[i] != p.bytes[i])
                return false;
        return true;
    }

    uint8_t* find(const Pattern& p, uintptr_t hint)
    {
        MODULEINFO info{};
        GetModuleInformation(GetCurrentProcess(), GetModuleHandleW(nullptr), &info, sizeof(info));
        auto* base = static_cast<uint8_t*>(info.lpBaseOfDll);
        const size_t size = info.SizeOfImage;

        const uintptr_t rva = hint - 0x140000000;
        if (rva + p.bytes.size() <= size && matches(base + rva, p))
            return base + rva;

        for (size_t i = 0; i + p.bytes.size() <= size; i++)
        {
            MEMORY_BASIC_INFORMATION mbi;
            if ((i & 0xFFF) == 0 && VirtualQuery(base + i, &mbi, sizeof(mbi)) &&
                (mbi.State != MEM_COMMIT || (mbi.Protect & (PAGE_NOACCESS | PAGE_GUARD))))
            {
                i = static_cast<uint8_t*>(mbi.BaseAddress) + mbi.RegionSize - base - 1;
                continue;
            }
            if (matches(base + i, p))
                return base + i;
        }
        return nullptr;
    }

    using OperatorNewFn = void* (*)(size_t);
    using OperatorDeleteFn = void (*)(void*);
    using HeapCMallocFn = void* (*)(size_t, size_t, const char*);
}

bool Game::resolveAll(std::string& missing)
{
    for (auto& sig : sigs)
    {
        if (!sig.address)
            sig.address = find(parse(sig.pattern), sig.hint);
        if (!sig.address)
            missing += std::string(missing.empty() ? "" : ", ") + sig.name;
    }
    return missing.empty();
}

uint8_t* Game::findPattern(const char* pattern, uintptr_t hint)
{
    return find(parse(pattern), hint);
}

uint8_t* Game::at(SigId id)
{
    return sigs[id].address;
}

uint8_t* Game::readRel32(uint8_t* instr, ptrdiff_t instrOffset, ptrdiff_t instrSize)
{
    uint8_t* p = instr + instrOffset;
    int32_t rel;
    memcpy(&rel, p + instrSize - 4, 4);
    return p + instrSize + rel;
}

void* Game::operatorNew(size_t size)
{
    static auto fn = reinterpret_cast<OperatorNewFn>(readRel32(at(OperatorNewCall), 0, 5));
    return fn(size);
}

void Game::operatorDelete(void* ptr)
{
    static auto fn = reinterpret_cast<OperatorDeleteFn>(at(OperatorDelete));
    fn(ptr);
}

void* Game::heapCMallocAllocate(size_t type, size_t size, const char* name)
{
    static auto fn = reinterpret_cast<HeapCMallocFn>(at(HeapCMallocAllocate));
    return fn(type, size, name);
}
