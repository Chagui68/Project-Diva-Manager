// Score slots for PV ids the game's save data has no room for. Without this the game gets a null
// score for custom songs. Extra scores are kept in DivaLoader_scores.bin next to the game.
#include "Pch.h"
#include "Game.h"
#include "Hook.h"
#include "Loader.h"

namespace
{
    struct Score
    {
        int32_t pvId;
        uint8_t data[0x132C];
    };
    static_assert(sizeof(Score) == 0x1330, "game score size");

    const uint8_t EMPTY_SCORE_DATA[] =
    {
#include "EmptyScore.inc"
    };
    static_assert(sizeof(EMPTY_SCORE_DATA) == sizeof(Score), "empty score size");

    constexpr char FILE_NAME[] = "DivaLoader_scores.bin";
    constexpr uint32_t FILE_MAGIC = 0x53434C44; // "DLCS"

    std::unordered_map<int32_t, Score> scores;
    CRITICAL_SECTION lock;
    bool unlockCustom = true;

    // Byte of a score entry the game reads to decide whether Extreme/Extra Extreme are playable
    // (the same flag ExPatch by nas sets, MIT). Custom songs get it set so they start unlocked.
    constexpr size_t EXTREME_UNLOCK_OFFSET = 0x11D;

    constexpr int32_t FIRST_CUSTOM_PV_ID = 1000; // the game's own songs are all below this

    void unlockExtreme(Score& score)
    {
        if (unlockCustom)
            reinterpret_cast<uint8_t*>(&score)[EXTREME_UNLOCK_OFFSET] = 1;
    }

    // Custom songs whose score lives in the game's own save data get the flag too.
    Score* unlockIfCustom(Score* score, int32_t pvId)
    {
        if (score && pvId >= FIRST_CUSTOM_PV_ID)
            unlockExtreme(*score);
        return score;
    }

    using FindScoreFn = Score* (*)(void*, int32_t);
    FindScoreFn originalFindOrCreateScore;
    FindScoreFn originalFindScore;

    Score* findOrCreateScore(void* saveData, int32_t pvId)
    {
        EnterCriticalSection(&lock);
        Score* result = nullptr;
        if (pvId >= 0)
        {
            const auto it = scores.find(pvId);
            if (it != scores.end())
                result = &it->second;
        }
        if (!result)
        {
            result = originalFindOrCreateScore(saveData, pvId);
            if (!result && pvId >= 0)
            {
                result = &scores[pvId];
                memcpy(result, EMPTY_SCORE_DATA, sizeof(Score));
                result->pvId = pvId;
                unlockExtreme(*result);
                LOG("Nueva puntuación para pv_%d", pvId);
            }
        }
        LeaveCriticalSection(&lock);
        return unlockIfCustom(result, pvId);
    }

    Score* findScore(void* saveData, int32_t pvId)
    {
        EnterCriticalSection(&lock);
        Score* result = nullptr;
        if (pvId >= 0)
        {
            const auto it = scores.find(pvId);
            if (it != scores.end())
                result = &it->second;
        }
        LeaveCriticalSection(&lock);
        return result ? result : unlockIfCustom(originalFindScore(saveData, pvId), pvId);
    }

    void load()
    {
        FILE* file = fopen(FILE_NAME, "rb");
        if (!file)
            return;
        uint32_t magic = 0, count = 0;
        if (fread(&magic, 4, 1, file) == 1 && magic == FILE_MAGIC && fread(&count, 4, 1, file) == 1)
        {
            for (uint32_t i = 0; i < count; i++)
            {
                Score score;
                if (fread(&score, sizeof(score), 1, file) != 1)
                    break;
                unlockExtreme(score);
                scores[score.pvId] = score;
            }
        }
        fclose(file);
        LOG("%zu puntuación(es) de canciones personalizadas cargadas", scores.size());
    }
}

void Scores::init(const std::string& unlockMode)
{
    InitializeCriticalSection(&lock);
    unlockCustom = unlockMode != "none";
    load();

    if (unlockMode == "all")
    {
        // ExPatch-style: the getter "movzx eax, byte [rcx+11Dh] ; ret" becomes "mov eax, 1 ; ret"
        if (uint8_t* getter = Game::findPattern("0F B6 81 1D 01 00 00 C3", 0x1401D9BC0))
        {
            Hook::writeBytes(getter, 0xB8, 0x01, 0x00, 0x00, 0x00, 0xC3);
            LOG("Extremo y Extra Extremo desbloqueados en todas las canciones");
        }
        else
            LOG("aviso: no se encontró la función de desbloqueo de Extremo");
    }
    else
        LOG("Extremo/Extra Extremo desbloqueados en canciones custom: %s", unlockCustom ? "sí" : "no");

    // Callers expect these game functions to preserve every register, so the detours go through
    // a thunk that saves them all before calling into C++.
    uint8_t* findOrCreate = Game::at(Game::FindOrCreateScore); // sub rsp,28h ; mov r10,rcx  (4 + 3 bytes)
    uint8_t* find = Game::at(Game::FindScore);                 // test edx,edx ; js rel32    (2 + 6 bytes)
    originalFindOrCreateScore = reinterpret_cast<FindScoreFn>(
        Hook::install(findOrCreate, Hook::makePreservingThunk(findOrCreate, &findOrCreateScore), 7));
    originalFindScore = reinterpret_cast<FindScoreFn>(
        Hook::install(find, Hook::makePreservingThunk(find, &findScore), 8, { { 4, 8 } }));
    if (!originalFindOrCreateScore || !originalFindScore)
        LOG("ERROR: no se pudieron enganchar las puntuaciones");
}

void Scores::save()
{
    if (scores.empty())
        return;
    FILE* file = fopen(FILE_NAME, "wb");
    if (!file)
        return;
    const uint32_t count = static_cast<uint32_t>(scores.size());
    fwrite(&FILE_MAGIC, 4, 1, file);
    fwrite(&count, 4, 1, file);
    for (const auto& [id, score] : scores)
        fwrite(&score, sizeof(score), 1, file);
    fclose(file);
}
