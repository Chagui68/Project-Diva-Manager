// Mod folders: each enabled mod's include dirs are put in front of the game's rom search paths,
// and mod_*.db files are merged through the game's mount-data (mdata) prefix list.
#include "Pch.h"
#include "Game.h"
#include "Hook.h"
#include "Loader.h"
#include "Toml.h"

namespace fs = std::filesystem;

namespace
{
    std::vector<std::string> modDirectories; // include folders of enabled mods, highest priority first

    struct DllMod
    {
        std::wstring directory;
        HMODULE module;
    };
    std::vector<DllMod> dllMods;

    // Keeps existing folders, relative to the game folder when possible, with forward slashes.
    std::vector<std::string> normalizeDirectories(const std::vector<std::string>& paths)
    {
        std::vector<std::string> result;
        const fs::path current = fs::current_path().lexically_normal();
        for (const auto& p : paths)
        {
            std::error_code ec;
            const fs::path path = fs::path(p).lexically_normal();
            if (!fs::is_directory(path, ec))
                continue;
            std::string full = path.string();
            std::string relative = fs::relative(path, current, ec).string();
            std::string chosen = !ec && !relative.empty() && relative.size() < full.size() ? relative : full;
            std::replace(chosen.begin(), chosen.end(), '\\', '/');
            while (!chosen.empty() && chosen.back() == '/')
                chosen.pop_back();
            result.push_back(chosen);
        }
        return result;
    }

    // ---- mod_ databases ----------------------------------------------------------------------
    // The game builds database paths as "<folder>/<prefix>_xxx_db.bin" for every prefix in the mdata
    // list. We add "\x01<mod rom dir>\x01_" prefixes and rewrite them to "<mod rom dir>/<folder>/mod_xxx".
    constexpr char MAGIC = 0x01;

    bool resolveModDatabasePath(const prj::string& path, prj::string& destination)
    {
        const size_t a = path.find(MAGIC);
        if (a == prj::string::npos)
            return false;
        const size_t b = path.find(MAGIC, a + 1);
        if (b == prj::string::npos)
            return false;

        const prj::string folder = path.substr(0, a);
        const prj::string modRom = path.substr(a + 1, b - a - 1);
        const prj::string file = path.substr(b + 1);
        destination = modRom;
        destination += "/";
        destination += folder;
        destination += "mod";
        destination += file;
        return true;
    }

    using ResolveFilePathFn = size_t (*)(prj::string&, prj::string*);
    ResolveFilePathFn originalResolveFilePath;

    size_t hookResolveFilePath(prj::string& filePath, prj::string* destFilePath)
    {
        prj::string& target = destFilePath ? *destFilePath : filePath;
        if (resolveModDatabasePath(filePath, target))
        {
            const DWORD attributes = GetFileAttributesA(target.c_str());
            return attributes != INVALID_FILE_ATTRIBUTES && !(attributes & FILE_ATTRIBUTE_DIRECTORY);
        }
        return originalResolveFilePath(filePath, destFilePath);
    }

    void addMdataPrefixes(const std::vector<std::string>& modRomDirectories)
    {
        auto& prefixes = *reinterpret_cast<prj::list<prj::string>*>(
            Game::readRel32(Game::at(Game::InitMdataMgr), 0xFE, 7));
        // reverse order so the highest priority mod is read last and wins
        for (auto it = modRomDirectories.rbegin(); it != modRomDirectories.rend(); ++it)
        {
            prj::string prefix;
            prefix += MAGIC;
            prefix += it->c_str();
            prefix += MAGIC;
            prefix += "_";
            prefixes.push_back(prefix);
        }
    }

    // ---- rom search paths ---------------------------------------------------------------------
    using VoidFn = void (*)();
    VoidFn originalInitRomDirectoryPaths;

