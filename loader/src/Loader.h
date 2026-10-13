#pragma once

#include <string>
#include <vector>

class Toml;

namespace Mods
{
    // read mod list, load DLL mods (PreInit), install file hooks; `skip` may hold "cpk", "db", "rom"
    void init(const Toml& rootConfig, const std::vector<std::string>& skip);
    void callInit();                    // DLL mods Init + PostInit (at WinMain)
}

namespace Patches
{
    void init();    // loose files, id limits, Steam restart
    void initPv();  // PV IDs above 999
}

namespace Scores
{
    void init(const std::string& unlockMode); // "custom" (default), "all" or "none"
    void save();
}
