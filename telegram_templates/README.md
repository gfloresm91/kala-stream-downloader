# Telegram templates

Cada archivo `.txt` en esta carpeta controla el texto de una notificación de Telegram.

Los placeholders disponibles dependen de cada template. Se escriben entre llaves, por ejemplo:

```text
Canal: {channel}
Archivo: {processed_file}
```

Si usas un placeholder que no existe para ese evento, el script lo deja tal cual en el mensaje. Por ejemplo, `{foo}` se enviaría como `{foo}`.

Si necesitas escribir llaves literales en un mensaje, escápalas duplicándolas: `{{` para `{` y `}}` para `}`.

## Templates disponibles

| Template | Cuándo se envía | Placeholders disponibles |
| --- | --- | --- |
| `startup.txt` | Cuando inicia el downloader. | `{channel}`, `{root_path}` |
| `live.txt` | Cuando detecta que el canal está en vivo. | `{channel}`, `{stream_title}`, `{game_name}`, `{quality}` |
| `recording_started.txt` | Cuando empieza la grabación con `streamlink`. | `{channel}`, `{quality}`, `{recorded_file}`, `{recorded_file_name}` |
| `recording_missing_file.txt` | Cuando termina la grabación pero no existe el archivo esperado. | `{channel}`, `{recorded_file}`, `{recorded_file_name}` |
| `streamlink_error.txt` | Cuando `streamlink` termina con error, pero dejó un archivo grabado. | `{channel}`, `{returncode}`, `{recorded_file}`, `{recorded_file_name}` |
| `recording_done.txt` | Cuando termina la grabación base. | `{channel}`, `{recorded_file}`, `{recorded_file_name}` |
| `stream_processing_error.txt` | Cuando falla el flujo que procesa un stream detectado. | `{channel}`, `{details}` |
| `background_processing_error.txt` | Cuando falla el procesamiento en background. | `{channel}`, `{recorded_file}`, `{recorded_file_name}`, `{details}` |
| `ffmpeg_error.txt` | Cuando `ffmpeg` no puede procesar el video. | `{channel}`, `{recorded_file}`, `{recorded_file_name}`, `{details}` |
| `processed.txt` | Cuando el video queda procesado correctamente. | `{channel}`, `{processed_file}`, `{processed_file_name}` |
| `chat_download_error.txt` | Cuando falla la descarga del chat. | `{vod_id}`, `{details}` |
| `chat_downloaded.txt` | Cuando el chat se descarga correctamente. | `{vod_id}`, `{chat_dir}`, `{chat_dir_name}` |
| `vod_download_error.txt` | Cuando falla la descarga del VOD. | `{vod_id}`, `{returncode}` |
| `vod_downloaded.txt` | Cuando el VOD se descarga correctamente. | `{vod_id}`, `{vod_target}`, `{vod_target_name}` |
| `compression_started.txt` | Cuando empieza la compresión con HandBrake. | `{processed_file}`, `{processed_file_name}`, `{compressed_target}`, `{compressed_target_name}` |
| `compression_done.txt` | Cuando termina correctamente la compresión. | `{compressed_target}`, `{compressed_target_name}` |
| `compression_error.txt` | Cuando la compresión termina con error. | `{returncode}`, `{log_file}`, `{log_file_name}` |
| `archive_moved.txt` | Cuando el archivo procesado se mueve al destino de archivo. | `{channel}`, `{processed_file}`, `{processed_file_name}`, `{archive_target}`, `{archive_target_name}`, `{archive_public_url}` |
| `archive_copied.txt` | Cuando el archivo procesado se copia al destino de archivo. | `{channel}`, `{processed_file}`, `{processed_file_name}`, `{archive_target}`, `{archive_target_name}`, `{archive_public_url}` |
| `post_stream_vod_error.txt` | Cuando no se puede obtener el VOD para tareas post-stream. | `{details}` |
| `post_stream_vod_not_found.txt` | Cuando no se encuentra VOD para tareas post-stream. | Sin placeholders |
| `post_stream_vod_missing_id.txt` | Cuando el VOD obtenido no trae ID. | Sin placeholders |
| `fatal_error.txt` | Cuando ocurre un error fatal del script. | `{channel}`, `{details}` |