    void hookInitRomDirectoryPaths()
    {
        originalInitRomDirectoryPaths();

        auto& romPaths = *reinterpret_cast<prj::vector<prj::string>*>(
            Game::readRel32(Game::at(Game::InitRomDirectoryPaths), 0x30, 7));

        std::vector<std::string> candidates;
        for (const auto& mod : modDirectories)
            for (const auto& rom : romPaths)
                candidates.push_back(mod + "\\" + rom.c_str());
        const std::vector<std::string> modRom = normalizeDirectories(candidates);
        if (modRom.empty())
            return;

        LOG("Carpetas rom de mods:");
        std::vector<prj::string> inserted;
        for (const auto& p : modRom)
        {
            LOG("  %s", p.c_str());
            inserted.emplace_back(p.c_str());
        }
        romPaths.insert(romPaths.begin(), inserted.begin(), inserted.end());
        addMdataPrefixes(modRom);
    }

    // ---- loose TXT files the game would only read from CPKs -----------------------------------
    struct CpkFileHandle
    {
        char type[0x100]; // "criloader"
        void* data;
        size_t dataSize;
        uint8_t reserved[0x18];
    };
    using OpenFileFromCpkFn = CpkFileHandle* (*)(const char*, bool, bool);
    OpenFileFromCpkFn originalOpenFileFromCpk;

    CpkFileHandle* hookOpenFileFromCpk(const char* fileName, bool a2, bool a3)
    {
        if (a2 && a3 && !strstr(fileName, "osage_play_data_tmp"))
        {
            if (FILE* file = fopen(fileName, "rb"))
            {
                auto* handle = static_cast<CpkFileHandle*>(Game::operatorNew(sizeof(CpkFileHandle)));
                ZeroMemory(handle, sizeof(*handle));
                strcpy_s(handle->type, "criloader");
                fseek(file, 0, SEEK_END);
                handle->dataSize = ftell(file);
                fseek(file, 0, SEEK_SET);
                handle->data = Game::heapCMallocAllocate(5, handle->dataSize + 1, "cri file extract buffer");
                fread(handle->data, handle->dataSize, 1, file);
                static_cast<uint8_t*>(handle->data)[handle->dataSize] = 0;
                fclose(file);
                return handle;
            }
        }
        return originalOpenFileFromCpk(fileName, a2, a3);
    }

    // ---- mod discovery --------------------------------------------------------------------------
    std::wstring widen(const std::string& s)
    {
        if (s.empty())
            return {};
        const int n = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, nullptr, 0);
        std::wstring w(n, L'\0');
        MultiByteToWideChar(CP_UTF8, 0, s.c_str(), -1, w.data(), n);
        w.resize(n - 1);
        return w;
    }

    std::vector<std::wstring> dllPaths;

    void readMod(const fs::path& folder)
    {
        Toml config;
        if (!config.load((folder / L"config.toml").wstring()))
        {
            LOG("  ! %s: config.toml %s", folder.filename().string().c_str(), config.error.c_str());
            return;
        }
        if (!config.getBool("enabled", true))
            return;

        LOG("  + %s", config.getString("name", folder.filename().string()).c_str());
        auto includes = config.getArray("include");
        if (!config.has("include"))
            includes.push_back(".");
        for (const auto& include : includes)
            if (!include.empty())
                modDirectories.push_back(folder.string() + "\\" + include);
        for (const auto& dll : config.getArray("dll"))
            if (!dll.empty())
                dllPaths.push_back((folder / widen(dll)).wstring());
    }

    void loadDllMods()
    {
        wchar_t savedDir[MAX_PATH];
        GetCurrentDirectoryW(MAX_PATH, savedDir);
        // lowest priority first so higher priority mods hook last
        for (auto it = dllPaths.rbegin(); it != dllPaths.rend(); ++it)
        {
            const fs::path path = fs::absolute(*it);
            if (!fs::is_regular_file(path))
            {
                LOG("  ! DLL no encontrada: %ls", path.c_str());
                continue;
            }
            const std::wstring dir = path.parent_path().wstring();
            SetCurrentDirectoryW(dir.c_str());
            SetDllDirectoryW(dir.c_str());
            HMODULE module = LoadLibraryW(path.c_str());
            SetDllDirectoryW(nullptr);
            SetCurrentDirectoryW(savedDir);
            if (!module)
            {
                LOG("  ! No se pudo cargar %ls (error %lu)", path.c_str(), GetLastError());
                continue;
            }
            LOG("  DLL %ls", path.filename().c_str());
            for (const char* name : { "PreInit", "preInit", "pre_init" })
                if (auto fn = reinterpret_cast<void (*)()>(GetProcAddress(module, name)))
                {
                    SetCurrentDirectoryW(dir.c_str());
                    fn();
                    SetCurrentDirectoryW(savedDir);
                }
            for (const char* name : { "D3DInit", "OnFrame", "OnResize" })
                if (GetProcAddress(module, name))
                    LOG("    aviso: %s no está soportado por DivaLoader", name);
            dllMods.push_back({ dir, module });
        }
    }

    void callExports(std::initializer_list<const char*> names)
    {
        wchar_t savedDir[MAX_PATH];
        GetCurrentDirectoryW(MAX_PATH, savedDir);
        for (const auto& mod : dllMods)
            for (const char* name : names)
                if (auto fn = reinterpret_cast<void (*)()>(GetProcAddress(mod.module, name)))
                {
                    SetCurrentDirectoryW(mod.directory.c_str());
                    fn();
                }
        SetCurrentDirectoryW(savedDir);
    }
}

