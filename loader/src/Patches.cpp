// Byte patches to the game (offsets from DivaModLoader, MIT) and the PV ID range extension.
#include "Pch.h"
#include "Game.h"
#include "Hook.h"
#include "Loader.h"

using Hook::writeBytes;
using Hook::writeNop;

namespace
{
    // ---- Steam: never restart through the Steam client when started directly -------------------
    bool __cdecl steamRestartAppIfNecessary(uint32_t appId)
    {
        if (FILE* file = fopen("steam_appid.txt", "w"))
        {
            fprintf(file, "%u", appId);
            fclose(file);
        }
        return false;
    }

    void patchImport(const char* dllName, const char* functionName, const void* replacement)
    {
        auto* base = reinterpret_cast<uint8_t*>(GetModuleHandleW(nullptr));
        auto* dos = reinterpret_cast<IMAGE_DOS_HEADER*>(base);
        auto* nt = reinterpret_cast<IMAGE_NT_HEADERS*>(base + dos->e_lfanew);
        const auto& dir = nt->OptionalHeader.DataDirectory[IMAGE_DIRECTORY_ENTRY_IMPORT];
        if (!dir.VirtualAddress)
            return;
        for (auto* imp = reinterpret_cast<IMAGE_IMPORT_DESCRIPTOR*>(base + dir.VirtualAddress); imp->Name; imp++)
        {
            if (_stricmp(reinterpret_cast<char*>(base + imp->Name), dllName) != 0)
                continue;
            auto* names = reinterpret_cast<IMAGE_THUNK_DATA*>(base + (imp->OriginalFirstThunk ? imp->OriginalFirstThunk : imp->FirstThunk));
            auto* slots = reinterpret_cast<IMAGE_THUNK_DATA*>(base + imp->FirstThunk);
            for (; names->u1.AddressOfData; names++, slots++)
            {
                if (IMAGE_SNAP_BY_ORDINAL(names->u1.Ordinal))
                    continue;
                auto* byName = reinterpret_cast<IMAGE_IMPORT_BY_NAME*>(base + names->u1.AddressOfData);
                if (strcmp(reinterpret_cast<char*>(byName->Name), functionName) == 0)
                {
                    const auto value = reinterpret_cast<ULONGLONG>(replacement);
                    Hook::writeMemory(&slots->u1.Function, &value, sizeof(value));
                    LOG("Import %s!%s redirigido", dllName, functionName);
                    return;
                }
            }
        }
    }

    // ---- PV IDs ----------------------------------------------------------------------------------
    // The game loops pv ids 0..999 looking each one up in pv_db. We instead collect the ids present in
    // the pv_db text and feed exactly those to the loop, so any id works.
    std::vector<uint32_t> pvIdStack;

    uint32_t pvParseStart(const char* data, size_t length)
    {
        size_t i = 0;
        uint32_t lastPvId = 0;
        while (i < length)
        {
            while (i < length && (data[i] == '\t' || data[i] == '\n' || data[i] == '\r' || data[i] == ' '))
                i++;
            if (length - i > 3 && data[i] == 'p' && data[i + 1] == 'v' && data[i + 2] == '_')
            {
                i += 3;
                uint32_t pvId = 0;
                while (i < length && data[i] >= '0' && data[i] <= '9')
                    pvId = pvId * 10 + (data[i++] - '0');
                if (pvId != lastPvId && pvId != 0)
                {
                    lastPvId = pvId;
                    pvIdStack.push_back(pvId);
                }
            }
            while (i < length && data[i] != '\n' && data[i] != '\r')
                i++;
        }
        if (!pvIdStack.empty())
        {
            const uint32_t id = pvIdStack.back();
            pvIdStack.pop_back();
            return id;
        }
        return 0xFFFFFFFF;
    }

    uint32_t pvParseNext()
    {
        if (!pvIdStack.empty())
        {
            const uint32_t id = pvIdStack.back();
            pvIdStack.pop_back();
            return id;
        }
        return 0xFFFFFFFF;
    }

    // push rbp rcx rdx rsi rdi r8..r15 / reverse
    const std::initializer_list<uint8_t> PUSH_ALL = { 0x55, 0x51, 0x52, 0x56, 0x57, 0x41, 0x50, 0x41, 0x51, 0x41, 0x52,
                                                      0x41, 0x53, 0x41, 0x54, 0x41, 0x55, 0x41, 0x56, 0x41, 0x57 };
    const std::initializer_list<uint8_t> POP_ALL = { 0x41, 0x5F, 0x41, 0x5E, 0x41, 0x5D, 0x41, 0x5C, 0x41, 0x5B, 0x41,
                                                     0x5A, 0x41, 0x59, 0x41, 0x58, 0x5F, 0x5E, 0x5A, 0x59, 0x5D };
}

