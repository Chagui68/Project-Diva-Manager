# Diva Manager

Gestor de canciones para **Hatsune Miku: Project DIVA Mega Mix+** (Steam), con su propio mod loader,
[DivaLoader](loader/README.md). Los mods de DivaModLoader también funcionan.

- Importa canciones en `.mp4` (también `.mkv`, `.webm`, `.mov`, `.mp3`, `.m4a`, `.ogg`, `.wav`, `.flac`).
- Genera las notas automáticamente a partir del audio, en Fácil, Normal, Difícil, Extremo y Extra Extremo.
  Incluye notas múltiples (2 a 4 botones a la vez), deslizamientos L/R y deslizamientos encadenados.
- Convierte el video a `.usm` 720p con fotogramas constantes (máx. 30), el contenedor que usa el juego.
- Activa, desactiva, ordena por prioridad y elimina mods.
- Instala o actualiza DivaLoader en la carpeta del juego.
- Lanza el juego desde Steam.

## Requisitos

- Python 3.12 con los paquetes de `requirements.txt`:
  ```bash
  python -m pip install --user -r requirements.txt
  ```
- FFmpeg (incluye `ffmpeg.exe` y `ffprobe.exe`). Es obligatorio para importar `.mp4`:
  ```bash
  winget install Gyan.FFmpeg
  ```
  Si no está en el PATH, usa el botón **Buscar…** e indica dónde está `ffmpeg.exe`.
- DivaLoader: el repositorio trae una copia ya compilada en `loader\bin\dinput8.dll`. Instálala con el
  botón **Instalar DivaLoader** del gestor. Solo hace falta compilar (`loader\build.bat`, con Visual Studio
  Build Tools y C++) si cambias el código del loader.
- yt-dlp, opcional: solo para descargar desde URL. El gestor ofrece instalarlo la primera vez.

## Uso

Haz doble clic en `diva_manager.pyw`, o ejecuta:

```bash
python diva_manager.pyw
```

