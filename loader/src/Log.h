#pragma once

#include <cstdio>

namespace Log
{
    void init(bool console);
    void write(const char* fmt, ...);
}

#define LOG(...) Log::write(__VA_ARGS__)