void Patches::init()
{
    patchImport("steam_api64.dll", "SteamAPI_RestartAppIfNecessary", &steamRestartAppIfNecessary);

    // Read loose files from rom folders instead of only CPKs.
    writeBytes(Game::at(Game::RomCheck1) + 0x10, 0xEB);
    writeBytes(Game::at(Game::RomCheck2) + 0x12, 0xEB);

    // Module ID limit (1035) and costume limit (498).
    writeBytes(Game::at(Game::ModuleIdLimit1) + 0xD, 0x89, 0xD0, 0xC3);
    writeNop(Game::at(Game::ModuleIdLimit2) + 0xB, 4);
    writeBytes(Game::at(Game::CosLimit1), 0xEB);
    writeNop(Game::at(Game::CosLimit2), 4);

    // Accept pv_db entries regardless of their date.
    writeNop(Game::at(Game::PvDbDateCheck), 6);
    LOG("Parches aplicados");
}

void Patches::initPv()
{
    // Bounds checks that are always true but would read out of range with large ids.
    writeNop(Game::at(Game::PvIfCheck1), 0xE);
    uint8_t* check2 = Game::at(Game::PvIfCheck2);
    for (int offset : { 0x0, 0x23, 0x46, 0x70, 0x93 })
        writeBytes(check2 + offset, 0x90, 0x90, 0x90, 0xEB);
    writeBytes(Game::at(Game::PvIfCheck3), 0x90, 0x90, 0x90, 0xEB);

    // MM+ UI stored pv ids as u16; the field has room for u32.
    writeNop(Game::at(Game::PvU16Trunc1), 1);
    writeNop(Game::at(Game::PvU16Trunc2), 1);
    writeNop(Game::at(Game::PvU16Trunc2) + 7, 3);
    writeBytes(Game::at(Game::PvU16Trunc3), 0x90, 0x8B);
    writeNop(Game::at(Game::PvU16Trunc4), 1);

    uint8_t* start = Game::at(Game::PvParseStart); // mov r13, imm64 (10) ; nop5 (5)  <- loop start is +0xF
    uint8_t* loop = Game::at(Game::PvParseLoop);   // inc r14 ; cmp r14, 1000 ; jb loop  (16 bytes)

    // Called at the parse start with the pv_db text in rdi and its length in rbx.
    Hook::Code s;
    s.b(PUSH_ALL)
     .b({ 0x48, 0x89, 0xF9 })                 // mov rcx, rdi
     .b({ 0x48, 0x89, 0xDA })                 // mov rdx, rbx
     .b({ 0x48, 0x83, 0xEC, 0x20 })           // sub rsp, 20h
     .movRax(reinterpret_cast<const void*>(&pvParseStart)).callRax()
     .b({ 0x48, 0x83, 0xC4, 0x20 })           // add rsp, 20h
     .b(POP_ALL)
     .b({ 0x41, 0x89, 0xC6 })                 // mov r14d, eax
     .b({ 0x49, 0xBD }).u64(0x4325C53EF368EBull) // mov r13, imm64 (the instruction we replaced)
     .b({ 0xC3 });                            // ret
    uint8_t* startStub = s.finish(start);

    // Replaces the loop end: next id from the stack, or leave the loop.
    Hook::Code l;
    l.b(PUSH_ALL)
     .b({ 0x48, 0x83, 0xEC, 0x28 })           // sub rsp, 28h (entered by jmp: keep 16-byte alignment)
     .movRax(reinterpret_cast<const void*>(&pvParseNext)).callRax()
     .b({ 0x48, 0x83, 0xC4, 0x28 })           // add rsp, 28h
     .b(POP_ALL)
     .b({ 0x83, 0xF8, 0xFF })                 // cmp eax, -1
     .b({ 0x74, 0x0F })                       // je done
     .b({ 0x41, 0x89, 0xC6 })                 // mov r14d, eax
     .movRax(start + 0xF).jmpRax()            // back to loop body
     .movRax(loop + 0x10).jmpRax();           // done: after the loop
    uint8_t* loopStub = l.finish(loop);

    if (!startStub || !loopStub)
    {
        LOG("ERROR: sin memoria para el parche de PV IDs");
        return;
    }

    // call startStub ; 10x nop  (covers the 15 replaced bytes)
    std::vector<uint8_t> patch(15, 0x90);
    patch[0] = 0xE8;
    const int32_t relStart = static_cast<int32_t>(startStub - (start + 5));
    memcpy(&patch[1], &relStart, 4);
    Hook::writeMemory(start, patch.data(), patch.size());

    uint8_t jump[5] = { 0xE9 };
    const int32_t relLoop = static_cast<int32_t>(loopStub - (loop + 5));
    memcpy(&jump[1], &relLoop, 4);
    Hook::writeMemory(loop, jump, sizeof(jump));
    LOG("PV IDs ampliados (cualquier id en pv_db)");
}
