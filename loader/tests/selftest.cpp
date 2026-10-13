// Self-test for the hook engine and TOML reader (no game needed). Build: tests\build_test.bat
#include "../src/Pch.h"
#include "../src/Hook.h"
#include "../src/Toml.h"

static int failures;
#define CHECK(cond) do { if (!(cond)) { printf("FALLO linea %d: %s\n", __LINE__, #cond); failures++; } else printf("ok   %s\n", #cond); } while (0)

using IntFn = int (*)(int);
static IntFn origA, origB;
static int detourA(int x) { return origA(x) * 10; }
static int detourB(int x) { return origB(x) + 100; }
static int plainAdd(int a, int b) { return a + b; }

static uint8_t* makeCode(std::initializer_list<uint8_t> bytes)
{
    // place near the exe image, like game code
    uint8_t* mem = Hook::allocNear(GetModuleHandleW(nullptr), bytes.size());
    memcpy(mem, bytes.begin(), bytes.size());
    return mem;
}

int main()
{
    // A: mov [rsp+8],rbx ; lea eax,[rcx+1] ; mov rbx,[rsp+8] ; ret
    uint8_t* a = makeCode({ 0x48, 0x89, 0x5C, 0x24, 0x08, 0x8D, 0x41, 0x01, 0x48, 0x8B, 0x5C, 0x24, 0x08, 0xC3 });
    CHECK(reinterpret_cast<IntFn>(a)(5) == 6);
    origA = reinterpret_cast<IntFn>(Hook::install(a, &detourA, 5));
    CHECK(origA != nullptr);
    CHECK(reinterpret_cast<IntFn>(a)(5) == 60);
    CHECK(origA(5) == 6);

    // B: test ecx,ecx ; js neg ; lea eax,[rcx+1] ; ret ; neg: mov eax,-1 ; ret   (js rel32 in stolen bytes)
    uint8_t* b = makeCode({ 0x85, 0xC9, 0x0F, 0x88, 0x04, 0x00, 0x00, 0x00, 0x8D, 0x41, 0x01, 0xC3,
                            0xB8, 0xFF, 0xFF, 0xFF, 0xFF, 0xC3 });
    CHECK(reinterpret_cast<IntFn>(b)(3) == 4);
    CHECK(reinterpret_cast<IntFn>(b)(-3) == -1);
    origB = reinterpret_cast<IntFn>(Hook::install(b, &detourB, 8, { { 4, 8 } }));
    CHECK(reinterpret_cast<IntFn>(b)(3) == 104);
    CHECK(reinterpret_cast<IntFn>(b)(-3) == 99);

    // Preserving thunk forwards rcx/rdx and returns rax
    using AddFn = int (*)(int, int);
    auto thunk = reinterpret_cast<AddFn>(Hook::makePreservingThunk(GetModuleHandleW(nullptr), &plainAdd));
    CHECK(thunk(20, 22) == 42);

    // writeBranch: call through near relay
    uint8_t* c = makeCode({ 0x90, 0x90, 0x90, 0x90, 0x90, 0x90, 0xC3 });
    Hook::writeBranch(c, &detourA, false, 6);
    CHECK(c[0] == 0xE9 && c[5] == 0x90);

    // TOML
    const wchar_t* path = L"selftest_config.toml";
    FILE* f = _wfopen(path, L"wb");
    fputs("# comentario\nenabled = true\nconsole = false # fin\nmods = \"mods\"\n"
          "priority = [\n  \"Mod A\",\n  'Mod B', # x\n  \"C\\\"D\"\n]\n"
          "include = [\".\"]\nname = \"Canción ñ\"\n[tabla]\nenabled = false\n", f);
    fclose(f);
    Toml t;
    CHECK(t.load(path));
    CHECK(t.getBool("enabled", false) == true);
    CHECK(t.getBool("console", true) == false);
    CHECK(t.getString("mods", "") == "mods");
    const auto pr = t.getArray("priority");
    CHECK(pr.size() == 3 && pr[0] == "Mod A" && pr[1] == "Mod B" && pr[2] == "C\"D");
    CHECK(t.getArray("include").size() == 1);
    CHECK(t.getString("name", "") == "Canción ñ");
    CHECK(!t.has("missing") && t.getBool("missing", true));
    _wremove(path);

    printf(failures ? "\n%d FALLOS\n" : "\nTODO OK\n", failures);
    return failures ? 1 : 0;
}