## Placeholders usados actualmente

Esta tabla muestra los placeholders que están presentes hoy en los archivos `.txt` de esta carpeta. Puedes usar otros placeholders de la tabla anterior siempre que estén disponibles para ese mismo template.

| Template | Placeholders usados en el texto actual |
| --- | --- |
| `startup.txt` | `{channel}`, `{root_path}` |
| `live.txt` | `{channel}`, `{stream_title}`, `{game_name}`, `{quality}` |
| `recording_started.txt` | `{channel}`, `{quality}`, `{recorded_file}` |
| `recording_missing_file.txt` | `{channel}`, `{recorded_file}` |
| `streamlink_error.txt` | `{channel}`, `{returncode}`, `{recorded_file}` |
| `recording_done.txt` | `{channel}`, `{recorded_file}` |
| `stream_processing_error.txt` | `{channel}`, `{details}` |
| `background_processing_error.txt` | `{channel}`, `{recorded_file}`, `{details}` |
| `ffmpeg_error.txt` | `{channel}`, `{recorded_file}`, `{details}` |
| `processed.txt` | `{channel}`, `{processed_file}` |
| `chat_download_error.txt` | `{vod_id}`, `{details}` |
| `chat_downloaded.txt` | `{vod_id}`, `{chat_dir}` |
| `vod_download_error.txt` | `{vod_id}`, `{returncode}` |
| `vod_downloaded.txt` | `{vod_id}`, `{vod_target}` |
| `compression_started.txt` | `{processed_file_name}` |
| `compression_done.txt` | `{compressed_target_name}` |
| `compression_error.txt` | `{returncode}`, `{log_file}` |
| `archive_moved.txt` | `{archive_target}` |
| `archive_copied.txt` | `{archive_public_url}`, `{processed_file_name}` |
| `post_stream_vod_error.txt` | `{details}` |
| `post_stream_vod_not_found.txt` | Sin placeholders |
| `post_stream_vod_missing_id.txt` | Sin placeholders |
| `fatal_error.txt` | `{channel}`, `{details}` |

## Significado de placeholders

| Placeholder | Significado |
| --- | --- |
| `{archive_public_url}` | URL pública opcional configurada en `TWITCH_ARCHIVE_PUBLIC_URL`. |
| `{archive_target}` | Ruta completa del archivo copiado o movido al destino de archivo. |
| `{archive_target_name}` | Nombre del archivo copiado o movido al destino de archivo, sin ruta. |
| `{channel}` | Canal de Twitch configurado en `TWITCH_USERNAME`. |
| `{chat_dir}` | Ruta completa de la carpeta donde se guardó el chat. |
| `{chat_dir_name}` | Nombre de la carpeta donde se guardó el chat, sin ruta. |
| `{compressed_target}` | Ruta completa del archivo comprimido generado por HandBrake. |
| `{compressed_target_name}` | Nombre del archivo comprimido, sin ruta. |
| `{details}` | Detalle textual del error o condición reportada. |
| `{game_name}` | Categoría o juego informado por Twitch para el stream. |
| `{log_file}` | Ruta completa del log generado por HandBrake. |
| `{log_file_name}` | Nombre del archivo de log, sin ruta. |
| `{processed_file}` | Ruta completa del video procesado por `ffmpeg`. |
| `{processed_file_name}` | Nombre del video procesado, sin ruta. |
| `{quality}` | Calidad configurada para `streamlink`, por ejemplo `best` o `1080p60`. |
| `{recorded_file}` | Ruta completa del archivo grabado base en `recorded/`. |
| `{recorded_file_name}` | Nombre del archivo grabado base, sin ruta. |
| `{returncode}` | Código de salida de un comando externo. |
| `{root_path}` | Ruta base configurada en `TWITCH_ROOT_PATH`. |
| `{stream_title}` | Título del stream informado por Twitch, sanitizado para uso local. |
| `{vod_id}` | ID del VOD de Twitch. |
| `{vod_target}` | Ruta completa del VOD descargado. |
| `{vod_target_name}` | Nombre del VOD descargado, sin ruta. |

## Nota

Estos placeholders no están documentados en una web externa. Son propios de este script y salen de las llamadas internas a `notify_template(...)` en `kala-stream-download.py`.
