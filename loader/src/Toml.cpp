#include "Pch.h"
#include "Toml.h"

namespace
{
    void skipSpace(const std::string& s, size_t& i)
    {
        for (;;)
        {
            while (i < s.size() && (s[i] == ' ' || s[i] == '\t' || s[i] == '\r' || s[i] == '\n'))
                i++;
            if (i < s.size() && s[i] == '#')
            {
                while (i < s.size() && s[i] != '\n')
                    i++;
                continue;
            }
            return;
        }
    }

    bool readString(const std::string& s, size_t& i, std::string& out)
    {
        const char quote = s[i++];
        out.clear();
        while (i < s.size() && s[i] != quote)
        {
            if (quote == '"' && s[i] == '\\' && i + 1 < s.size())
            {
                const char e = s[++i];
                out += e == 'n' ? '\n' : e == 't' ? '\t' : e;
                i++;
                continue;
            }
            out += s[i++];
        }
        if (i >= s.size())
            return false;
        i++;
        return true;
    }

    std::string trim(const std::string& s)
    {
        const size_t a = s.find_first_not_of(" \t\r\n");
        const size_t b = s.find_last_not_of(" \t\r\n");
        return a == std::string::npos ? "" : s.substr(a, b - a + 1);
    }
}

bool Toml::load(const std::wstring& path)
{
    FILE* file = _wfopen(path.c_str(), L"rb");
    if (!file)
    {
        error = "no se pudo abrir";
        return false;
    }
    std::string s;
    char buffer[4096];
    size_t n;
    while ((n = fread(buffer, 1, sizeof(buffer), file)) > 0)
        s.append(buffer, n);
    fclose(file);
    if (s.size() >= 3 && static_cast<uint8_t>(s[0]) == 0xEF)
        s.erase(0, 3);

    bool inTable = false;
    size_t i = 0;
    while (true)
    {
        skipSpace(s, i);
        if (i >= s.size())
            break;
        if (s[i] == '[')
        {
            // [table] headers: everything after the first table is ignored at top level
            inTable = true;
            while (i < s.size() && s[i] != '\n')
                i++;
            continue;
        }

        const size_t eq = s.find('=', i);
        const size_t nl = s.find('\n', i);
        if (eq == std::string::npos || (nl != std::string::npos && nl < eq))
        {
            error = "línea sin '='";
            return false;
        }
        std::string key = trim(s.substr(i, eq - i));
        if (key.size() >= 2 && (key[0] == '"' || key[0] == '\''))
            key = key.substr(1, key.size() - 2);
        i = eq + 1;
        while (i < s.size() && (s[i] == ' ' || s[i] == '\t'))
            i++;

        Value value;
        if (i < s.size() && (s[i] == '"' || s[i] == '\''))
        {
            value.isString = true;
            if (!readString(s, i, value.scalar))
            {
                error = "cadena sin cerrar en " + key;
                return false;
            }
        }
        else if (i < s.size() && s[i] == '[')
        {
            value.isArray = true;
            i++;
            for (;;)
            {
                skipSpace(s, i);
                if (i >= s.size())
                {
                    error = "array sin cerrar en " + key;
                    return false;
                }
                if (s[i] == ']')
                {
                    i++;
                    break;
                }
                if (s[i] == ',')
                {
                    i++;
                    continue;
                }
                if (s[i] == '"' || s[i] == '\'')
                {
                    std::string item;
                    if (!readString(s, i, item))
                    {
                        error = "cadena sin cerrar en " + key;
                        return false;
                    }
                    value.array.push_back(item);
                    continue;
                }
                size_t start = i;
                while (i < s.size() && s[i] != ',' && s[i] != ']' && s[i] != '\n')
                    i++;
                value.array.push_back(trim(s.substr(start, i - start)));
            }
        }
        else
        {
            size_t start = i;
            while (i < s.size() && s[i] != '\n' && s[i] != '#')
                i++;
            value.scalar = trim(s.substr(start, i - start));
        }
        if (!inTable)
            values[key] = value;
        while (i < s.size() && s[i] != '\n' && s[i] != '#')
            i++;
    }
    return true;
}

bool Toml::getBool(const std::string& key, bool fallback) const
{
    const auto it = values.find(key);
    if (it == values.end() || it->second.isArray || it->second.isString)
        return fallback;
    if (it->second.scalar == "true")
        return true;
    if (it->second.scalar == "false")
        return false;
    return fallback;
}

std::string Toml::getString(const std::string& key, const std::string& fallback) const
{
    const auto it = values.find(key);
    return it == values.end() || it->second.isArray ? fallback : it->second.scalar;
}

std::vector<std::string> Toml::getArray(const std::string& key) const
{
    const auto it = values.find(key);
    return it == values.end() || !it->second.isArray ? std::vector<std::string>() : it->second.array;
}
