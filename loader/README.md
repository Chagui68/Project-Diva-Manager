# DivaLoader

Mod loader propio para **Hatsune Miku: Project DIVA Mega Mix+** (Steam). Se carga como `dinput8.dll` y es
compatible con la estructura de mods de DivaModLoader:

```
mods/<Mod>/config.toml
mods/<Mod>/rom/...
```

## Qué hace

| Función | Cómo |
|---|---|
| Archivos sueltos de mods | Inserta las carpetas `include` de cada mod activo delante de las rutas `rom` del juego. |
| Bases de datos `mod_*` (`mod_pv_db.txt`, `mod_spr_db.bin`, etc.) | Añade cada mod a la lista de prefijos de bases de datos del juego y resuelve sus rutas. |
| PV ID mayores que 999 | Parchea el bucle que lee `pv_db` para que recorra los IDs que existen en el archivo. |
| Extremo y Extra Extremo desbloqueados en canciones custom | Activa el byte `0x11D` de su registro de puntuación (el mismo que usa [ExPatch](https://github.com/nastys/ExPatch), MIT). Con `unlock_extreme = "all"` aplica el parche de ExPatch a todas las canciones. |
| Puntuaciones de canciones nuevas | Crea huecos de puntuación para IDs que el guardado del juego no contempla y los guarda en `DivaLoader_scores.bin`. |
| `.txt` sueltos que el juego solo leería del CPK | Hook de apertura de archivos. |
| Límites de módulos (1035) y trajes (498), y comprobación de fecha de `pv_db` | Parches de bytes. |
| Mods DLL | Carga la `dll = [...]` de cada mod y llama a sus funciones exportadas `PreInit`, `Init` y `PostInit`. No soporta `D3DInit`, `OnFrame` ni `OnResize`. |
| Arranque fuera de Steam | Redirige `SteamAPI_RestartAppIfNecessary` y escribe `steam_appid.txt`. |
| Diagnóstico | Escribe `DivaLoader.log` junto al juego, con las excepciones fatales y la dirección donde ocurrieron. |

El motor de hooks (`src/Hook.cpp`) es propio y no usa Detours ni MinHook. Cada hook declara cuántos bytes
reemplaza y dónde hay saltos relativos que hay que reubicar.

## Compilar

Requiere Visual Studio Build Tools 2022 con la carga de trabajo «Desarrollo de escritorio con C++».

```bash
loader\build.bat
```

El resultado queda en `loader\build\dinput8.dll`. El repositorio también trae una copia ya compilada en
`loader\bin\dinput8.dll`, así que no hace falta compilar para usarlo. El botón **Instalar DivaLoader** de
Diva Manager copia al juego la versión compilada en local si existe, o si no la de `loader\bin`. Si ya
había otro `dinput8.dll`, lo guarda como `dinput8.dll.bak`.

Pruebas del motor de hooks y del lector TOML, sin el juego:

```bash
loader\tests\build_test.bat
```

## config.toml (carpeta del juego)

```toml
enabled = true      # false desactiva el loader
console = false     # true abre una consola con el log
mods = "mods"       # carpeta de mods
priority = [        # opcional: orden de carga, el primero tiene más prioridad
  "MiMod",
]
unlock_extreme = "custom"  # "custom" (canciones nuevas), "all" (todas) o "none"
debug_skip = []     # diagnóstico: "patches", "scores", "pv", "cpk", "db", "rom"
```

Sin `priority`, los mods cargan en orden alfabético. Con `priority`, solo cargan los mods que aparecen en la lista.

## Compatibilidad

Las direcciones se buscan por patrón de bytes. Primero se comprueban en la dirección que tienen en la build
actual de Steam y, si no coinciden, se busca en todo el ejecutable. Si una actualización del juego cambia el
código, el loader avisa y el juego arranca sin mods.

## Créditos

Los patrones de bytes, los offsets de los parches y la técnica de rutas `rom` y prefijos de bases de datos
vienen de [DivaModLoader](https://github.com/blueskythlikesclouds/DivaModLoader) (licencia MIT). De ahí
también sale la plantilla de puntuación vacía (`src/EmptyScore.inc`). El código de este loader es una
implementación nueva.
