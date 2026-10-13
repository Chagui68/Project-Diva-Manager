#include "Pch.h"

#include <cstdarg>

static FILE* logFile;
static bool logConsole;

void Log::init(bool console)
{
    logFile = fopen("DivaLoader.log", "w");
    logConsole = console;
    if (console)
    {
        if (!GetConsoleWindow())
            AllocConsole();
        freopen("CONOUT$", "w", stdout);
    }
}

void Log::write(const char* fmt, ...)
{
    char buffer[2048];
    va_list args;
    va_start(args, fmt);
    vsnprintf(buffer, sizeof(buffer), fmt, args);
    va_end(args);

    if (logFile)
    {
        fprintf(logFile, "%s\n", buffer);
        fflush(logFile);
    }
    if (logConsole)
        printf("[DivaLoader] %s\n", buffer);
}
