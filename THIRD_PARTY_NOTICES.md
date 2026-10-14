# Third-party notices

DivaLoader (`loader/`) uses byte patterns, patch offsets and data taken from the projects below.

| Project | Used for |
|---|---|
| [DivaModLoader](https://github.com/blueskythlikesclouds/DivaModLoader) | Byte patterns and address hints in `loader/src/Game.cpp`, patch offsets in `loader/src/Patches.cpp`, the rom-path and mod database technique, and the empty score template in `loader/src/EmptyScore.inc`. |
| [ExPatch](https://github.com/nastys/ExPatch) | The Extreme/Extra Extreme unlock flag offset (`0x11D`) and the getter patch in `loader/src/Scores.cpp`. |
| [MikuMikuLibrary](https://github.com/blueskythlikesclouds/MikuMikuLibrary) | The AES-256-CBC key and IV used by `divamgr/gamedata.py` to read the game's own CPK files for analysis. |

The Future Tone DSC opcode table in `divamgr/gamedata.py` follows the one in
[Open PD Script Editor](https://github.com/nastys/Open-PD-Script-Editor).

These projects use the MIT License:

```
MIT License

Copyright (c) 2022 Skyth          (DivaModLoader)
Copyright (c) 2023 Skyth          (MikuMikuLibrary)
Copyright (c) 2022 nastys         (ExPatch)
Copyright (c) 2020 nastys         (Open PD Script Editor)

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
