// DivaLoader: mod loader for Hatsune Miku: Project DIVA Mega Mix+.
// Loaded by the game as dinput8.dll; forwards DirectInput8Create to the system DLL.
//
// Timeline:
//   DllMain        -> find game addresses, hook the CRT entry point (nothing heavy under loader lock)
//   CRT main hook  -> read config, patch the game, register mod folders, load DLL mods (PreInit)
//   WinMain hook   -> DLL mods Init/PostInit, PV ID patch
#include "Pch.h"
#include <unknwn.h>
#include "Game.h"
#include "Hook.h"
#include "Loader.h"
#include "Toml.h"

using DirectInput8CreateFn = HRESULT(WINAPI*)(HINSTANCE, DWORD, REFIID, LPVOID*, LPUNKNOWN);
static DirectInput8CreateFn realDirectInput8Create;

static void loadRealDInput()
{
    if (realDirectInput8Create)
        return;
    wchar_t path[MAX_PATH];
    GetSystemDirectoryW(path, MAX_PATH);
    wcscat_s(path, L"\\dinput8.dll");
    if (HMODULE module = LoadLibraryW(path))
        realDirectInput8Create = reinterpret_cast<DirectInput8CreateFn>(GetProcAddress(module, "DirectInput8Create"));
}

extern "C" __declspec(dllexport) HRESULT WINAPI DirectInput8Create(HINSTANCE instance, DWORD version, REFIID riid,
                                                                  LPVOID* out, LPUNKNOWN outer)
{
    loadRealDInput();
    return realDirectInput8Create ? realDirectInput8Create(instance, version, riid, out, outer) : E_FAIL;
}

using EntryFn = int(WINAPI*)(HINSTANCE, HINSTANCE, LPSTR, int);
static EntryFn originalCrtMain;
static EntryFn originalWinMain;
static bool loaderEnabled;
static std::vector<std::string> skip; // config `debug_skip`: parts to leave out while diagnosing

static bool skipped(const char* part)
{
    return std::find(skip.begin(), skip.end(), part) != skip.end();
}

// Logs crashes (code + module offset) to DivaLoader.log; the game keeps handling them as usual.
static LONG CALLBACK logFatalException(EXCEPTION_POINTERS* info)
{
    static volatile LONG logged;
    const DWORD code = info->ExceptionRecord->ExceptionCode;
    const bool fatal = code == EXCEPTION_ACCESS_VIOLATION || code == EXCEPTION_ILLEGAL_INSTRUCTION ||
                       code == EXCEPTION_PRIV_INSTRUCTION || code == EXCEPTION_STACK_OVERFLOW ||
                       code == EXCEPTION_INT_DIVIDE_BY_ZERO || code == 0xC0000409;
    if (fatal && InterlockedIncrement(&logged) <= 20)
    {
        const auto address = reinterpret_cast<uintptr_t>(info->ExceptionRecord->ExceptionAddress);
        HMODULE module = nullptr;
        wchar_t name[MAX_PATH] = L"?";
        GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS | GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
                           reinterpret_cast<LPCWSTR>(address), &module);
        if (module)
            GetModuleFileNameW(module, name, MAX_PATH);
        const wchar_t* shortName = wcsrchr(name, L'\\') ? wcsrchr(name, L'\\') + 1 : name;
        LOG("EXCEPCIÓN %08lX en %p (%ls+0x%llX) datos %llX %llX hilo %lu", code, info->ExceptionRecord->ExceptionAddress,
            shortName, static_cast<unsigned long long>(address - reinterpret_cast<uintptr_t>(module)),
            static_cast<unsigned long long>(info->ExceptionRecord->ExceptionInformation[0]),
            static_cast<unsigned long long>(info->ExceptionRecord->ExceptionInformation[1]), GetCurrentThreadId());
    }
    return EXCEPTION_CONTINUE_SEARCH;
}

static int WINAPI hookWinMain(HINSTANCE instance, HINSTANCE prev, LPSTR cmdLine, int show)
{
    if (loaderEnabled)
    {
        Mods::callInit();
        if (!skipped("pv"))
            Patches::initPv();
        LOG("Listo. Iniciando el juego.");
    }
    const int result = originalWinMain(instance, prev, cmdLine, show);
    LOG("WinMain terminó con código %d", result);
    return result;
}

static int WINAPI hookCrtMain(HINSTANCE instance, HINSTANCE prev, LPSTR cmdLine, int show)
{
    loadRealDInput();

    Toml config;
    if (!config.load(L"config.toml") && GetFileAttributesW(L"config.toml") != INVALID_FILE_ATTRIBUTES)
    {
        const std::string msg = "Error en config.toml: " + config.error;
        MessageBoxA(nullptr, msg.c_str(), "DivaLoader", MB_ICONERROR);
    }

    loaderEnabled = config.getBool("enabled", true);
    if (loaderEnabled)
    {
        Log::init(config.getBool("console", false));
        LOG("DivaLoader 1.0");
        skip = config.getArray("debug_skip");
        for (const auto& s : skip)
            LOG("debug_skip: %s", s.c_str());
        AddVectoredExceptionHandler(0, &logFatalException);
        if (!skipped("patches"))
            Patches::init();
        if (!skipped("scores"))
            Scores::init(config.getString("unlock_extreme", "custom"));
        Mods::init(config, skip);

        uint8_t* winMain = Game::readRel32(Game::at(Game::WinMainCall), 0, 5);
        // prologue: push rbp / push rbx / push rdi / push r12  (40 55 53 57 41 54)
        originalWinMain = reinterpret_cast<EntryFn>(Hook::install(winMain, &hookWinMain, 6));
        if (!originalWinMain)
            LOG("ERROR: no se pudo enganchar WinMain");
    }
    return originalCrtMain(instance, prev, cmdLine, show);
}

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID)
{
    if (reason == DLL_PROCESS_ATTACH)
    {
        DisableThreadLibraryCalls(instance);

        std::string missing;
        if (!Game::resolveAll(missing))
        {
            const std::string msg = "Versión del juego no compatible con DivaLoader.\nNo se encontró: " + missing;
            MessageBoxA(nullptr, msg.c_str(), "DivaLoader", MB_ICONERROR);
            return TRUE; // keep the game running without mods
        }
        // prologue: mov [rsp+8], rbx  (48 89 5C 24 08)
        originalCrtMain = reinterpret_cast<EntryFn>(Hook::install(Game::at(Game::CrtMain), &hookCrtMain, 5));
    }
    else if (reason == DLL_PROCESS_DETACH)
    {
        if (loaderEnabled)
            Scores::save();
    }
    return TRUE;
}
