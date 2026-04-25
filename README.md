# Kala Stream Downloader

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-Stable-success)

Script en Python para monitorear un canal de Twitch, grabar el directo con `streamlink` y procesar el archivo final con `ffmpeg`.

## Qué hace

- Detecta cuando un canal entra en vivo.
- Graba el stream en `recorded/<canal>/`.
- Repara/copia el archivo final con `ffmpeg` hacia `processed/<canal>/` en background.
- Puede descargar el chat del VOD con `tcd` cuando Twitch lo publica.
- Puede descargar el VOD completo al terminar el stream.
- Puede comprimir el archivo procesado con `HandBrakeCLI` usando un preset JSON.
- Opcionalmente copia o mueve el archivo procesado a una segunda carpeta.
- Puede enviar notificaciones a Telegram, incluyendo topics de supergrupos.
- Las tareas de procesamiento, chat/VOD, archivado y compresión corren en background para no bloquear el monitoreo.
- Evita sobrescribir archivos existentes generando nombres únicos como `archivo (1).mp4`.

## Requisitos

- Python 3.10 o superior
- `streamlink`
- `ffmpeg`
- `HandBrakeCLI` opcional, solo si vas a usar `TWITCH_COMPRESS_PROCESSED_ENABLED=true`
- `tcd` opcional, solo si vas a usar `TWITCH_CHAT_DOWNLOAD=true`
- Bot de Telegram opcional, solo si vas a usar `TELEGRAM_NOTIFICATIONS_ENABLED=true`

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

También necesitas tener `streamlink` y `ffmpeg` disponibles en tu `PATH`.

Una vez activado `.venv`, usa `python` y `pip` del entorno virtual para evitar diferencias entre versiones instaladas en el sistema.

En macOS, por ejemplo, puedes instalar las dependencias externas con Homebrew:

```bash
brew install streamlink ffmpeg
```

Si vas a comprimir videos, instala también `HandBrakeCLI`. Si vas a descargar chats, instala `tcd` y déjalo disponible en tu `PATH`.

## Credenciales de Twitch

El script usa la API de Twitch para saber si el canal está en vivo, obtener el ID del canal y buscar el VOD publicado al terminar el directo.

Para completar `TWITCH_CLIENT_ID` y `TWITCH_CLIENT_SECRET`:

1. Entra a <https://dev.twitch.tv/console/apps>.
2. Crea una aplicación.
3. Copia el Client ID.
4. Genera y copia el Client Secret.

`TWITCH_OAUTH_PRIVATE` es opcional. Sirve para pasar un token privado a `streamlink` cuando necesitas que la descarga use una sesión autenticada, por ejemplo para contenido con restricciones de acceso.

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

TELEGRAM_NOTIFICATIONS_ENABLED=false
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
TELEGRAM_MESSAGE_THREAD_ID=
TELEGRAM_NOTIFY_STARTUP=true
TELEGRAM_NOTIFY_LIVE=true
TELEGRAM_NOTIFY_RECORDING_STARTED=true
TELEGRAM_NOTIFY_RECORDING_DONE=true
TELEGRAM_NOTIFY_PROCESSED=true
TELEGRAM_NOTIFY_POST_TASKS=true
TELEGRAM_NOTIFY_ERRORS=true

FFMPEG_BINARY=ffmpeg
HANDBRAKE_BINARY=HandBrakeCLI
STREAMLINK_BINARY=streamlink
TCD_BINARY=tcd

LOG_LEVEL=INFO
```

Si quieres, puedes partir desde [.env_example](.env_example).

## Uso

Con el `.env` listo:

```bash
.venv/bin/python kala-stream-download.py
```

También puedes pasar opciones por CLI, por ejemplo:

```bash
.venv/bin/python kala-stream-download.py --username tu_canal --root-path /tmp/twitch-recordings
```

Puedes ver todas las opciones disponibles con:

```bash
.venv/bin/python kala-stream-download.py --help
```

Las opciones booleanas también se pueden desactivar por CLI usando `--no-*`, por ejemplo:

```bash
.venv/bin/python kala-stream-download.py --no-telegram-notify-live --no-download-vod
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

Si además `TWITCH_SHORT_FOLDER=true`, esa carpeta usa solo la fecha como nombre:

```text
processed/<canal>/YYYYMMDD/
```

Si `TWITCH_SHORT_FOLDER=false`, la carpeta incluye fecha, título, juego y canal.

El archivo final procesado se genera con este formato:

```text
YYYYMMDD_<titulo_stream>_HHhMMmSSs.mp4
```

La grabación base dentro de `recorded/<canal>/` usa este formato:

```text
YYYYMMDD_HHhMMmSSs_<titulo_stream>_<juego>_<canal>.mp4
```

## Variables importantes

`TWITCH_USERNAME`

Canal que el script va a monitorear.

`TWITCH_ROOT_PATH`

Ruta base donde se crearán las carpetas `recorded/` y `processed/`.

Si no se define, usa `twitch_recordings/` dentro del directorio desde donde ejecutes el script.

`TWITCH_QUALITY`

Calidad que se pasa a `streamlink`, por ejemplo `best`, `1080p60`, `720p`, etc.

`TWITCH_REFRESH`

Cada cuántos segundos consulta si el canal está en vivo.

`TWITCH_TIMEZONE`

Zona horaria usada para nombres de archivos, carpetas y descarga de chat.

`TWITCH_OAUTH_PRIVATE`

Token privado opcional para que `streamlink` use una sesión autenticada al grabar streams o descargar VODs.

`TWITCH_CHAT_DOWNLOAD`

Si está en `true`, descarga el chat del VOD con `tcd`.

