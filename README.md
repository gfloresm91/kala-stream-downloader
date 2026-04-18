# Kala Stream Downloader

Script en Python para monitorear un canal de Twitch, grabar el directo con `streamlink` y procesar el archivo final con `ffmpeg`.

## Qué hace

- Detecta cuando un canal entra en vivo.
- Graba el stream en `recorded/<canal>/`.
- Repara/copia el archivo final con `ffmpeg` hacia `processed/<canal>/`.
- Puede descargar el chat del VOD con `tcd`.
- Puede descargar el VOD completo al terminar el stream.
- Evita sobrescribir archivos existentes generando nombres únicos como `archivo (1).mp4`.

## Requisitos

- Python 3.10 o superior
- `streamlink`
- `ffmpeg`
- `tcd` opcional, solo si vas a usar `TWITCH_CHAT_DOWNLOAD=true`

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

También necesitas tener `streamlink` y `ffmpeg` disponibles en tu `PATH`.

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
TWITCH_MAKE_STREAM_FOLDER=false
TWITCH_SHORT_FOLDER=false
TWITCH_STREAMLINK_DEBUG=false

TWITCH_HLS_SEGMENTS_LIVE=3
TWITCH_HLS_SEGMENTS_VOD=10
TWITCH_DELETE_RECORDED_MODE=1
TWITCH_REQUEST_TIMEOUT=15

FFMPEG_BINARY=ffmpeg
STREAMLINK_BINARY=streamlink
TCD_BINARY=tcd

LOG_LEVEL=INFO
```

Si quieres, puedes partir desde [.env_example](/Users/gabriel/Developer/kala-download-stream-script/.env_example:1).

## Uso

Con el `.env` listo:

```bash
python3 kala-stream-download.py
```

También puedes pasar opciones por CLI, por ejemplo:

```bash
python3 kala-stream-download.py --username tu_canal --root-path /tmp/twitch-recordings
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

`TWITCH_DOWNLOAD_VOD`

Si está en `true`, además intenta descargar el VOD completo cuando termina el directo.

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

## Notas

- `TWITCH_OAUTH_PRIVATE` es opcional.
- El script usa la API de Twitch, así que necesitas `TWITCH_CLIENT_ID` y `TWITCH_CLIENT_SECRET`.
- `streamlink` y `ffmpeg` se validan al iniciar.
- Si `TWITCH_CHAT_DOWNLOAD=true`, también se valida que `tcd` exista en el sistema.
