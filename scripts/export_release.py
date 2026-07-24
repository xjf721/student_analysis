#!/usr/bin/env python3
"""Create a data-free deployment ZIP using only the Python standard library."""

from __future__ import annotations

import argparse
import os
import re
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional, Tuple


EXCLUDED_DIRECTORIES = {
    '.agents',
    '.codex',
    '.git',
    '.idea',
    '.pytest_cache',
    '.venv',
    '.vscode',
    '.worktrees',
    '---bak---',
    '__pycache__',
    'build',
    'dist',
    'export',
    'logs',
    'new-datas',
    'node_modules',
    'uploads',
    'venv',
}
EXCLUDED_FILE_NAMES = {
    '.env',
    'Thumbs.db',
    'desktop.ini',
}
EXCLUDED_ENDINGS = (
    '.7z',
    '.bak',
    '.db',
    '.dump',
    '.gz',
    '.key',
    '.log',
    '.pem',
    '.pyc',
    '.rar',
    '.sql',
    '.sqlite',
    '.sqlite3',
    '.tar',
    '.xls',
    '.xlsx',
    '.zip',
)
SAFE_VERSION = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]*$')


def _should_include_file(path: Path) -> bool:
    name = path.name
    lower_name = name.lower()
    if name in EXCLUDED_FILE_NAMES:
        return False
    if lower_name.startswith('.env.') and lower_name != '.env.example':
        return False
    return not lower_name.endswith(EXCLUDED_ENDINGS)


def collect_release_files(project_dir: Path) -> Iterable[Path]:
    """Return release files in stable relative-path order."""
    project_dir = Path(project_dir).resolve()
    files = []
    for current_root, directory_names, file_names in os.walk(project_dir):
        directory_names[:] = sorted(
            name for name in directory_names if name not in EXCLUDED_DIRECTORIES
        )
        root_path = Path(current_root)
        for file_name in sorted(file_names):
            file_path = root_path / file_name
            if _should_include_file(file_path):
                files.append(file_path)
    return sorted(files, key=lambda path: path.relative_to(project_dir).as_posix())


def build_release(
    project_dir: Path,
    output_dir: Path,
    version: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Tuple[Path, int]:
    """Build and return ``(archive_path, included_file_count)``."""
    project_dir = Path(project_dir).resolve()
    output_dir = Path(output_dir)
    if not output_dir.is_absolute():
        output_dir = project_dir / output_dir
    output_dir = output_dir.resolve()

    if version is not None and not SAFE_VERSION.fullmatch(version):
        raise ValueError('version may contain only letters, numbers, dot, underscore, and dash')

    release_id = version or (now or datetime.now()).strftime('%Y%m%d_%H%M%S')
    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / f'student_analysis_{release_id}.zip'
    temporary_path = output_dir / f'.{archive_path.name}.tmp'
    release_files = list(collect_release_files(project_dir))

    try:
        with zipfile.ZipFile(
            temporary_path,
            mode='w',
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for file_path in release_files:
                archive.write(
                    file_path,
                    arcname=file_path.relative_to(project_dir).as_posix(),
                )
        temporary_path.replace(archive_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()

    return archive_path, len(release_files)


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--project-dir',
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help='project root to package (defaults to this repository)',
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('export'),
        help='output directory, relative to the project root by default',
    )
    parser.add_argument('--version', help='optional safe label used in the ZIP filename')
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    try:
        archive_path, file_count = build_release(
            project_dir=args.project_dir,
            output_dir=args.output,
            version=args.version,
        )
    except (OSError, ValueError, zipfile.BadZipFile) as error:
        print(f'[ERROR] Export failed: {error}', file=sys.stderr)
        return 1

    size_kib = archive_path.stat().st_size / 1024
    print(f'Created: {archive_path}')
    print(f'Files: {file_count}')
    print(f'Size: {size_kib:.1f} KiB')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
