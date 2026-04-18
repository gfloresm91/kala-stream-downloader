#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import logging
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
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
    make_stream_folder: bool
    short_folder: bool
    hls_segments_live: int
    hls_segments_vod: int
    streamlink_debug: bool
    delete_recorded_mode: int  # 0=ask, 1=keep, 2=delete
    ffmpeg_binary: str
    streamlink_binary: str
    tcd_binary: str
    request_timeout: int
    log_level: str


class TwitchRecorder:
    TWITCH_TOKEN_URL = "https://id.twitch.tv/oauth2/token"
    TWITCH_USERS_URL = "https://api.twitch.tv/helix/users"
    TWITCH_STREAMS_URL = "https://api.twitch.tv/helix/streams"
    TWITCH_VIDEOS_URL = "https://api.twitch.tv/helix/videos"

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.session = requests.Session()
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
        logging.info("Refresh: %.1f segundos", self.cfg.refresh)

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

        try:
            ZoneInfo(self.cfg.timezone_name)
        except Exception as exc:
            raise ValueError(f"Timezone inválida: {self.cfg.timezone_name}") from exc

    def ensure_dependencies(self) -> None:
        required = [self.cfg.streamlink_binary, self.cfg.ffmpeg_binary]
        for binary in required:
            if shutil.which(binary) is None:
                raise RuntimeError(f"No se encontró '{binary}' en PATH")

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
        resp = self.session.post(
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

    def get_latest_vod(self) -> Optional[dict]:
        resp = self.session.get(
            self.TWITCH_VIDEOS_URL,
            headers=self.get_api_headers(),
            params={"user_id": self.channel_id, "type": "archive", "first": 1},
            timeout=self.cfg.request_timeout,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return data[0] if data else None

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

            logging.info("Volviendo a monitorear...")
            time.sleep(self.cfg.refresh)

    def handle_live_stream(self, live_info: dict) -> None:
        present_date = self.now_local().strftime("%Y%m%d")
        present_datetime = self.now_local().strftime("%Y%m%d_%Hh%Mm%Ss")

        stream_title = sanitize_name(live_info.get("title", "Untitled"))
        game_name = sanitize_name(live_info.get("game_name", "UnknownGame"))

        initial_name = sanitize_name(
            f"{present_datetime}_{stream_title}_{game_name}_{self.cfg.username}.mp4"
        )

        recorded_file = self.make_safe_unique_file(self.recorded_root / initial_name)

        self.run_streamlink_live(recorded_file)

        if not recorded_file.exists():
            logging.warning("La grabación terminó pero no existe el archivo: %s", recorded_file)
            return

        latest_vod = None
        try:
            latest_vod = self.get_latest_vod()
        except Exception as exc:
            logging.warning("No se pudo obtener el último VOD: %s", exc)

        processed_dir, final_name, vod_id = self.build_targets(
            live_info=live_info,
            latest_vod=latest_vod,
            fallback_title=stream_title,
            fallback_game=game_name,
            present_date=present_date,
            present_datetime=present_datetime,
        )

        processed_dir.mkdir(parents=True, exist_ok=True)

        new_recorded_file = self.make_safe_unique_file(self.recorded_root / final_name)
        if recorded_file != new_recorded_file:
            recorded_file.rename(new_recorded_file)
            recorded_file = new_recorded_file

        processed_file = self.make_safe_unique_file(processed_dir / final_name)

        if self.cfg.chat_download and vod_id:
            self.download_chat(vod_id, processed_dir, final_name)

        if self.cfg.download_vod and vod_id:
            self.download_vod(vod_id, final_name)

        logging.info("Reparando video con ffmpeg...")
        self.run_ffmpeg_fix(recorded_file, processed_file)
        logging.info("Video procesado: %s", processed_file)

    def build_targets(
        self,
        live_info: dict,
        latest_vod: Optional[dict],
        fallback_title: str,
        fallback_game: str,
        present_date: str,
        present_datetime: str,
    ) -> tuple[Path, str, Optional[str]]:
        vod_id = None
        game_name = sanitize_name(live_info.get("game_name", fallback_game))
        title = fallback_title
        date_prefix = present_date
        datetime_prefix = self.now_local().strftime("%Y%m%d_(%H-%M)")

        if latest_vod:
            vod_id = latest_vod.get("id")
            title = sanitize_name(latest_vod.get("title", fallback_title))
            created_at = latest_vod.get("created_at")
            if created_at:
                dt_utc = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                dt_local = dt_utc.astimezone(ZoneInfo(self.cfg.timezone_name))
                date_prefix = dt_local.strftime("%Y%m%d")
                datetime_prefix = dt_local.strftime("%Y%m%d_(%H-%M)")

        if vod_id:
            filename = sanitize_name(
                f"{datetime_prefix}_{vod_id}_{title}_{game_name}_{self.cfg.username}.mp4"
            )
        else:
            filename = sanitize_name(
                f"{present_datetime}_{title}_{game_name}_{self.cfg.username}.mp4"
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

        candidate = processed_dir / filename
        candidate = self.ensure_path_length(
            candidate,
            title,
            game_name,
            vod_id,
            date_prefix,
            present_datetime,
        )

        return candidate.parent, candidate.name, vod_id

    def run_streamlink_live(self, output_file: Path) -> None:
        cmd = [self.cfg.streamlink_binary]

        if self.cfg.streamlink_debug:
            cmd += ["--loglevel", "trace"]

        if self.cfg.oauth_private:
            cmd += [
                "--twitch-api-header=Authorization=OAuth " + self.cfg.oauth_private,
                "--twitch-disable-ads",
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
        subprocess.run(cmd, check=False)

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
            "--timezone",
            self.cfg.timezone_name,
            "-f",
            "irc,ssa,json",
            "-o",
            str(chat_dir),
        ]
        logging.info("Descargando chat del VOD %s...", vod_id)
        logging.debug("CMD: %s", " ".join(cmd))
        subprocess.run(cmd, check=False)

    def download_vod(self, vod_id: str, final_name: str) -> None:
        vod_target = self.make_safe_unique_file(self.recorded_root / f"VOD_{final_name}")

        cmd = [self.cfg.streamlink_binary]

        if self.cfg.streamlink_debug:
            cmd += ["--loglevel", "trace"]

        if self.cfg.oauth_private:
            cmd += [
                "--twitch-api-header=Authorization=OAuth " + self.cfg.oauth_private,
                "--twitch-disable-ads",
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
        subprocess.run(cmd, check=False)

    def now_local(self) -> datetime:
        return datetime.now(ZoneInfo(self.cfg.timezone_name))

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
                    f"{present_datetime}_{current_title}_{game_name}_{self.cfg.username}.mp4"
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


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    return int(value) if value is not None else default


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

    parser.add_argument("--chat-download", action="store_true", default=env_bool("TWITCH_CHAT_DOWNLOAD", False))
    parser.add_argument("--download-vod", action="store_true", default=env_bool("TWITCH_DOWNLOAD_VOD", False))
    parser.add_argument("--make-stream-folder", action="store_true", default=env_bool("TWITCH_MAKE_STREAM_FOLDER", False))
    parser.add_argument("--short-folder", action="store_true", default=env_bool("TWITCH_SHORT_FOLDER", False))
    parser.add_argument("--streamlink-debug", action="store_true", default=env_bool("TWITCH_STREAMLINK_DEBUG", False))

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
    parser.add_argument("--streamlink-binary", default=os.getenv("STREAMLINK_BINARY", "streamlink"))
    parser.add_argument("--tcd-binary", default=os.getenv("TCD_BINARY", "tcd"))

    parser.add_argument("--request-timeout", type=int, default=env_int("TWITCH_REQUEST_TIMEOUT", 15))
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
        make_stream_folder=args.make_stream_folder,
        short_folder=args.short_folder,
        hls_segments_live=args.hls_segments_live,
        hls_segments_vod=args.hls_segments_vod,
        streamlink_debug=args.streamlink_debug,
        delete_recorded_mode=args.delete_recorded_mode,
        ffmpeg_binary=args.ffmpeg_binary,
        streamlink_binary=args.streamlink_binary,
        tcd_binary=args.tcd_binary,
        request_timeout=args.request_timeout,
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
        return 1


if __name__ == "__main__":
    sys.exit(main())