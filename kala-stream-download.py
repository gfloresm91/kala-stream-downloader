#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests
from dotenv import load_dotenv
from zoneinfo import ZoneInfo


INVALID_FS_CHARS = '<>:"/\\|?*'
MAX_PATH_LEN = 240


@dataclass
class Config:
    client_id: str
    client_secret: str
    oauth_private: str
    username: str
    quality: str
    root_path: Path
    refresh: float
    timezone_name: str
    chat_download: bool
    download_vod: bool
    compress_processed_enabled: bool
    compress_processed_path: Path | None
    compress_processed_preset_file: Path | None
    compress_processed_preset_name: str
    compress_processed_suffix: str
    archive_processed_enabled: bool
    archive_processed_path: Path | None
    archive_processed_mode: str
    make_stream_folder: bool
    short_folder: bool
    hls_segments_live: int
    hls_segments_vod: int
    streamlink_debug: bool
    delete_recorded_mode: int  # 0=ask, 1=keep, 2=delete
    ffmpeg_binary: str
    handbrake_binary: str
    streamlink_binary: str
    tcd_binary: str
    request_timeout: int
    telegram_notifications_enabled: bool
    telegram_bot_token: str
    telegram_chat_id: str
    telegram_message_thread_id: int | None
    telegram_notify_startup: bool
    telegram_notify_live: bool
    telegram_notify_recording_started: bool
    telegram_notify_recording_done: bool
    telegram_notify_processed: bool
    telegram_notify_post_tasks: bool
    telegram_notify_errors: bool
    log_level: str


class TelegramNotifier:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    @property
    def enabled(self) -> bool:
        return (
            self.cfg.telegram_notifications_enabled
            and bool(self.cfg.telegram_bot_token)
            and bool(self.cfg.telegram_chat_id)
        )

    def send(self, message: str) -> None:
        if not self.enabled:
            return

        worker = threading.Thread(
            target=self.send_sync,
            args=(message,),
            daemon=True,
            name="telegram-notifier",
        )
        worker.start()

    def send_sync(self, message: str) -> None:
        if not self.enabled:
            return

        url = f"https://api.telegram.org/bot{self.cfg.telegram_bot_token}/sendMessage"
        payload = {
            "chat_id": self.cfg.telegram_chat_id,
            "text": message,
            "disable_web_page_preview": True,
        }
        if self.cfg.telegram_message_thread_id is not None:
            payload["message_thread_id"] = self.cfg.telegram_message_thread_id

        try:
            resp = requests.post(url, data=payload, timeout=self.cfg.request_timeout)
            resp.raise_for_status()
        except Exception as exc:
            logging.warning("No se pudo enviar notificación Telegram: %s", exc)