void Mods::init(const Toml& rootConfig, const std::vector<std::string>& skip)
{
    const std::string modsDir = rootConfig.getString("mods", "mods");
    const auto priority = rootConfig.getArray("priority");
    LOG("Mods en \"%s\"", modsDir.c_str());

    std::error_code ec;
    if (!priority.empty())
    {
        LOG(" usando la lista de prioridad");
        for (const auto& name : priority)
        {
            const fs::path folder = fs::path(widen(modsDir)) / widen(name);
            if (fs::is_directory(folder, ec))
                readMod(folder);
        }
    }
    else if (fs::is_directory(widen(modsDir), ec))
    {
        LOG(" orden alfabético");
        std::vector<fs::path> folders;
        for (const auto& entry : fs::directory_iterator(widen(modsDir), ec))
            if (entry.is_directory())
                folders.push_back(entry.path());
        std::sort(folders.begin(), folders.end(), [](const fs::path& a, const fs::path& b) {
            return _wcsicmp(a.filename().c_str(), b.filename().c_str()) < 0;
        });
        for (const auto& folder : folders)
            readMod(folder);
    }

    loadDllMods();

    const auto skipped = [&](const char* part) { return std::find(skip.begin(), skip.end(), part) != skip.end(); };
    bool ok = true;
    if (!skipped("cpk"))
        // OpenFileFromCpk prologue: mov [rsp+10h], rbx (5 bytes)
        ok &= (originalOpenFileFromCpk = reinterpret_cast<OpenFileFromCpkFn>(
            Hook::install(Game::at(Game::LoadFileFromCpk), &hookOpenFileFromCpk, 5))) != nullptr;
    if (!skipped("db"))
        // ResolveFilePath prologue: mov [rsp+18h], rbx (5 bytes)
        ok &= (originalResolveFilePath = reinterpret_cast<ResolveFilePathFn>(
            Hook::install(Game::readRel32(Game::at(Game::ResolveFilePathCall), 0, 5), &hookResolveFilePath, 5))) != nullptr;
    if (!modDirectories.empty() && !skipped("rom"))
        // InitRomDirectoryPaths prologue: mov [rsp+8], rbx (5 bytes)
        ok &= (originalInitRomDirectoryPaths = reinterpret_cast<VoidFn>(
            Hook::install(Game::at(Game::InitRomDirectoryPaths), &hookInitRomDirectoryPaths, 5))) != nullptr;
    if (!ok)
        LOG("ERROR: falló la instalación de algún hook de archivos");
    LOG("%zu carpeta(s) de mods activas, %zu DLL", modDirectories.size(), dllMods.size());
}

void Mods::callInit()
{
    callExports({ "Init", "init" });
    callExports({ "PostInit", "postInit", "post_init" });
}
