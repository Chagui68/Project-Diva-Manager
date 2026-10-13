#pragma once

#include <map>
#include <string>
#include <vector>

// Tiny TOML subset reader: top-level `key = value` with strings, booleans, integers and
// (multi-line) arrays of strings. Tables and other types are ignored.
class Toml
{
public:
    bool load(const std::wstring& path);

    bool getBool(const std::string& key, bool fallback) const;
    std::string getString(const std::string& key, const std::string& fallback) const;
    std::vector<std::string> getArray(const std::string& key) const;
    bool has(const std::string& key) const { return values.count(key) != 0; }

    std::string error;

private:
    struct Value
    {
        std::string scalar;
        std::vector<std::string> array;
        bool isArray = false;
        bool isString = false;
    };
    std::map<std::string, Value> values;
};