class TwitchRecorder:
    TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
    TWITCH_USERS_URL = "https://api.twitch.tv/helix/users"
    TWITCH_STREAMS_URL = "https://api.twitch.tv/helix/streams"
    TWITCH_VIDEOS_URL = "https://api.twitch.tv/helix/videos"

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.session = requests.Session()
        self.notifier = TelegramNotifier(cfg)
        self.oauth_token: Optional[str] = None
        self.channel_id: Optional[str] = None

        self.recorded_root = self.cfg.root_path / "recorded" / self.cfg.username
        self.processed_root = self.cfg.root_path / "processed" / self.cfg.username

    def run(self) -> None:
        self.validate_config()
        self.ensure_dependencies()
        self.ensure_directories()
        self.handle_old_recordings_policy()

        self.oauth_token = self.get_app_oauth_token()
        self.channel_id = self.get_channel_id(self.cfg.username)

        logging.info("Auto Stream Recording Twitch (KALAPLEX TOOLS)")
        logging.info("Canal: %s", self.cfg.username)
        logging.info("Root path: %s", self.cfg.root_path)
        logging.info("Timezone: %s", self.cfg.timezone_name)
        logging.info("Chat download: %s", self.cfg.chat_download)
        logging.info("VOD download: %s", self.cfg.download_vod)
        logging.info("Compress processed: %s", self.cfg.compress_processed_enabled)
        logging.info("Archive processed: %s", self.cfg.archive_processed_enabled)
        logging.info("Refresh: %.1f segundos", self.cfg.refresh)

        if self.cfg.telegram_notify_startup:
            self.notify(
                "Kala Stream Downloader iniciado.\n"
                f"Canal: {self.cfg.username}\n"
                f"Root: {self.cfg.root_path}"
            )

        self.loopcheck()

    def validate_config(self) -> None:
        if not self.cfg.client_id:
            raise ValueError("Falta client_id")
        if not self.cfg.client_secret:
            raise ValueError("Falta client_secret")
        if not self.cfg.username:
            raise ValueError("Falta username")
        if self.cfg.refresh < 1:
            logging.warning("Refresh < 1 no es válido. Se ajusta a 1.")
            self.cfg.refresh = 1
        if not (1 <= self.cfg.hls_segments_live <= 10):
            raise ValueError("hls_segments_live debe estar entre 1 y 10")
        if not (1 <= self.cfg.hls_segments_vod <= 10):
            raise ValueError("hls_segments_vod debe estar entre 1 y 10")
        if self.cfg.compress_processed_enabled and not self.cfg.compress_processed_path:
            raise ValueError(
                "Si compress_processed_enabled=true debes indicar compress_processed_path"
            )
        if self.cfg.compress_processed_enabled and not self.cfg.compress_processed_preset_file:
            raise ValueError(
                "Si compress_processed_enabled=true debes indicar compress_processed_preset_file"
            )
        if self.cfg.compress_processed_enabled and not self.cfg.compress_processed_preset_name:
            raise ValueError(
                "Si compress_processed_enabled=true debes indicar compress_processed_preset_name"
            )
        if (
            self.cfg.compress_processed_enabled
            and self.cfg.archive_processed_enabled
            and self.cfg.archive_processed_mode == "move"
        ):
            raise ValueError(
                "No se puede usar archive_processed_mode=move junto con la compresion en background"
            )
        if self.cfg.archive_processed_mode not in {"copy", "move"}:
            raise ValueError("archive_processed_mode debe ser 'copy' o 'move'")
        if self.cfg.archive_processed_enabled and not self.cfg.archive_processed_path:
            raise ValueError(
                "Si archive_processed_enabled=true debes indicar archive_processed_path"
            )
        if self.cfg.telegram_notifications_enabled:
            if not self.cfg.telegram_bot_token:
                raise ValueError(
                    "Si telegram_notifications_enabled=true debes indicar telegram_bot_token"
                )
            if not self.cfg.telegram_chat_id:
                raise ValueError(
                    "Si telegram_notifications_enabled=true debes indicar telegram_chat_id"
                )

        try:
            ZoneInfo(self.cfg.timezone_name)
        except Exception as exc:
            raise ValueError(f"Timezone inválida: {self.cfg.timezone_name}") from exc

    def notify(self, message: str, *, errors_only: bool = False) -> None:
        if errors_only and not self.cfg.telegram_notify_errors:
            return
        self.notifier.send(message)

    def ensure_dependencies(self) -> None:
        required = [self.cfg.streamlink_binary, self.cfg.ffmpeg_binary]
        for binary in required:
            if shutil.which(binary) is None:
                raise RuntimeError(f"No se encontró '{binary}' en PATH")

        if self.cfg.compress_processed_enabled:
            if shutil.which(self.cfg.handbrake_binary) is None:
                raise RuntimeError(f"No se encontró '{self.cfg.handbrake_binary}' en PATH")
            if (
                not self.cfg.compress_processed_preset_file
                or not self.cfg.compress_processed_preset_file.is_file()
            ):
                raise RuntimeError(
                    f"No se encontró preset de HandBrake: {self.cfg.compress_processed_preset_file}"
                )

        if self.cfg.chat_download and shutil.which(self.cfg.tcd_binary) is None:
            raise RuntimeError(
                f"Se activó chat_download pero no se encontró '{self.cfg.tcd_binary}' en PATH"
            )

    def ensure_directories(self) -> None:
        self.recorded_root.mkdir(parents=True, exist_ok=True)
        self.processed_root.mkdir(parents=True, exist_ok=True)

    def handle_old_recordings_policy(self) -> None:
        if self.cfg.delete_recorded_mode == 0:
            answer = input(
                "¿Quieres borrar archivos previos de recorded? [y/N]: "
            ).strip().lower()
            should_delete = answer == "y"
        elif self.cfg.delete_recorded_mode == 2:
            should_delete = True
        else:
            should_delete = False

        if should_delete:
            for file in self.recorded_root.glob("*"):
                if file.is_file():
                    logging.info("Borrando archivo previo: %s", file)
                    file.unlink(missing_ok=True)

    def get_app_oauth_token(self) -> str:
        return self.get_app_oauth_token_for_session(self.session)

    def get_app_oauth_token_for_session(self, session: requests.Session) -> str:
        resp = session.post(
            self.TWITCH_TOKEN_URL,
            params={
                "client_id": self.cfg.client_id,
                "client_secret": self.cfg.client_secret,
                "grant_type": "client_credentials",
            },
            timeout=self.cfg.request_timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        token = data.get("access_token")
        if not token:
            raise RuntimeError("No se pudo obtener access_token")
        return token

    def get_api_headers(self) -> dict[str, str]:
        if not self.oauth_token:
            raise RuntimeError("OAuth token no inicializado")
        return {
            "Authorization": f"Bearer {self.oauth_token}",
            "Client-ID": self.cfg.client_id,
        }

    def get_channel_id(self, username: str) -> str:
        resp = self.session.get(
            self.TWITCH_USERS_URL,
            headers=self.get_api_headers(),
            params={"login": username},
            timeout=self.cfg.request_timeout,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            raise RuntimeError(f"Usuario de Twitch no encontrado: {username}")
        return data[0]["id"]

    def get_live_stream_info(self) -> Optional[dict]:
        resp = self.session.get(
            self.TWITCH_STREAMS_URL,
            headers=self.get_api_headers(),
            params={"user_id": self.channel_id},
            timeout=self.cfg.request_timeout,
        )

        if resp.status_code == 401:
            logging.warning("Token vencido o inválido. Renovando token.")
            self.oauth_token = self.get_app_oauth_token()
            resp = self.session.get(
                self.TWITCH_STREAMS_URL,
                headers=self.get_api_headers(),
                params={"user_id": self.channel_id},
                timeout=self.cfg.request_timeout,
            )

        resp.raise_for_status()
        data = resp.json().get("data", [])
        return data[0] if data else None

    def get_recent_vods_for_session(
        self,
        session: requests.Session,
        oauth_token: Optional[str],
        channel_id: Optional[str],
        first: int = 5,
    ) -> list[dict]:
        if not oauth_token:
            raise RuntimeError("OAuth token no inicializado")
        if not channel_id:
            raise RuntimeError("Channel id no inicializado")

        resp = session.get(
            self.TWITCH_VIDEOS_URL,
            headers={
                "Authorization": f"Bearer {oauth_token}",
                "Client-ID": self.cfg.client_id,
            },
            params={"user_id": channel_id, "type": "archive", "first": first},
            timeout=self.cfg.request_timeout,
        )
        resp.raise_for_status()
        return resp.json().get("data", [])

    def get_matching_vod_with_retry_for_session(
        self,
        session: requests.Session,
        oauth_token: Optional[str],
        channel_id: Optional[str],
        stream_started_at: Optional[datetime],
        stream_finished_at: datetime,
        attempts: int = 6,
        delay_seconds: float = 20.0,
    ) -> Optional[dict]:
        last_error: Optional[Exception] = None

        for attempt in range(1, attempts + 1):
            try:
                vods = self.get_recent_vods_for_session(
                    session,
                    oauth_token,
                    channel_id,
                    first=5,
                )
                if not stream_started_at:
                    if vods:
                        return vods[0]
                else:
                    match = self.find_matching_vod(
                        vods,
                        stream_started_at,
                        stream_finished_at,
                    )
                    if match:
                        return match

                logging.info(
                    "Aun no hay VOD compatible disponible en Twitch. Intento %s/%s.",
                    attempt,
                    attempts,
                )
            except Exception as exc:
                last_error = exc
                logging.warning(
                    "No se pudo obtener VOD compatible (intento %s/%s): %s",
                    attempt,
                    attempts,
                    exc,
                )

            if attempt < attempts:
                time.sleep(delay_seconds)

        if last_error:
            raise RuntimeError("No se pudo obtener VOD compatible tras varios intentos") from last_error

        return None

    def find_matching_vod(
        self,
        vods: list[dict],
        stream_started_at: datetime,
        stream_finished_at: datetime,
    ) -> Optional[dict]:
        window_start = stream_started_at - timedelta(minutes=15)
        window_end = stream_finished_at + timedelta(minutes=30)

        for vod in vods:
            created_at = parse_twitch_datetime(vod.get("created_at"))
            if not created_at:
                continue
            if window_start <= created_at <= window_end:
                return vod

        return None

    def loopcheck(self) -> None:
        while True:
            try:
                live_info = self.get_live_stream_info()
            except requests.RequestException as exc:
                logging.error("Error consultando Twitch API: %s", exc)
                time.sleep(self.cfg.refresh)
                continue
            except Exception as exc:
                logging.exception("Error inesperado consultando Twitch: %s", exc)
                time.sleep(self.cfg.refresh)
                continue

            if not live_info:
                logging.info(
                    "[%s] %s está offline. Reintentando en %.1fs",
                    self.now_local().strftime("%H:%M:%S"),
                    self.cfg.username,
                    self.cfg.refresh,
                )
                time.sleep(self.cfg.refresh)
                continue

            logging.info(
                "[%s] %s está EN VIVO - %s",
                self.now_local().strftime("%H:%M:%S"),
                self.cfg.username,
                live_info.get("title", ""),
            )

            try:
                self.handle_live_stream(live_info)
            except Exception as exc:
                logging.exception("Error procesando stream: %s", exc)
                self.notify(
                    "Error procesando stream.\n"
                    f"Canal: {self.cfg.username}\n"
                    f"Detalle: {exc}",
                    errors_only=True,
                )

            logging.info("Volviendo a monitorear...")
            time.sleep(self.cfg.refresh)

    def handle_live_stream(self, live_info: dict) -> None:
        present_date = self.now_local().strftime("%Y%m%d")
        present_datetime = self.now_local().strftime("%Y%m%d_%Hh%Mm%Ss")
        stream_started_at = parse_twitch_datetime(live_info.get("started_at"))

        stream_title = sanitize_name(live_info.get("title", "Untitled"))
        game_name = sanitize_name(live_info.get("game_name", "UnknownGame"))

        if self.cfg.telegram_notify_live:
            self.notify(
                "Stream detectado en vivo.\n"
                f"Canal: {self.cfg.username}\n"
                f"Titulo: {stream_title}\n"
                f"Juego: {game_name}\n"
                f"Calidad: {self.cfg.quality}"
            )

        initial_name = sanitize_name(
            f"{present_datetime}_{stream_title}_{game_name}_{self.cfg.username}.mp4"
        )

        recorded_file = self.make_safe_unique_file(self.recorded_root / initial_name)

        if self.cfg.telegram_notify_recording_started:
            self.notify(
                "Grabación iniciada.\n"
                f"Canal: {self.cfg.username}\n"
                f"Calidad: {self.cfg.quality}\n"
                f"Archivo: {recorded_file}"
            )

        streamlink_returncode = self.run_streamlink_live(recorded_file)
        stream_finished_at = datetime.now(timezone.utc)

        if not recorded_file.exists():
            logging.warning("La grabación terminó pero no existe el archivo: %s", recorded_file)
            self.notify(
                "La grabación terminó, pero no se encontró el archivo generado.\n"
                f"Canal: {self.cfg.username}\n"
                f"Archivo esperado: {recorded_file}",
                errors_only=True,
            )
            return

        if streamlink_returncode != 0:
            logging.warning(
                "streamlink terminó con código %s. Se intentará procesar el archivo existente.",
                streamlink_returncode,
            )
            self.notify(
                "streamlink terminó con error, pero existe un archivo grabado.\n"
                f"Canal: {self.cfg.username}\n"
                f"Codigo: {streamlink_returncode}\n"
                f"Archivo: {recorded_file}",
                errors_only=True,
            )

        if self.cfg.telegram_notify_recording_done:
            self.notify(
                "Grabación terminada.\n"
                f"Canal: {self.cfg.username}\n"
                f"Archivo: {recorded_file}"
            )

        self.start_recording_processing(
            recorded_file=recorded_file,
            live_info=live_info,
            stream_title=stream_title,
            game_name=game_name,
            present_date=present_date,
            present_datetime=present_datetime,
            stream_started_at=stream_started_at,
            stream_finished_at=stream_finished_at,
        )

    def start_recording_processing(
        self,
        recorded_file: Path,
        live_info: dict,
        stream_title: str,
        game_name: str,
        present_date: str,
        present_datetime: str,
        stream_started_at: Optional[datetime],
        stream_finished_at: datetime,
    ) -> None:
        worker = threading.Thread(
            target=self.process_recording,
            kwargs={
                "recorded_file": recorded_file,
                "live_info": live_info,
                "stream_title": stream_title,
                "game_name": game_name,
                "present_date": present_date,
                "present_datetime": present_datetime,
                "stream_started_at": stream_started_at,
                "stream_finished_at": stream_finished_at,
            },
            daemon=True,
            name=f"process-recording-{self.cfg.username}",
        )
        worker.start()
        logging.info("Procesamiento de grabación lanzado en background.")

    def process_recording(
        self,
        recorded_file: Path,
        live_info: dict,
        stream_title: str,
        game_name: str,
        present_date: str,
        present_datetime: str,
        stream_started_at: Optional[datetime],
        stream_finished_at: datetime,
    ) -> None:
        try:
            self._process_recording(
                recorded_file=recorded_file,
                live_info=live_info,
                stream_title=stream_title,
                game_name=game_name,
                present_date=present_date,
                present_datetime=present_datetime,
                stream_started_at=stream_started_at,
                stream_finished_at=stream_finished_at,
            )
        except Exception as exc:
            logging.exception("Error en procesamiento background: %s", exc)
            self.notify(
                "Error en procesamiento background.\n"
                f"Canal: {self.cfg.username}\n"
                f"Archivo: {recorded_file}\n"
                f"Detalle: {exc}",
                errors_only=True,
            )

    def _process_recording(
        self,
        recorded_file: Path,
        live_info: dict,
        stream_title: str,
        game_name: str,
        present_date: str,
        present_datetime: str,
        stream_started_at: Optional[datetime],
        stream_finished_at: datetime,
    ) -> None:
        processed_dir, recorded_name, processed_name = self.build_targets(
            live_info=live_info,
            fallback_title=stream_title,
            fallback_game=game_name,
            present_date=present_date,
            present_datetime=present_datetime,
        )

        processed_dir.mkdir(parents=True, exist_ok=True)

        new_recorded_file = self.make_safe_unique_file(self.recorded_root / recorded_name)
        if recorded_file != new_recorded_file:
            recorded_file.rename(new_recorded_file)
            recorded_file = new_recorded_file

        processed_file = self.make_safe_unique_file(processed_dir / processed_name)

        logging.info("Reparando video con ffmpeg...")
        try:
            self.run_ffmpeg_fix(recorded_file, processed_file)
        except Exception as exc:
            logging.exception("No se pudo procesar video con ffmpeg: %s", exc)
            self.notify(
                "No se pudo procesar video con ffmpeg.\n"
                f"Canal: {self.cfg.username}\n"
                f"Archivo: {recorded_file}\n"
                f"Detalle: {exc}",
                errors_only=True,
            )
            return

        logging.info("Video procesado: %s", processed_file)
        if self.cfg.telegram_notify_processed:
            self.notify(
                "Video procesado correctamente.\n"
                f"Canal: {self.cfg.username}\n"
                f"Archivo: {processed_file}"
            )
        self.compress_processed_file(processed_file)
        self.archive_processed_file(processed_file)
        self.start_post_stream_tasks(
            processed_dir,
            processed_name,
            stream_started_at,
            stream_finished_at,
        )

    def build_targets(
        self,
        live_info: dict,
        fallback_title: str,
        fallback_game: str,
        present_date: str,
        present_datetime: str,
    ) -> tuple[Path, str, str]:
        game_name = sanitize_name(live_info.get("game_name", fallback_game))
        title = fallback_title
        date_prefix = present_date
        time_suffix = present_datetime.split("_", 1)[1]

        recorded_name = sanitize_name(
            f"{present_datetime}_{title}_{game_name}_{self.cfg.username}.mp4"
        )

        processed_name = sanitize_name(
            f"{present_date}_{fallback_title}_{time_suffix}.mp4"
        )

        if self.cfg.short_folder:
            folder_name = date_prefix
        else:
            folder_name = sanitize_name(
                f"{date_prefix}_{title}_{game_name}_{self.cfg.username}"
            )

        processed_dir = (
            self.processed_root / folder_name
            if self.cfg.make_stream_folder
            else self.processed_root
        )

        candidate = processed_dir / processed_name
        candidate = self.ensure_path_length(
            candidate,
            fallback_title,
            game_name,
            None,
            present_date,
            present_datetime,
        )

        return candidate.parent, recorded_name, candidate.name

    def run_streamlink_live(self, output_file: Path) -> int:
        cmd = [self.cfg.streamlink_binary]

        if self.cfg.streamlink_debug:
            cmd += ["--loglevel", "trace"]

        if self.cfg.oauth_private:
            cmd += [
                "--twitch-api-header=Authorization=OAuth " + self.cfg.oauth_private,
                "--http-cookie",
                f"auth-token={self.cfg.oauth_private}",
            ]

        cmd += [
            "--stream-segment-threads",
            str(self.cfg.hls_segments_live),
            "--hls-live-restart",
            "--retry-streams",
            str(int(self.cfg.refresh)),
            "https://twitch.tv/" + self.cfg.username,
            self.cfg.quality,
            "-o",
            str(output_file),
        ]

        logging.info("Iniciando streamlink live...")
        logging.debug("CMD: %s", " ".join(cmd))
        result = subprocess.run(cmd, check=False)
        return result.returncode

    def run_ffmpeg_fix(self, input_file: Path, output_file: Path) -> None:
        cmd = [
            self.cfg.ffmpeg_binary,
            "-y",
            "-i",
            str(input_file),
            "-analyzeduration",
            "2147483647",
            "-probesize",
            "2147483647",
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-start_at_zero",
            "-copyts",
            str(output_file),
        ]
        logging.debug("CMD: %s", " ".join(cmd))
        subprocess.run(cmd, check=True)

    def download_chat(self, vod_id: str, processed_dir: Path, final_name: str) -> None:
        chat_base = processed_dir / f"{Path(final_name).stem}_chat"
        chat_dir = self.make_unique_dir(chat_base)
        chat_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.cfg.tcd_binary,
            "-v",
            vod_id,
            "--client-id",
            self.cfg.client_id,
            "--client-secret",
            self.cfg.client_secret,
            "--timezone",
            self.cfg.timezone_name,
            "-f",
            "irc,ssa,json",
            "-o",
            str(chat_dir),
        ]
        logging.info("Descargando chat del VOD %s...", vod_id)
        logging.debug("CMD: %s", " ".join(cmd))
        result = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            stdout = (result.stdout or "").strip()
            details = stderr or stdout or f"codigo de salida {result.returncode}"
            logging.warning("No se pudo descargar el chat del VOD %s: %s", vod_id, details)
            self.notify(
                "No se pudo descargar el chat.\n"
                f"VOD: {vod_id}\n"
                f"Detalle: {details}",
                errors_only=True,
            )
            return

        logging.info("Chat descargado en: %s", chat_dir)
        if self.cfg.telegram_notify_post_tasks:
            self.notify(
                "Chat descargado correctamente.\n"
                f"VOD: {vod_id}\n"
                f"Carpeta: {chat_dir}"
            )

    def download_vod(self, vod_id: str, final_name: str) -> None:
        vod_target = self.make_safe_unique_file(self.recorded_root / f"VOD_{final_name}")

        cmd = [self.cfg.streamlink_binary]

        if self.cfg.streamlink_debug:
            cmd += ["--loglevel", "trace"]

        if self.cfg.oauth_private:
            cmd += [
                "--twitch-api-header=Authorization=OAuth " + self.cfg.oauth_private,
                "--http-cookie",
                f"auth-token={self.cfg.oauth_private}",
            ]

        cmd += [
            "--stream-segment-threads",
            str(self.cfg.hls_segments_vod),
            "https://twitch.tv/videos/" + vod_id,
            self.cfg.quality,
            "-o",
            str(vod_target),
        ]

        logging.info("Descargando VOD %s...", vod_id)
        logging.debug("CMD: %s", " ".join(cmd))
        result = subprocess.run(cmd, check=False)
        if result.returncode != 0:
            logging.warning("No se pudo descargar el VOD %s. Codigo: %s", vod_id, result.returncode)
            self.notify(
                "No se pudo descargar el VOD.\n"
                f"VOD: {vod_id}\n"
                f"Codigo: {result.returncode}",
                errors_only=True,
            )
            return

        if self.cfg.telegram_notify_post_tasks:
            self.notify(
                "VOD descargado correctamente.\n"
                f"VOD: {vod_id}\n"
                f"Archivo: {vod_target}"
            )

    def now_local(self) -> datetime:
        return datetime.now(ZoneInfo(self.cfg.timezone_name))

    def compress_processed_file(self, processed_file: Path) -> None:
        if (
            not self.cfg.compress_processed_enabled
            or not self.cfg.compress_processed_path
            or not self.cfg.compress_processed_preset_file
        ):
            return

        compress_root = self.cfg.compress_processed_path.expanduser().resolve()
        compress_root.mkdir(parents=True, exist_ok=True)

        compressed_target = self.make_safe_unique_file(
            compress_root / f"{processed_file.stem}{self.cfg.compress_processed_suffix}{processed_file.suffix}"
        )
        log_file = compressed_target.with_suffix(".handbrake.log")

        cmd = [
            self.cfg.handbrake_binary,
            "--preset-import-file",
            str(self.cfg.compress_processed_preset_file),
            "--preset",
            self.cfg.compress_processed_preset_name,
            "-i",
            str(processed_file),
            "-o",
            str(compressed_target),
        ]

        logging.info("Iniciando compresion en background: %s", compressed_target)
        logging.debug("CMD: %s", " ".join(cmd))

        with log_file.open("ab") as log_handle:
            process = subprocess.Popen(
                cmd,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )

        should_watch_compression = (
            self.cfg.telegram_notify_post_tasks or self.cfg.telegram_notify_errors
        )

        if self.cfg.telegram_notify_post_tasks:
            self.notify(
                "Compresión iniciada en background.\n"
                f"Origen: {processed_file}\n"
                f"Destino: {compressed_target}"
            )

        if should_watch_compression:
            worker = threading.Thread(
                target=self.watch_compression_process,
                args=(process, compressed_target, log_file),
                daemon=True,
                name=f"handbrake-{self.cfg.username}",
            )
            worker.start()

    def watch_compression_process(
        self,
        process: subprocess.Popen,
        compressed_target: Path,
        log_file: Path,
    ) -> None:
        returncode = process.wait()
        if returncode == 0:
            if self.cfg.telegram_notify_post_tasks:
                self.notify(
                    "Compresión terminada correctamente.\n"
                    f"Archivo: {compressed_target}"
                )
            return

        logging.warning("HandBrake terminó con código %s. Log: %s", returncode, log_file)
        self.notify(
            "La compresión terminó con error.\n"
            f"Codigo: {returncode}\n"
            f"Log: {log_file}",
            errors_only=True,
        )

    def archive_processed_file(self, processed_file: Path) -> None:
        if not self.cfg.archive_processed_enabled or not self.cfg.archive_processed_path:
            return

        archive_root = self.cfg.archive_processed_path.expanduser().resolve()
        archive_root.mkdir(parents=True, exist_ok=True)

        archive_target = self.make_safe_unique_file(archive_root / processed_file.name)

        if self.cfg.archive_processed_mode == "move":
            shutil.move(str(processed_file), str(archive_target))
            logging.info("Archivo procesado movido a: %s", archive_target)
            if self.cfg.telegram_notify_post_tasks:
                self.notify(
                    "Archivo procesado movido.\n"
                    f"Destino: {archive_target}"
                )
            return

        shutil.copy2(processed_file, archive_target)
        logging.info("Archivo procesado copiado a: %s", archive_target)
        if self.cfg.telegram_notify_post_tasks:
            self.notify(
                "Archivo procesado copiado.\n"
                f"Destino: {archive_target}"
            )

    def start_post_stream_tasks(
        self,
        processed_dir: Path,
        processed_name: str,
        stream_started_at: Optional[datetime],
        stream_finished_at: datetime,
    ) -> None:
        if not (self.cfg.chat_download or self.cfg.download_vod):
            return

        worker = threading.Thread(
            target=self.run_post_stream_tasks,
            args=(processed_dir, processed_name, stream_started_at, stream_finished_at),
            daemon=True,
            name=f"post-stream-{self.cfg.username}",
        )
        worker.start()
        logging.info("Tareas de VOD/chat lanzadas en background.")

    def run_post_stream_tasks(
        self,
        processed_dir: Path,
        processed_name: str,
        stream_started_at: Optional[datetime],
        stream_finished_at: datetime,
    ) -> None:
        session = requests.Session()

        try:
            oauth_token = self.get_app_oauth_token_for_session(session)
            latest_vod = self.get_matching_vod_with_retry_for_session(
                session,
                oauth_token,
                self.channel_id,
                stream_started_at,
                stream_finished_at,
            )
        except Exception as exc:
            logging.warning("No se pudo obtener el ultimo VOD: %s", exc)
            self.notify(
                "No se pudo obtener el último VOD para tareas post-stream.\n"
                f"Detalle: {exc}",
                errors_only=True,
            )
            return

        if not latest_vod:
            logging.warning("No se encontro VOD para tareas post-stream.")
            if self.cfg.telegram_notify_post_tasks:
                self.notify("No se encontró VOD para tareas post-stream.")
            return

        vod_id = latest_vod.get("id")
        if not vod_id:
            logging.warning("El VOD obtenido no trae id. Se omiten tareas post-stream.")
            self.notify(
                "El VOD obtenido no trae id. Se omiten tareas post-stream.",
                errors_only=True,
            )
            return

        if self.cfg.chat_download:
            self.download_chat(vod_id, processed_dir, processed_name)

        if self.cfg.download_vod:
            self.download_vod(vod_id, processed_name)

    def make_unique_file(self, path: Path) -> Path:
        if not path.exists():
            return path

        counter = 1
        while True:
            candidate = path.with_name(f"{path.stem} ({counter}){path.suffix}")
            if not candidate.exists():
                return candidate
            counter += 1

    def make_unique_dir(self, path: Path) -> Path:
        if not path.exists():
            return path

        counter = 1
        while True:
            candidate = path.parent / f"{path.name} ({counter})"
            if not candidate.exists():
                return candidate
            counter += 1

    def make_safe_unique_file(self, path: Path) -> Path:
        safe_name = sanitize_name(path.name)
        candidate = path.with_name(safe_name)
        candidate = self.ensure_simple_path_length(candidate)
        return self.make_unique_file(candidate)

    def ensure_simple_path_length(self, path: Path) -> Path:
        if len(str(path)) < MAX_PATH_LEN:
            return path

        stem = path.stem
        suffix = path.suffix
        overflow = len(str(path)) - MAX_PATH_LEN
        trimmed = stem[:-overflow] if overflow < len(stem) else stem[:40]
        trimmed = trimmed.rstrip(" ._-")
        return path.with_name(f"{trimmed}{suffix}")

    def ensure_path_length(
        self,
        candidate: Path,
        title: str,
        game_name: str,
        vod_id: Optional[str],
        date_prefix: str,
        present_datetime: str,
    ) -> Path:
        if len(str(candidate)) < MAX_PATH_LEN:
            return candidate

        current_title = title
        time_suffix = present_datetime.split("_", 1)[1]

        for _ in range(12):
            if len(current_title) <= 12:
                break

            current_title = current_title[:-10].rstrip(" ._-")

            if vod_id:
                filename = sanitize_name(
                    f"{date_prefix}_({self.now_local().strftime('%H-%M')})_{vod_id}_{current_title}_{game_name}_{self.cfg.username}.mp4"
                )
            else:
                filename = sanitize_name(
                    f"{date_prefix}_{current_title}_{time_suffix}.mp4"
                )

            if self.cfg.short_folder:
                folder_name = date_prefix
            else:
                folder_name = sanitize_name(
                    f"{date_prefix}_{current_title}_{game_name}_{self.cfg.username}"
                )

            processed_dir = (
                self.processed_root / folder_name
                if self.cfg.make_stream_folder
                else self.processed_root
            )

            new_candidate = processed_dir / filename
            if len(str(new_candidate)) < MAX_PATH_LEN:
                logging.warning("Ruta demasiado larga. Se recortó el título.")
                return new_candidate

        logging.warning("No se pudo optimizar bien la ruta. Aplicando recorte simple.")
        return self.ensure_simple_path_length(candidate)


def sanitize_name(value: str) -> str:
    value = value.replace("\n", " ").replace("\r", " ").strip()

    cleaned = []
    for ch in value:
        if ch in INVALID_FS_CHARS:
            continue
        cleaned.append(ch)

    result = "".join(cleaned)
    result = " ".join(result.split())
    result = result.rstrip(" .")

    return result or "untitled"


def parse_twitch_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


def env_optional_int(name: str) -> int | None:
    value = os.getenv(name)
    if value is None or not value.strip():
        return None
    return int(value)


def env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    return float(value) if value is not None else default


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Graba directos de Twitch automáticamente."
    )

    parser.add_argument(
        "--username",
        default=os.getenv("TWITCH_USERNAME"),
        required=os.getenv("TWITCH_USERNAME") is None,
        help="Nombre del canal de Twitch",
    )
    parser.add_argument("--quality", default=os.getenv("TWITCH_QUALITY", "best"))
    parser.add_argument(
        "--root-path",
        default=os.getenv("TWITCH_ROOT_PATH", str(Path.cwd() / "twitch_recordings")),
        help="Ruta base para recorded/ y processed/",
    )

    parser.add_argument("--client-id", default=os.getenv("TWITCH_CLIENT_ID", ""))
    parser.add_argument("--client-secret", default=os.getenv("TWITCH_CLIENT_SECRET", ""))
    parser.add_argument("--oauth-private", default=os.getenv("TWITCH_OAUTH_PRIVATE", ""))

    parser.add_argument("--refresh", type=float, default=env_float("TWITCH_REFRESH", 5.0))
    parser.add_argument("--timezone", default=os.getenv("TWITCH_TIMEZONE", "America/Santiago"))

    parser.add_argument(
        "--chat-download",
        action=argparse.BooleanOptionalAction,
        default=env_bool("TWITCH_CHAT_DOWNLOAD", False),
    )
    parser.add_argument(
        "--download-vod",
        action=argparse.BooleanOptionalAction,
        default=env_bool("TWITCH_DOWNLOAD_VOD", False),
    )
    parser.add_argument(
        "--compress-processed-enabled",
        action=argparse.BooleanOptionalAction,
        default=env_bool("TWITCH_COMPRESS_PROCESSED_ENABLED", False),
    )
    parser.add_argument(
        "--compress-processed-path",
        default=os.getenv("TWITCH_COMPRESS_PROCESSED_PATH", ""),
    )
    parser.add_argument(
        "--compress-processed-preset-file",
        default=os.getenv("TWITCH_COMPRESS_PROCESSED_PRESET_FILE", ""),
    )
    parser.add_argument(
        "--compress-processed-preset-name",
        default=os.getenv("TWITCH_COMPRESS_PROCESSED_PRESET_NAME", ""),
    )
    parser.add_argument(
        "--compress-processed-suffix",
        default=os.getenv("TWITCH_COMPRESS_PROCESSED_SUFFIX", "_compressed"),
    )
    parser.add_argument(
        "--archive-processed-enabled",
        action=argparse.BooleanOptionalAction,
        default=env_bool("TWITCH_ARCHIVE_PROCESSED_ENABLED", False),
    )
    parser.add_argument(
        "--archive-processed-path",
        default=os.getenv("TWITCH_ARCHIVE_PROCESSED_PATH", ""),
    )
    parser.add_argument(
        "--archive-processed-mode",
        default=os.getenv("TWITCH_ARCHIVE_PROCESSED_MODE", "copy").strip().lower(),
        choices=["copy", "move"],
    )
    parser.add_argument(
        "--make-stream-folder",
        action=argparse.BooleanOptionalAction,
        default=env_bool("TWITCH_MAKE_STREAM_FOLDER", False),
    )
    parser.add_argument(
        "--short-folder",
        action=argparse.BooleanOptionalAction,
        default=env_bool("TWITCH_SHORT_FOLDER", False),
    )
    parser.add_argument(
        "--streamlink-debug",
        action=argparse.BooleanOptionalAction,
        default=env_bool("TWITCH_STREAMLINK_DEBUG", False),
    )

    parser.add_argument("--hls-segments-live", type=int, default=env_int("TWITCH_HLS_SEGMENTS_LIVE", 3))
    parser.add_argument("--hls-segments-vod", type=int, default=env_int("TWITCH_HLS_SEGMENTS_VOD", 10))

    parser.add_argument(
        "--delete-recorded-mode",
        type=int,
        choices=[0, 1, 2],
        default=env_int("TWITCH_DELETE_RECORDED_MODE", 1),
        help="0=ask, 1=keep, 2=delete",
    )

    parser.add_argument("--ffmpeg-binary", default=os.getenv("FFMPEG_BINARY", "ffmpeg"))
    parser.add_argument("--handbrake-binary", default=os.getenv("HANDBRAKE_BINARY", "HandBrakeCLI"))
    parser.add_argument("--streamlink-binary", default=os.getenv("STREAMLINK_BINARY", "streamlink"))
    parser.add_argument("--tcd-binary", default=os.getenv("TCD_BINARY", "tcd"))

    parser.add_argument("--request-timeout", type=int, default=env_int("TWITCH_REQUEST_TIMEOUT", 15))
    parser.add_argument(
        "--telegram-notifications-enabled",
        action=argparse.BooleanOptionalAction,
        default=env_bool("TELEGRAM_NOTIFICATIONS_ENABLED", False),
    )
    parser.add_argument("--telegram-bot-token", default=os.getenv("TELEGRAM_BOT_TOKEN", ""))
    parser.add_argument("--telegram-chat-id", default=os.getenv("TELEGRAM_CHAT_ID", ""))
    parser.add_argument(
        "--telegram-message-thread-id",
        type=int,
        default=env_optional_int("TELEGRAM_MESSAGE_THREAD_ID"),
    )
    parser.add_argument(
        "--telegram-notify-startup",
        action=argparse.BooleanOptionalAction,
        default=env_bool("TELEGRAM_NOTIFY_STARTUP", True),
    )
    parser.add_argument(
        "--telegram-notify-live",
        action=argparse.BooleanOptionalAction,
        default=env_bool("TELEGRAM_NOTIFY_LIVE", True),
    )
    parser.add_argument(
        "--telegram-notify-recording-done",
        action=argparse.BooleanOptionalAction,
        default=env_bool("TELEGRAM_NOTIFY_RECORDING_DONE", True),
    )
    parser.add_argument(
        "--telegram-notify-recording-started",
        action=argparse.BooleanOptionalAction,
        default=env_bool("TELEGRAM_NOTIFY_RECORDING_STARTED", True),
    )
    parser.add_argument(
        "--telegram-notify-processed",
        action=argparse.BooleanOptionalAction,
        default=env_bool("TELEGRAM_NOTIFY_PROCESSED", True),
    )
    parser.add_argument(
        "--telegram-notify-post-tasks",
        action=argparse.BooleanOptionalAction,
        default=env_bool("TELEGRAM_NOTIFY_POST_TASKS", True),
    )
    parser.add_argument(
        "--telegram-notify-errors",
        action=argparse.BooleanOptionalAction,
        default=env_bool("TELEGRAM_NOTIFY_ERRORS", True),
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )

    return parser


