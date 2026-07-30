import subprocess
import sys
import tempfile
import unittest
import zipfile
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class ReleaseExportTests(unittest.TestCase):
    def test_wrappers_use_one_cross_platform_python_implementation(self):
        windows_wrapper = (PROJECT_ROOT / 'export.bat').read_text(encoding='utf-8')
        posix_wrapper = (PROJECT_ROOT / 'export.sh').read_text(encoding='utf-8')

        self.assertIn('scripts\\export_release.py', windows_wrapper)
        self.assertIn('scripts/export_release.py', posix_wrapper)
        self.assertNotIn('Compress-Archive', windows_wrapper)
        self.assertNotIn('zip -r', posix_wrapper)
        self.assertNotIn('dirname', posix_wrapper)

    def test_collect_release_files_excludes_runtime_and_teaching_data(self):
        from scripts.export_release import collect_release_files

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / 'app.py').write_text('print("ok")', encoding='utf-8')
            (root / 'README.md').write_text('demo', encoding='utf-8')
            (root / '.env').write_text('SECRET=value', encoding='utf-8')
            (root / 'students.xlsx').write_bytes(b'private')
            (root / 'uploads').mkdir()
            (root / 'uploads' / 'payload.xlsx').write_bytes(b'private')
            (root / 'logs').mkdir()
            (root / 'logs' / 'system.log').write_text('log', encoding='utf-8')
            (root / '.venv').mkdir()
            (root / '.venv' / 'marker.txt').write_text('venv', encoding='utf-8')
            (root / '.worktrees').mkdir()
            (root / '.worktrees' / 'other-branch.py').write_text(
                'not part of this release', encoding='utf-8'
            )

            relative_paths = {
                path.relative_to(root).as_posix()
                for path in collect_release_files(root)
            }

        self.assertEqual({'README.md', 'app.py'}, relative_paths)

    def test_build_release_creates_timestamped_zip_with_relative_paths(self):
        from scripts.export_release import build_release

        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / 'project'
            project_dir.mkdir()
            (project_dir / 'app.py').write_text('print("ok")', encoding='utf-8')
            (project_dir / 'templates').mkdir()
            (project_dir / 'templates' / 'index.html').write_text(
                'demo', encoding='utf-8'
            )

            archive_path, file_count = build_release(
                project_dir=project_dir,
                output_dir=project_dir / 'export',
                now=datetime(2026, 7, 24, 17, 30, 5),
            )

            self.assertEqual(
                'student_analysis_20260724_173005.zip', archive_path.name
            )
            self.assertEqual(2, file_count)
            with zipfile.ZipFile(archive_path) as archive:
                self.assertEqual(
                    ['app.py', 'templates/index.html'], sorted(archive.namelist())
                )

    def test_cli_runs_without_external_zip_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir) / 'project'
            project_dir.mkdir()
            (project_dir / 'app.py').write_text('print("ok")', encoding='utf-8')
            output_dir = project_dir / 'packages'

            result = subprocess.run(
                [
                    sys.executable,
                    str(PROJECT_ROOT / 'scripts' / 'export_release.py'),
                    '--project-dir',
                    str(project_dir),
                    '--output',
                    str(output_dir),
                    '--version',
                    'demo-1',
                ],
                capture_output=True,
                text=True,
                check=False,
            )

            self.assertEqual(0, result.returncode, result.stderr)
            self.assertTrue((output_dir / 'student_analysis_demo-1.zip').is_file())


if __name__ == '__main__':
    unittest.main()