La descarga del chat depende de que Twitch ya haya generado el VOD. Al terminar el directo, el script reintenta durante un rato hasta obtener el `vod_id`.
Esos reintentos corren en background para que el script pueda volver a monitorear sin esperar las tareas posteriores.

El chat se descarga en formatos `irc`, `ssa` y `json`.

Para evitar confundir VODs cuando hay reconexiones rápidas, el script busca un VOD compatible con la ventana de tiempo del stream recién grabado.

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

`TWITCH_MAKE_STREAM_FOLDER`

Si está en `true`, crea una carpeta por stream dentro de `processed/<canal>/`.

`TWITCH_SHORT_FOLDER`

Si está en `true`, la carpeta por stream usa solo la fecha `YYYYMMDD`. Solo tiene efecto cuando `TWITCH_MAKE_STREAM_FOLDER=true`.

`TWITCH_STREAMLINK_DEBUG`

Si está en `true`, ejecuta `streamlink` con logs detallados (`--loglevel trace`).

`TWITCH_HLS_SEGMENTS_LIVE`

Cantidad de segmentos HLS paralelos que usa `streamlink` al grabar un directo. Debe estar entre `1` y `10`.

`TWITCH_HLS_SEGMENTS_VOD`

Cantidad de segmentos HLS paralelos que usa `streamlink` al descargar un VOD. Debe estar entre `1` y `10`.

`TWITCH_DELETE_RECORDED_MODE`

Controla qué pasa con archivos previos dentro de `recorded/<canal>/` al iniciar:

- `0`: pregunta antes de borrar
- `1`: no borra nada
- `2`: borra automáticamente

`TWITCH_REQUEST_TIMEOUT`

Timeout en segundos para las llamadas HTTP a la API de Twitch.

`TELEGRAM_NOTIFICATIONS_ENABLED`

Si está en `true`, activa las notificaciones por Telegram.

`TELEGRAM_BOT_TOKEN`

Token del bot de Telegram. Lo entrega BotFather.

`TELEGRAM_CHAT_ID`

ID del chat, grupo o canal donde el bot debe enviar los mensajes.

`TELEGRAM_MESSAGE_THREAD_ID`

ID opcional del topic/thread dentro de un supergrupo de Telegram. Déjalo vacío si no usas topics.

Para enviar a un topic de Telegram necesitas `TELEGRAM_CHAT_ID` con el ID del grupo o supergrupo y `TELEGRAM_MESSAGE_THREAD_ID` con el ID del topic. Si envías a un chat, canal o grupo sin topics, deja `TELEGRAM_MESSAGE_THREAD_ID=` vacío.

`TELEGRAM_NOTIFY_STARTUP`

Notifica cuando el script inicia y queda monitoreando.

`TELEGRAM_NOTIFY_LIVE`

Notifica cuando detecta que el canal está en vivo.

`TELEGRAM_NOTIFY_RECORDING_STARTED`

Notifica cuando el script lanza `streamlink` para empezar a grabar. Incluye canal, calidad y archivo destino.

`TELEGRAM_NOTIFY_RECORDING_DONE`

Notifica cuando termina la grabación base de `streamlink`.

`TELEGRAM_NOTIFY_PROCESSED`

Notifica cuando `ffmpeg` termina de generar el video procesado.

`TELEGRAM_NOTIFY_POST_TASKS`

Notifica tareas secundarias completadas, como chat descargado, VOD descargado, compresión iniciada/terminada y archivado.

`TELEGRAM_NOTIFY_ERRORS`

Notifica errores fatales o fallos relevantes, aunque el script pueda seguir monitoreando. Algunos errores de chat, VOD o compresión se notifican con este flag aunque `TELEGRAM_NOTIFY_POST_TASKS=false`.

`STREAMLINK_BINARY`, `FFMPEG_BINARY`, `HANDBRAKE_BINARY`, `TCD_BINARY`

Permiten indicar el nombre o ruta del ejecutable que usará el script para cada herramienta externa.

`LOG_LEVEL`

Nivel de detalle de los logs. Valores disponibles: `DEBUG`, `INFO`, `WARNING` y `ERROR`.

- `INFO`: recomendado para uso normal.
- `DEBUG`: muestra comandos ejecutados y más detalle para diagnosticar problemas.
- `WARNING` o `ERROR`: reduce el ruido cuando solo quieres ver problemas.

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
- Si `TWITCH_COMPRESS_PROCESSED_ENABLED=true`, también se valida que `HandBrakeCLI` exista y que el archivo de preset JSON exista.
- Si `TWITCH_CHAT_DOWNLOAD=true`, también se valida que `tcd` exista en el sistema.
- El procesamiento con `ffmpeg` corre en background para no bloquear la detección de un nuevo directo.
- La descarga de chat/VOD corre en background para no bloquear la detección de un nuevo directo.
- El archivado adicional corre dentro del flujo de procesamiento en background.
- La compresión corre en background para no bloquear la detección de un nuevo directo.
- Si el proceso se detiene mientras hay tareas en background, la grabación original queda en `recorded/`, pero el procesamiento, archivado, compresión o descarga de chat/VOD podrían quedar incompletos.
- Si `streamlink` termina con error pero deja un archivo grabado, el script avisa el error e intenta procesar el archivo existente.
- No se puede combinar compresión en background con `TWITCH_ARCHIVE_PROCESSED_MODE=move`, porque movería el archivo antes de que HandBrake termine de leerlo.
- Las notificaciones de Telegram se envían en background y no bloquean la detección ni el inicio de grabación. Si Telegram no responde, el flujo principal continúa.
- Solo el aviso de error fatal intenta enviarse antes de que el proceso termine.
