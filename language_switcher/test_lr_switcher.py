"""LR integration fixtures use only original EXE/INI copies; no live installation changes."""
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
ORIGINAL = Path(os.environ.get('FF13_LR_ORIGINAL_DIR', HERE / 'test_data' / 'lr'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LRChineseTests(unittest.TestCase):
    edition = 'zh-source'
    game = 'lr'
    namespace = 'LR'

    def setUp(self):
        self.assertTrue(EXE.is_file(), 'Build FF13LanguageSwitch.exe before running tests')
        if not all((ORIGINAL / self.edition / rel).is_file() for rel in ['LRFF13.exe', 'steam_api.ini']):
            self.skipTest(f'Original LR fixtures missing in {ORIGINAL / self.edition}; see README.md')
        self.temp = tempfile.TemporaryDirectory(prefix='lr_switch_')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / '雷光歸來'
        self.root.mkdir()
        self.backup = self.base / 'original'
        for rel in ['LRFF13.exe', 'steam_api.ini']:
            shutil.copy2(ORIGINAL / self.edition / rel, self.root / rel)
        self.original_ini = (self.root / 'steam_api.ini').read_bytes()

    def run_switch(self, mode, exe=EXE, extra=(), explicit_game=True, explicit_backup=True):
        args = [str(exe), mode, '--quiet', '--game-dir', str(self.root)]
        if explicit_game:
            args += ['--game', self.game]
        if explicit_backup:
            args += ['--backup-dir', str(self.backup)]
        return subprocess.run(args + list(extra), env=dict(os.environ, PATH=''), timeout=30).returncode

    def expected(self, mode):
        value = b'tchinese' if self.edition == 'zh-source' else b'english'
        return self.original_ini.replace(b'Language=' + value,
                                         b'Language=' + (b'tchinese' if mode == 'zh' else b'english'))

    def test_roundtrip_changes_only_language_and_never_writes_exe(self):
        main = self.root / 'LRFF13.exe'
        before = (digest(main), main.stat().st_mtime_ns)
        for mode in ['zh', 'en', 'zh', 'en']:
            self.assertEqual(self.run_switch(mode), 0)
            self.assertEqual((self.root / 'steam_api.ini').read_bytes(), self.expected(mode))
            self.assertEqual(before, (digest(main), main.stat().st_mtime_ns))
        backups = list(self.backup.rglob('steam_api.ini'))
        self.assertEqual(len(backups), 2)
        self.assertEqual({p.read_bytes() for p in backups}, {self.expected('zh'), self.expected('en')})
        self.assertFalse(list(self.backup.rglob('*.exe')))

    def test_idempotent_mode_does_not_write_or_backup(self):
        mode = 'zh' if self.edition == 'zh-source' else 'en'
        before = (self.root / 'steam_api.ini').stat().st_mtime_ns
        self.assertEqual(self.run_switch(mode), 0)
        self.assertEqual(before, (self.root / 'steam_api.ini').stat().st_mtime_ns)
        self.assertFalse(self.backup.exists())

    def test_unknown_exe_prevents_any_change(self):
        with (self.root / 'LRFF13.exe').open('r+b') as stream:
            stream.seek(500)
            stream.write(b'UNKNOWN')
        self.assertNotEqual(self.run_switch('en' if self.edition == 'zh-source' else 'zh'), 0)
        self.assertEqual((self.root / 'steam_api.ini').read_bytes(), self.original_ini)
        self.assertFalse(self.backup.exists())

    def test_unknown_ini_is_not_overwritten(self):
        target = self.root / 'steam_api.ini'
        data = self.original_ini + b'\r\ncustom=true\r\n'
        target.write_bytes(data)
        self.assertNotEqual(self.run_switch('zh'), 0)
        self.assertEqual(target.read_bytes(), data)
        self.assertFalse(self.backup.exists())

    def test_corrupt_backup_is_not_overwritten(self):
        target = self.backup / hashlib.sha256(self.original_ini).hexdigest() / 'steam_api.ini'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'keep invalid backup')
        self.assertNotEqual(self.run_switch('en' if self.edition == 'zh-source' else 'zh'), 0)
        self.assertEqual(target.read_bytes(), b'keep invalid backup')
        self.assertEqual((self.root / 'steam_api.ini').read_bytes(), self.original_ini)

    def test_backup_directory_failure_keeps_original(self):
        self.backup.write_bytes(b'not a directory')
        self.assertNotEqual(self.run_switch('en' if self.edition == 'zh-source' else 'zh'), 0)
        self.assertEqual((self.root / 'steam_api.ini').read_bytes(), self.original_ini)

    def test_locked_ini_keeps_original_and_cleans_temporary_file(self):
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                                      ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateFileW(str(self.root / 'steam_api.ini'), 0x80000000, 1, None, 3, 0, None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        try:
            self.assertNotEqual(self.run_switch('en' if self.edition == 'zh-source' else 'zh'), 0)
        finally:
            kernel.CloseHandle(handle)
        self.assertEqual((self.root / 'steam_api.ini').read_bytes(), self.original_ini)
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_running_lr_prevents_changes(self):
        suspended = self.base / 'LRFF13.exe'
        shutil.copy2(EXE, suspended)
        process = subprocess.Popen([str(suspended)], creationflags=4)
        try:
            self.assertNotEqual(self.run_switch('zh'), 0)
            self.assertEqual((self.root / 'steam_api.ini').read_bytes(), self.original_ini)
            self.assertFalse(self.backup.exists())
        finally:
            process.terminate()
            process.wait(timeout=10)

    def test_standalone_exe_with_empty_path(self):
        alone = self.base / 'standalone'
        alone.mkdir()
        native = alone / EXE.name
        shutil.copy2(EXE, native)
        self.assertEqual(self.run_switch('zh', native), 0)
        self.assertEqual((self.root / 'steam_api.ini').read_bytes(), self.expected('zh'))
        self.assertEqual(list(alone.iterdir()), [native])

    def test_infer_lr_from_directory(self):
        self.assertEqual(self.run_switch('zh', explicit_game=False), 0)
        self.assertEqual((self.root / 'steam_api.ini').read_bytes(), self.expected('zh'))

    def test_explicit_backup_flag_uses_local_namespace(self):
        alone = self.base / 'standalone'
        alone.mkdir()
        self.backup.mkdir()
        native = alone / EXE.name
        shutil.copy2(EXE, native)
        self.assertEqual(self.run_switch('en' if self.edition == 'zh-source' else 'zh', native,
                                         explicit_backup=False, extra=('--backup',)), 0)
        target = self.root / 'original' / 'language_switcher' / self.namespace / hashlib.sha256(self.original_ini).hexdigest() / 'steam_api.ini'
        self.assertEqual(target.read_bytes(), self.original_ini)
        self.assertFalse(list(self.backup.iterdir()))

    def test_default_switching_creates_no_backup_directory(self):
        for mode in ['en', 'zh']:
            self.assertEqual(self.run_switch(mode, explicit_backup=False), 0)
            self.assertEqual((self.root / 'steam_api.ini').read_bytes(), self.expected(mode))
            self.assertFalse((self.root / 'original').exists())
            self.assertFalse(self.backup.exists())
            self.assertFalse(list(self.root.rglob('*.tmp')))

    def test_default_ignores_unusable_unrequested_backup_path(self):
        sentinel = self.root / 'original'
        sentinel.write_bytes(b'leave this file untouched')
        mode = 'en' if self.edition == 'zh-source' else 'zh'
        self.assertEqual(self.run_switch(mode, explicit_backup=False), 0)
        self.assertEqual(sentinel.read_bytes(), b'leave this file untouched')
        self.assertEqual((self.root / 'steam_api.ini').read_bytes(), self.expected(mode))

    def test_status_is_read_only(self):
        self.assertEqual(self.run_switch('status'), 0)
        self.assertEqual((self.root / 'steam_api.ini').read_bytes(), self.original_ini)
        self.assertFalse(self.backup.exists())

    def test_profile_never_redirects_invalid_local_installation(self):
        copied = self.root / EXE.name
        shutil.copy2(EXE, copied)
        target = self.root / 'steam_api.ini'
        target.write_bytes(self.original_ini + b'\r\nwrong-directory=true\r\n')
        before = target.read_bytes()
        result = subprocess.run([str(copied), 'status', '--game', self.game, '--quiet'], timeout=30)
        self.assertNotEqual(result.returncode, 0, 'Profile redirected to an installation outside the EXE folder')
        self.assertEqual(target.read_bytes(), before)
        self.assertFalse(self.backup.exists())

    def test_empty_exe_folder_never_uses_default_installation_or_cwd(self):
        empty = self.base / 'no-game'
        empty.mkdir()
        native = empty / EXE.name
        shutil.copy2(EXE, native)
        for profile_args in [[], ['--game', self.game]]:
            result = subprocess.run([str(native), 'status', '--quiet', *profile_args],
                                    cwd=self.root, timeout=30, env=dict(os.environ, PATH=''))
            self.assertNotEqual(result.returncode, 0, 'Empty EXE folder fell back to another installation')
        self.assertEqual((self.root / 'steam_api.ini').read_bytes(), self.original_ini)
        self.assertEqual(list(empty.iterdir()), [native])

    def test_detect_exe_folder_with_unrelated_working_directory(self):
        native = self.root / EXE.name
        shutil.copy2(EXE, native)
        elsewhere = self.base / 'elsewhere'
        elsewhere.mkdir()
        mode = 'en' if self.edition == 'zh-source' else 'zh'
        result = subprocess.run([str(native), mode, '--quiet'], cwd=elsewhere,
                                timeout=30, env=dict(os.environ, PATH=''))
        self.assertEqual(result.returncode, 0)
        self.assertEqual((self.root / 'steam_api.ini').read_bytes(), self.expected(mode))
        self.assertFalse(list(elsewhere.iterdir()))

    def test_wrong_game_profile_is_rejected(self):
        self.assertNotEqual(self.run_switch('zh', extra=('--game', 'xiii')), 0)
        self.assertEqual((self.root / 'steam_api.ini').read_bytes(), self.original_ini)
        self.assertFalse(self.backup.exists())


class LREnglishTests(LRChineseTests):
    edition = 'en-source'
    game = 'lr-en'
    namespace = 'LR'


if __name__ == '__main__':
    unittest.main(verbosity=2)
