#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Elimina archivos antiguos de recorded/<canal> y processed/<canal>."
    )
    parser.add_argument(
        "--root-path",
        default=os.getenv("TWITCH_ROOT_PATH", str(Path.cwd() / "twitch_recordings")),
        help="Ruta base donde existen recorded/ y processed/.",
    )
    parser.add_argument(
        "--username",
        default=os.getenv("TWITCH_USERNAME"),
        required=os.getenv("TWITCH_USERNAME") is None,
        help="Canal de Twitch usado para ubicar las carpetas del canal.",
    )
    parser.add_argument(
        "--min-age-hours",
        type=float,
        default=float(
            os.getenv(
                "CLEANUP_STREAM_FILES_MIN_AGE_HOURS",
                os.getenv("CLEANUP_RECORDED_MIN_AGE_HOURS", "24"),
            )
        ),
        help="Antigüedad mínima del archivo antes de borrarlo.",
    )
    parser.add_argument(
        "--targets",
        nargs="+",
        choices=["recorded", "processed"],
        default=os.getenv("CLEANUP_STREAM_FILES_TARGETS", "recorded,processed").replace(",", " ").split(),
        help="Carpetas bajo TWITCH_ROOT_PATH que se limpiarán.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Muestra qué se borraría sin eliminar archivos.",
    )
    parser.add_argument(
        "--log-level",
        default=os.getenv("LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    return parser


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cleanup_directory(target_dir: Path, min_age_hours: float, dry_run: bool) -> int:
    if min_age_hours < 0:
        raise ValueError("--min-age-hours no puede ser negativo")

    if not target_dir.exists():
        logging.info("No existe la carpeta objetivo: %s", target_dir)
        return 0

    if not target_dir.is_dir():
        raise RuntimeError(f"No es una carpeta: {target_dir}")

    cutoff = time.time() - (min_age_hours * 3600)
    deleted = 0
    skipped = 0

    for path in sorted(target_dir.rglob("*")):
        if not path.is_file():
            skipped += 1
            logging.debug("Omitiendo porque no es archivo: %s", path)
            continue

        stat = path.stat()
        if stat.st_mtime > cutoff:
            skipped += 1
            logging.debug("Omitiendo archivo reciente: %s", path)
            continue

        if dry_run:
            logging.info("Se borraría: %s", path)
        else:
            logging.info("Borrando: %s", path)
            path.unlink()
        deleted += 1

    remove_empty_dirs(target_dir, dry_run)

    action = "candidatos" if dry_run else "borrados"
    logging.info(
        "Limpieza terminada en %s: %s archivos %s, %s omitidos.",
        target_dir,
        deleted,
        action,
        skipped,
    )
    return deleted


def remove_empty_dirs(root_dir: Path, dry_run: bool) -> None:
    for path in sorted(root_dir.rglob("*"), key=lambda item: len(item.parts), reverse=True):
        if not path.is_dir():
            continue

        try:
            next(path.iterdir())
        except StopIteration:
            if dry_run:
                logging.info("Se borraría carpeta vacía: %s", path)
            else:
                logging.info("Borrando carpeta vacía: %s", path)
                path.rmdir()


def main() -> int:
    load_dotenv()
    parser = build_parser()
    args = parser.parse_args()
    configure_logging(args.log_level)

    try:
        root_path = Path(args.root_path).expanduser().resolve()
        for target in args.targets:
            cleanup_directory(root_path / target / args.username, args.min_age_hours, args.dry_run)
        return 0
    except Exception as exc:
        logging.exception("Error limpiando archivos antiguos: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
