"""Black-box tests of the self-contained Windows EXE; Python is a development tool only."""
import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
EXE = HERE / 'FF13LanguageSwitch.exe'
ORIGINAL = Path(os.environ.get('FF13_ORIGINAL_DIR', HERE / 'test_data' / 'xiii'))
XIII2_ORIGINAL = Path(os.environ.get('FF13_2_ORIGINAL_DIR', HERE / 'test_data' / 'xiii2'))
FILES = {
    'FFXiiiLauncher.exe': (
        'bca100658d01eded346c9302fda6dca80e99247810b87b18686dcc46fbc035aa',
        'd52ace473ad91be1a79777df4c7f39664fba1217609fc2f517dc9dd09bf2e183'),
    'white_data/prog/win/bin/ffxiiiimg.exe': (
        '0e48f3f374a28958493be97a77a76764e33854f92714fe7cfbb01e12d606eb75',
        '3e24354e1d4495d1633e1514fcc97cb4d1b54c201c135511cd22174e8b61334b'),
}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class NativeTests(unittest.TestCase):
    files = FILES
    original = ORIGINAL
    game = 'xiii'
    main_process = 'ffxiiiimg.exe'
    def setUp(self):
        self.assertTrue(EXE.is_file(), 'Standalone native EXE has not been built yet')
        if not all((self.original / rel).is_file() for rel in self.files):
            self.skipTest(f'Original game fixtures missing in {self.original}; see README.md')
        self.temp = tempfile.TemporaryDirectory(prefix='ff13_native_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / '遊戲'
        self.backup = Path(self.temp.name) / 'original'
        for rel in self.files:
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(self.original / rel, target)

    def run_switch(self, mode, exe=EXE, env=None, backup=True):
        args = [str(exe), mode, '--quiet', '--game', self.game, '--game-dir', str(self.root)]
        if backup:
            args += ['--backup-dir', str(self.backup)]
        return subprocess.run(args, timeout=30, env=env).returncode

    def hashes(self):
        return {rel: digest(self.root / rel) for rel in self.files}

    def test_roundtrip_and_idempotency(self):
        for mode, column in [('zh', 1), ('en', 0), ('zh', 1)]:
            self.assertEqual(self.run_switch(mode), 0)
            self.assertEqual(self.hashes(), {p: hashes[column] for p, hashes in self.files.items()})
        backups = list(self.backup.rglob('*.exe'))
        self.assertEqual(len(backups), 4)
        before = {p: p.stat().st_mtime_ns for p in backups}
        targets = {p: (self.root / p).stat().st_mtime_ns for p in self.files}
        self.assertEqual(self.run_switch('zh'), 0)
        self.assertEqual(before, {p: p.stat().st_mtime_ns for p in backups})
        self.assertEqual(targets, {p: (self.root / p).stat().st_mtime_ns for p in self.files})

    def test_unknown_file_refuses_all_changes(self):
        with (self.root / next(iter(self.files))).open('r+b') as stream:
            stream.seek(500)
            stream.write(b'UNKNOWN')
        before = self.hashes()
        self.assertNotEqual(self.run_switch('zh'), 0)
        self.assertEqual(before, self.hashes())
        self.assertFalse(self.backup.exists())

    def test_corrupt_backup_is_not_overwritten(self):
        rel = next(iter(self.files))
        target = self.backup / self.files[rel][0] / rel
        target.parent.mkdir(parents=True)
        target.write_bytes(b'keep invalid backup')
        before = self.hashes()
        self.assertNotEqual(self.run_switch('zh'), 0)
        self.assertEqual(before, self.hashes())
        self.assertEqual(target.read_bytes(), b'keep invalid backup')

    def test_read_only_status(self):
        before = self.hashes()
        self.assertEqual(self.run_switch('status'), 0)
        self.assertEqual(before, self.hashes())
        self.assertFalse(self.backup.exists())

    def test_second_file_commit_failure_rolls_back_first(self):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        locked = kernel.CreateFileW(str(self.root / list(self.files)[1]),
                                    0x80000000, 1, None, 3, 0, None)
        self.assertNotEqual(locked, ctypes.c_void_p(-1).value)
        before = self.hashes()
        try:
            self.assertNotEqual(self.run_switch('zh'), 0)
        finally:
            kernel.CloseHandle(locked)
        self.assertEqual(before, self.hashes())
        self.assertFalse(list(self.root.rglob('*.tmp')))

    def test_exe_runs_alone_without_scripts_or_path(self):
        alone = Path(self.temp.name) / 'standalone'
        alone.mkdir()
        native = alone / EXE.name
        shutil.copy2(EXE, native)
        environment = dict(os.environ, PATH='')
        self.assertEqual(self.run_switch('zh', native, env=environment), 0)
        self.assertEqual(self.hashes(), {p: h[1] for p, h in self.files.items()})
        self.assertEqual(list(alone.iterdir()), [native])

    def test_mixed_known_modes_can_be_unified(self):
        self.assertEqual(self.run_switch('zh'), 0)
        launcher = next(iter(self.files))
        shutil.copy2(self.original / launcher, self.root / launcher)
        self.assertEqual(self.run_switch('zh'), 0)
        self.assertEqual(self.hashes(), {p: h[1] for p, h in self.files.items()})

    def test_backup_directory_failure_does_not_change_game(self):
        self.backup.write_bytes(b'not a directory')
        before = self.hashes()
        self.assertNotEqual(self.run_switch('zh'), 0)
        self.assertEqual(before, self.hashes())

    def test_running_game_process_prevents_backups_and_changes(self):
        # A suspended copy supplies a real process name without running a game or opening a GUI.
        fake_game = Path(self.temp.name) / self.main_process
        shutil.copy2(EXE, fake_game)
        process = subprocess.Popen([str(fake_game)], creationflags=0x00000004)
        before = self.hashes()
        try:
            self.assertNotEqual(self.run_switch('zh'), 0)
            self.assertEqual(before, self.hashes())
            self.assertFalse(self.backup.exists())
        finally:
            process.terminate()
            process.wait(timeout=10)

    def test_game_is_inferred_from_explicit_directory(self):
        result = subprocess.run([str(EXE), 'zh', '--quiet', '--game-dir', str(self.root),
                                 '--backup-dir', str(self.backup)], timeout=30)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.hashes(), {p: h[1] for p, h in self.files.items()})

    def test_ambiguous_directory_requires_explicit_game(self):
        if self.game == 'xiii':
            other = XIII2_ORIGINAL / 'FFXiii2Launcher.exe'
        else:
            other = ORIGINAL / 'FFXiiiLauncher.exe'
        if not other.is_file():
            self.skipTest(f'Other-game fixture missing: {other}; see README.md')
        shutil.copy2(other, self.root / other.name)
        before = self.hashes()
        result = subprocess.run([str(EXE), 'zh', '--quiet', '--game-dir', str(self.root),
                                 '--backup-dir', str(self.backup)], timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.hashes())
        self.assertFalse(self.backup.exists())

    def test_explicit_backup_flag_uses_local_namespace(self):
        alone = Path(self.temp.name) / 'standalone'
        alone.mkdir()
        native = alone / EXE.name
        shutil.copy2(EXE, native)
        self.backup.mkdir()
        result = subprocess.run([str(native), 'zh', '--quiet', '--backup', '--game', self.game,
                                 '--game-dir', str(self.root)], timeout=30)
        self.assertEqual(result.returncode, 0)
        expected = self.root / 'original' / 'language_switcher'
        if self.game == 'xiii2':
            expected /= 'XIII-2'
        for rel, hashes in self.files.items():
            self.assertEqual(digest(expected / hashes[0] / rel), hashes[0])
        self.assertFalse(list(self.backup.iterdir()))

    def test_default_switching_creates_no_backup_directory(self):
        for mode, column in [('zh', 1), ('en', 0)]:
            self.assertEqual(self.run_switch(mode, backup=False), 0)
            self.assertEqual(self.hashes(), {p: h[column] for p, h in self.files.items()})
            self.assertFalse((self.root / 'original').exists())
            self.assertFalse(self.backup.exists())
            self.assertFalse(list(self.root.rglob('*.tmp')))

    def test_default_ignores_unusable_unrequested_backup_path(self):
        sentinel = self.root / 'original'
        sentinel.write_bytes(b'leave this file untouched')
        self.assertEqual(self.run_switch('zh', backup=False), 0)
        self.assertEqual(sentinel.read_bytes(), b'leave this file untouched')
        self.assertEqual(self.hashes(), {p: h[1] for p, h in self.files.items()})

    def test_no_backup_second_commit_failure_still_rolls_back(self):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateFileW(str(self.root / list(self.files)[1]), 0x80000000, 1, None, 3, 0, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        before = self.hashes()
        try:
            self.assertNotEqual(self.run_switch('zh', backup=False), 0)
        finally:
            kernel.CloseHandle(handle)
        self.assertEqual(before, self.hashes())
        self.assertFalse((self.root / 'original').exists())
        self.assertFalse(list(self.root.rglob('*.tmp')))

    def test_empty_exe_folder_never_uses_default_installation_or_cwd(self):
        empty = Path(self.temp.name) / 'no-game'
        empty.mkdir()
        native = empty / EXE.name
        shutil.copy2(EXE, native)
        before = self.hashes()
        for profile_args in [[], ['--game', self.game]]:
            result = subprocess.run([str(native), 'status', '--quiet', *profile_args],
                                    cwd=self.root, timeout=30, env=dict(os.environ, PATH=''))
            self.assertNotEqual(result.returncode, 0, 'Empty EXE folder fell back to another game directory')
        self.assertEqual(before, self.hashes())
        self.assertEqual(list(empty.iterdir()), [native])

    def test_detect_exe_folder_with_unrelated_working_directory(self):
        native = self.root / EXE.name
        shutil.copy2(EXE, native)
        elsewhere = Path(self.temp.name) / 'elsewhere'
        elsewhere.mkdir()
        result = subprocess.run([str(native), 'zh', '--quiet'], cwd=elsewhere,
                                timeout=30, env=dict(os.environ, PATH=''))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self.hashes(), {p: h[1] for p, h in self.files.items()})
        self.assertFalse(list(elsewhere.iterdir()))

    def test_drive_root_exe_does_not_resolve_to_drive_working_directory(self):
        # Map an unused temporary DOS drive, so no real drive-root files are created.
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.GetLogicalDrives.restype = wintypes.DWORD
        kernel.DefineDosDeviceW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR]
        kernel.DefineDosDeviceW.restype = wintypes.BOOL
        used = kernel.GetLogicalDrives()
        letter = next((chr(code) + ':' for code in range(ord('Z'), ord('P')-1, -1)
                       if not (used & (1 << (code-ord('A'))))), None)
        if letter is None:
            self.skipTest('No unused drive letter available')
        base = Path(self.temp.name).resolve()
        native = base / EXE.name
        shutil.copy2(EXE, native)
        target = '\\??\\' + str(base)
        self.assertTrue(kernel.DefineDosDeviceW(0x9, letter, target), ctypes.get_last_error())
        try:
            result = subprocess.run([letter + '\\' + EXE.name, 'status', '--quiet'],
                                    cwd=letter + '\\' + self.root.name, timeout=30,
                                    env=dict(os.environ, PATH=''))
            self.assertNotEqual(result.returncode, 0, 'Drive root resolved to its working-directory game')
            self.assertFalse((base / 'original').exists())
        finally:
            # EXACT_MATCH_ON_REMOVE ensures only this temporary mapping can be removed.
            self.assertTrue(kernel.DefineDosDeviceW(0xf, letter, target), ctypes.get_last_error())

    def test_wrong_game_profile_does_not_modify_any_file(self):
        before = self.hashes()
        other = 'xiii2' if self.game == 'xiii' else 'xiii'
        result = subprocess.run([str(EXE), 'zh', '--quiet', '--game', other,
                                 '--game-dir', str(self.root), '--backup-dir', str(self.backup)], timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.hashes())
        self.assertFalse(self.backup.exists())


class XIII2NativeTests(NativeTests):
    files = {
        'FFXiii2Launcher.exe': (
            '09940c9e9858c593cd12cd037c44697245645dca4bbff7f4ac7371e6bb30db36',
            '389b6e905a8d75fbc5394217f844bdc8811e41f5789d7679c7501a86be3e99af'),
        'alba_data/prog/win/bin/ffxiii2img.exe': (
            '575ea0325be70108b77f84b6f6a96bb7a02aa3abb151deaeb324b84d6cb5af07',
            'ab40dc456da9547a13beeda514cdce9adcf83c094b4990a746dc653c12025b0a'),
    }
    original = XIII2_ORIGINAL
    game = 'xiii2'
    main_process = 'ffxiii2img.exe'


if __name__ == '__main__':
    unittest.main(verbosity=2)