1. **➕ Importar canción…**: elige el archivo y ajusta título, artista, personaje, PV ID, dificultades,
   densidad de notas y códec de video.
   Si seleccionas varios archivos a la vez, se importan en lote con los mismos ajustes.
   **🌐 Desde URL…**: pega URLs de video, una por línea. Funciona con YouTube y otros sitios que soporta
   [yt-dlp](https://github.com/yt-dlp/yt-dlp). La primera vez ofrece instalar yt-dlp con pip. Los videos se
   guardan en `downloads/` antes de importarse. Usa solo videos que tengas derecho a descargar y usar: tuyos,
   con licencia libre o con permiso del autor.
2. Cada canción se guarda como un mod propio en `mods/DivaManager_pv<ID>_<título>/`.
3. **Vista previa**: muestra las notas generadas sobre la pantalla de juego y en una línea de tiempo.
4. **Regenerar…**: crea otra variante (semilla), cambia la densidad, ajusta el **desfase** de las notas en ms
   si notas que llegan antes o después de la música, y opcionalmente reconvierte el video.
   **Actualizar todas** aplica la sincronización nueva, Extra Extremo y el video 720p a todas tus canciones.
5. **▶ Jugar**: abre el juego con `steam://rungameid/1761390`.

## Cómo se generan las notas

El análisis está en `divamgr/analysis.py` y usa solo numpy y scipy. No usa librosa porque Windows
Application Control bloquea su dependencia `numba` en esta PC.

| Elemento | Cómo se deriva de la canción |
|---|---|
| Tempo y pulso | Tempo aproximado por autocorrelación y beat tracking. Luego se ajustan el periodo y la fase a toda la canción, plegando los ataques en intervalos de 2 ms. El bajo decide entre pulso y contrapulso, y ventanas de 16 pulsos verifican el ajuste o siguen la deriva si el tempo no es constante. |
| Compases | Fase de compás donde caen los golpes graves (bombo). |
| Momento de cada nota | Ataques fuertes cuantizados a la rejilla (negra, corchea o semicorchea según la dificultad). Las secciones más intensas reciben más notas. |
| Botón (△ ○ × □) | La banda de frecuencia que destaca en ese golpe: grave = ×, medio-grave = ○, medio-agudo = □, agudo = △. Las ráfagas rápidas comparten botón, como en los charts oficiales. |
| Holds | Sonidos tonales que siguen sonando más de un tiempo (voz o sintes largos). |
| Notas múltiples | Acentos donde todas las bandas golpean a la vez (platillo, bombo y acorde): 2 botones desde Normal, 3 en Difícil y hasta 4 en Extremo y Extra Extremo, solo en los golpes más fuertes. |
| Deslizamientos (L/R) | Golpes brillantes, donde destacan los agudos. La dirección sigue la melodía: si sube, R; si baja, L. Si el sonido se sostiene, se convierte en deslizamiento encadenado. |
| Posición en pantalla | Trayectorias curvas que siguen las frases. La altura sigue el brillo y tono de la melodía. |
| Estrellas | Se calculan a partir de la densidad de notas por segundo. |
| Preview de selección | El fragmento de 30 s más intenso, alineado al compás. |

## Archivos generados por canción

```
mods/DivaManager_pv9500_Titulo/
├── config.toml
├── diva_manager.json            datos para regenerar
└── rom/
    ├── mod_pv_db.txt            entrada de la canción (claves ordenadas)
    ├── script/pv_9500_<dificultad>.dsc
    ├── sound/song/pv_9500.ogg   Vorbis a 44100 Hz
    └── movie/pv_9500.usm        H.264 o VP9 en contenedor CriWare
```

Los charts son DSC formato Future Tone (`script_format=0x15122517`).

## Limitaciones

- No genera sprites de portada, fondo, logo ni miniatura. La canción aparece sin jacket en el menú.
- No genera letras.
- El video H.264 no se reproduce en Linux ni en Steam Deck. Para esos casos elige VP9, que es más lento de convertir.
- Si el PV ID choca con un mod que no está instalado, habrá conflicto. El gestor solo evita los IDs de los mods presentes.

## Pruebas y herramientas de desarrollo

| Ruta | Para qué |
|---|---|
| `tests\test_charts.py` | Comprueba tempo, alineación del pulso, notas DSC y orden del `pv_db` con canciones sintéticas a 97, 128 y 174 BPM. |
| `tests\test_pipeline.py` | Importa una canción completa en una carpeta de juego falsa, sin tocar el juego real. Si hay FFmpeg, prueba también el `.mp4` y el `.usm`. |
| `tests\test_download.py` | Flujo URL → descarga → importación, con la descarga simulada (no usa la red). |
| `tests\test_gui.py` | Ventana principal, vista previa e importación en lote sobre un juego falso. |
| `loader\tests\build_test.bat` | Pruebas del motor de hooks y del lector TOML de DivaLoader. |
| `tests	est_video.py` | Conversión `.usm`: framerate correcto en la cabecera, 720p y duración exacta. |
| `dev\sync_report.py` | Tempo, ajuste constante y deriva de las canciones importadas. |
| `dev\chart_report.py` | Estadísticas de notas por dificultad de las canciones importadas, sin escribir nada. |
| `dev\gui_demo.py` y `dev\capture_window.ps1` | Abren la interfaz con datos de ejemplo y capturan una ventana para revisar el diseño. |
| `tests\test_video.py` | Conversión `.usm`: framerate correcto en la cabecera, 720p y duración exacta. |
| `dev\sync_report.py` | Tempo, ajuste constante y deriva de las canciones importadas. |
| `dev\chart_report.py` | Estadísticas de notas por dificultad de las canciones importadas, sin escribir nada. |
| `dev\gui_demo.py` y `dev\capture_window.ps1` | Abren la interfaz con datos de ejemplo y capturan una ventana para revisar el diseño. |
| `dev\check_env.py` | Revisa paquetes Python, FFmpeg, yt-dlp, DivaLoader compilado e instalado, y mods. |
| `dev\sigcheck.py` | Tras una actualización del juego, verifica que las firmas de DivaLoader siguen en su sitio en `DivaMegaMix.exe`. |
| `dev\trygame.ps1` | Instala el loader recién compilado, abre el juego y muestra `DivaLoader.log`. Con `-Skip` desactiva componentes para aislar un fallo. |
| `dev\cpk.py` | Lista y extrae archivos de los `.cpk` del juego. |
