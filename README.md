# Kala Stream Downloader

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-Stable-success)

Script en Python para monitorear un canal de Twitch, grabar el directo con `streamlink` y procesar el archivo final con `ffmpeg`.

## Qué hace

- Detecta cuando un canal entra en vivo.
- Graba el stream en `recorded/<canal>/`.
- Repara/copia el archivo final con `ffmpeg` hacia `processed/<canal>/`.
- Puede descargar el chat del VOD con `tcd` cuando Twitch lo publica.
- Puede descargar el VOD completo al terminar el stream.
- Puede comprimir el archivo procesado con `HandBrakeCLI` usando un preset JSON.
- Opcionalmente copia o mueve el archivo procesado a una segunda carpeta.
- Las tareas de chat/VOD y compresión pueden correr en background para no bloquear el monitoreo.
- Evita sobrescribir archivos existentes generando nombres únicos como `archivo (1).mp4`.

## Requisitos

- Python 3.10 o superior
- `streamlink`
- `ffmpeg`
- `HandBrakeCLI` opcional, solo si vas a usar `TWITCH_COMPRESS_PROCESSED_ENABLED=true`
- `tcd` opcional, solo si vas a usar `TWITCH_CHAT_DOWNLOAD=true`

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

También necesitas tener `streamlink` y `ffmpeg` disponibles en tu `PATH`.

Una vez activado `.venv`, usa `python` y `pip` del entorno virtual para evitar diferencias entre versiones instaladas en el sistema.

## Configuración

Crea un archivo `.env` en la raíz del proyecto. Un ejemplo mínimo:

```env
TWITCH_USERNAME=tu_canal

TWITCH_CLIENT_ID=tu_client_id
TWITCH_CLIENT_SECRET=tu_client_secret
TWITCH_OAUTH_PRIVATE=

TWITCH_QUALITY=best
TWITCH_ROOT_PATH=/ruta/a/tus/grabaciones
TWITCH_REFRESH=5
TWITCH_TIMEZONE=America/Santiago

TWITCH_CHAT_DOWNLOAD=false
TWITCH_DOWNLOAD_VOD=false

TWITCH_COMPRESS_PROCESSED_ENABLED=false
TWITCH_COMPRESS_PROCESSED_PATH=
TWITCH_COMPRESS_PROCESSED_PRESET_FILE=
TWITCH_COMPRESS_PROCESSED_PRESET_NAME=Fast 1080p60
TWITCH_COMPRESS_PROCESSED_SUFFIX=_compressed

TWITCH_ARCHIVE_PROCESSED_ENABLED=false
TWITCH_ARCHIVE_PROCESSED_PATH=
TWITCH_ARCHIVE_PROCESSED_MODE=copy
TWITCH_MAKE_STREAM_FOLDER=false
TWITCH_SHORT_FOLDER=false
TWITCH_STREAMLINK_DEBUG=false

TWITCH_HLS_SEGMENTS_LIVE=3
TWITCH_HLS_SEGMENTS_VOD=10
TWITCH_DELETE_RECORDED_MODE=1
TWITCH_REQUEST_TIMEOUT=15

FFMPEG_BINARY=ffmpeg
HANDBRAKE_BINARY=HandBrakeCLI
STREAMLINK_BINARY=streamlink
TCD_BINARY=tcd

LOG_LEVEL=INFO
```

Si quieres, puedes partir desde [.env_example](/Users/gabriel/Developer/kala-apps/kala-stream-downloader/.env_example:1).

## Uso

Con el `.env` listo:

```bash
.venv/bin/python kala-stream-download.py
```

También puedes pasar opciones por CLI, por ejemplo:

```bash
.venv/bin/python kala-stream-download.py --username tu_canal --root-path /tmp/twitch-recordings
```

## Estructura de salida

```text
<root>/
├── recorded/
│   └── <canal>/
│       └── archivos temporales y VODs descargados
└── processed/
    └── <canal>/
        └── videos finales y chats descargados
```

Si `TWITCH_MAKE_STREAM_FOLDER=true`, cada stream se guarda dentro de su propia carpeta en `processed/<canal>/`.