def build_config(args: argparse.Namespace) -> Config:
    return Config(
        client_id=args.client_id,
        client_secret=args.client_secret,
        oauth_private=args.oauth_private,
        username=args.username,
        quality=args.quality,
        root_path=Path(args.root_path).expanduser().resolve(),
        refresh=args.refresh,
        timezone_name=args.timezone,
        chat_download=args.chat_download,
        download_vod=args.download_vod,
        compress_processed_enabled=args.compress_processed_enabled,
        compress_processed_path=(
            Path(args.compress_processed_path).expanduser().resolve()
            if args.compress_processed_path
            else None
        ),
        compress_processed_preset_file=(
            Path(args.compress_processed_preset_file).expanduser().resolve()
            if args.compress_processed_preset_file
            else None
        ),
        compress_processed_preset_name=args.compress_processed_preset_name,
        compress_processed_suffix=args.compress_processed_suffix,
        archive_processed_enabled=args.archive_processed_enabled,
        archive_processed_path=(
            Path(args.archive_processed_path).expanduser().resolve()
            if args.archive_processed_path
            else None
        ),
        archive_processed_mode=args.archive_processed_mode,
        make_stream_folder=args.make_stream_folder,
        short_folder=args.short_folder,
        hls_segments_live=args.hls_segments_live,
        hls_segments_vod=args.hls_segments_vod,
        streamlink_debug=args.streamlink_debug,
        delete_recorded_mode=args.delete_recorded_mode,
        ffmpeg_binary=args.ffmpeg_binary,
        handbrake_binary=args.handbrake_binary,
        streamlink_binary=args.streamlink_binary,
        tcd_binary=args.tcd_binary,
        request_timeout=args.request_timeout,
        telegram_notifications_enabled=args.telegram_notifications_enabled,
        telegram_bot_token=args.telegram_bot_token,
        telegram_chat_id=args.telegram_chat_id,
        telegram_message_thread_id=args.telegram_message_thread_id,
        telegram_notify_startup=args.telegram_notify_startup,
        telegram_notify_live=args.telegram_notify_live,
        telegram_notify_recording_started=args.telegram_notify_recording_started,
        telegram_notify_recording_done=args.telegram_notify_recording_done,
        telegram_notify_processed=args.telegram_notify_processed,
        telegram_notify_post_tasks=args.telegram_notify_post_tasks,
        telegram_notify_errors=args.telegram_notify_errors,
        log_level=args.log_level,
    )


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main() -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.log_level)
    cfg: Config | None = None

    try:
        cfg = build_config(args)
        recorder = TwitchRecorder(cfg)
        recorder.run()
        return 0
    except KeyboardInterrupt:
        logging.info("Interrumpido por el usuario.")
        return 130
    except Exception as exc:
        logging.exception("Error fatal: %s", exc)
        if cfg and cfg.telegram_notify_errors:
            TelegramNotifier(cfg).send_sync(
                "Error fatal en Kala Stream Downloader.\n"
                f"Canal: {cfg.username}\n"
                f"Detalle: {exc}"
            )
        return 1


if __name__ == "__main__":
    sys.exit(main())