El archivo final procesado se genera con este formato:

```text
YYYYMMDD_<titulo_stream>_HHhMMmSSs.mp4
```

## Variables importantes

`TWITCH_USERNAME`

Canal que el script va a monitorear.

`TWITCH_ROOT_PATH`

Ruta base donde se crearán las carpetas `recorded/` y `processed/`.

`TWITCH_REFRESH`

Cada cuántos segundos consulta si el canal está en vivo.

`TWITCH_CHAT_DOWNLOAD`

Si está en `true`, descarga el chat del VOD con `tcd`.

La descarga del chat depende de que Twitch ya haya generado el VOD. Al terminar el directo, el script reintenta durante un rato hasta obtener el `vod_id`.
Esos reintentos ahora corren en background, para que el script vuelva a monitorear apenas termina el procesamiento principal.

`TWITCH_DOWNLOAD_VOD`

Si está en `true`, además intenta descargar el VOD completo cuando termina el directo.

`TWITCH_COMPRESS_PROCESSED_ENABLED`

Si está en `true`, lanza una compresión en background con `HandBrakeCLI` al terminar el procesamiento con `ffmpeg`.

`TWITCH_COMPRESS_PROCESSED_PATH`

Carpeta donde debe quedar el archivo comprimido.

`TWITCH_COMPRESS_PROCESSED_PRESET_FILE`

Ruta al archivo JSON del preset de HandBrake.

`TWITCH_COMPRESS_PROCESSED_PRESET_NAME`

Nombre del preset dentro del archivo JSON.

`TWITCH_COMPRESS_PROCESSED_SUFFIX`

Sufijo que se agrega al nombre del archivo comprimido. Por defecto: `_compressed`.

`TWITCH_ARCHIVE_PROCESSED_ENABLED`

Si está en `true`, copia o mueve el archivo final procesado a una segunda carpeta.

`TWITCH_ARCHIVE_PROCESSED_PATH`

Ruta destino adicional para el archivo procesado. Puede estar fuera de `processed/`, por ejemplo en otra carpeta local, un disco externo o una carpeta sincronizada con OneDrive.

`TWITCH_ARCHIVE_PROCESSED_MODE`

Modo de traslado del archivo procesado:

- `copy`: recomendado, deja el archivo original en `processed/`
- `move`: mueve el archivo fuera de `processed/`

`TWITCH_DELETE_RECORDED_MODE`

Controla qué pasa con archivos previos dentro de `recorded/<canal>/` al iniciar:

- `0`: pregunta antes de borrar
- `1`: no borra nada
- `2`: borra automáticamente

## Cómo evita sobreescrituras

Cuando el script va a guardar una grabación, un VOD o un archivo procesado, revisa si el nombre ya existe. Si existe, crea uno nuevo con sufijos como:

- `video.mp4`
- `video (1).mp4`
- `video (2).mp4`

Eso aplica también a carpetas de chat descargado.

La misma lógica se usa si activas el archivado adicional del archivo procesado.

Si activas la compresión, el archivo comprimido se genera con este patrón:

- `YYYYMMDD_<titulo_stream>_HHhMMmSSs_compressed.mp4`

## Notas

- `TWITCH_OAUTH_PRIVATE` es opcional.
- El script usa la API de Twitch, así que necesitas `TWITCH_CLIENT_ID` y `TWITCH_CLIENT_SECRET`.
- `streamlink` y `ffmpeg` se validan al iniciar.
- Si `TWITCH_COMPRESS_PROCESSED_ENABLED=true`, también se valida que `HandBrakeCLI` exista y que el preset JSON sea válido.
- Si `TWITCH_CHAT_DOWNLOAD=true`, también se valida que `tcd` exista en el sistema.
- La descarga de chat/VOD corre en background para no bloquear la detección de un nuevo directo.
- La compresión corre en background para no bloquear la detección de un nuevo directo.
- No se puede combinar compresión en background con `TWITCH_ARCHIVE_PROCESSED_MODE=move`, porque movería el archivo antes de que HandBrake termine de leerlo.
