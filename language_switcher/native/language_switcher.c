#define UNICODE
#define _UNICODE
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tlhelp32.h>
#include <wincrypt.h>
#include <shellapi.h>

/* No C runtime, embedded game assets, interpreter, or non-system DLL. */
#define CAP 1024
typedef struct {
    const WCHAR *rel;
    DWORD size;
    const char *hash[2];
} Spec;
static const Spec specs_xiii[2] = {
    {L"FFXiiiLauncher.exe", 1692672,
     {"bca100658d01eded346c9302fda6dca80e99247810b87b18686dcc46fbc035aa",
      "d52ace473ad91be1a79777df4c7f39664fba1217609fc2f517dc9dd09bf2e183"}},
    {L"white_data\\prog\\win\\bin\\ffxiiiimg.exe", 36687360,
     {"0e48f3f374a28958493be97a77a76764e33854f92714fe7cfbb01e12d606eb75",
      "3e24354e1d4495d1633e1514fcc97cb4d1b54c201c135511cd22174e8b61334b"}}
};
static const Spec specs_xiii2[2] = {
    {L"FFXiii2Launcher.exe", 456704,
     {"09940c9e9858c593cd12cd037c44697245645dca4bbff7f4ac7371e6bb30db36",
      "389b6e905a8d75fbc5394217f844bdc8811e41f5789d7679c7501a86be3e99af"}},
    {L"alba_data\\prog\\win\\bin\\ffxiii2img.exe", 34123776,
     {"575ea0325be70108b77f84b6f6a96bb7a02aa3abb151deaeb324b84d6cb5af07",
      "ab40dc456da9547a13beeda514cdce9adcf83c094b4990a746dc653c12025b0a"}}
};
/* LR shares its unmodified EXE; each INI style retains its own original header. */
static Spec specs_lr[2] = {
    {L"steam_api.ini", 0, {NULL, NULL}},
    {L"LRFF13.exe", 33983488,
     {"e4b86525fb84e34f76df4a3ed41d135e6de5deb41f9286c2eb0a936a5017e1f5",
      "e4b86525fb84e34f76df4a3ed41d135e6de5deb41f9286c2eb0a936a5017e1f5"}}
};
static const DWORD lr_sizes[2][2] = {{3558, 3559}, {3591, 3592}};
static const DWORD lr_offsets[2] = {1230, 1263};
static const char *lr_hashes[2][2] = {
    {"5489243563a29e7a902900d59084f2e30c1a8b47633852a4372e5cb3044df11e",
     "807f3f99e7ae780a0d2e72f0bbcf3b4390acecb805647f5cccc0b896ffd8bb9b"},
    {"b48932e8638dd2c9fd6bae9428845d1dd51857f78eff971cf4c0cffbd1e0447f",
     "202c24c015a12c254fedb76ae6fd9e47fbd24a0986dd2b6a0fe3ffdcee90fcb7"}
};
static int lr_style;
static const Spec *specs = specs_xiii;
static int game_index = -1;
static const WCHAR *game_labels[3] = {L"FINAL FANTASY XIII", L"FINAL FANTASY XIII-2", L"LIGHTNING RETURNS"};
static const WCHAR *game_processes[3] = {L"ffxiiiimg.exe", L"ffxiii2img.exe", L"LRFF13.exe"};
static const WCHAR *game_markers[3] = {L"FFXiiiLauncher.exe", L"FFXiii2Launcher.exe", L"LRFF13.exe"};
static const WCHAR *backup_names[3] = {NULL, L"XIII-2", L"LR"};
static const WCHAR title[] = L"FF XIII 系列語言切換";
typedef struct {
    WCHAR path[CAP], temp[CAP];
    BYTE *data;
    int mode, changed, committed;
} State;
static State states[2];
static WCHAR game[CAP], backup[CAP], message[4096], error_text[4096];
static WCHAR module[CAP], scratch[CAP], backup_folder[CAP], backup_path[CAP], saved_error[4096];
static const WCHAR *labels[2] = {L"英文", L"繁體中文（內建資源）"};
static HCRYPTPROV provider;
static int quiet;
static int backup_enabled;
static const WCHAR hex[] = L"0123456789abcdef";

static BOOL cat(WCHAR *dst, DWORD capacity, const WCHAR *src) {
    DWORD i = (DWORD)lstrlenW(dst), j = 0;
    while (src[j] && i + 1 < capacity) dst[i++] = src[j++];
    dst[i] = 0;
    return src[j] == 0;
}
static BOOL fail(const WCHAR *why, const WCHAR *path) {
    lstrcpynW(error_text, why, 4096);
    if (path) { cat(error_text, 4096, L"\n"); cat(error_text, 4096, path); }
    return FALSE;
}
static BOOL join(WCHAR *out, const WCHAR *base, const WCHAR *rel) {
    DWORD n = (DWORD)lstrlenW(base);
    if (n + (DWORD)lstrlenW(rel) + 2 >= CAP) return fail(L"路徑過長。", base);
    lstrcpynW(out, base, CAP);
    if (n && out[n-1] != L'\\') cat(out, CAP, L"\\");
    return cat(out, CAP, rel);
}
static BOOL fullpath(WCHAR *out, const WCHAR *in) {
    DWORD n = GetFullPathNameW(in, CAP, out, NULL);
    if (!n || n >= CAP) return fail(L"無法解析路徑。", in);
    while (n > 3 && out[n-1] == L'\\') out[--n] = 0;
    return TRUE;
}
static BOOL isdir(const WCHAR *path) {
    DWORD a = GetFileAttributesW(path);
    return a != INVALID_FILE_ATTRIBUTES && (a & FILE_ATTRIBUTE_DIRECTORY);
}
static BOOL parent_dirs(const WCHAR *path) {
    WCHAR part[CAP];
    DWORD i, separators = 0;
    lstrcpynW(part, path, CAP);
    for (i = 0; part[i]; ++i) {
        if (part[i] != L'\\') continue;
        if (i < 3) continue;
        if (part[0] == L'\\' && part[1] == L'\\' && ++separators < 2) continue;
        part[i] = 0;
        if (!CreateDirectoryW(part, NULL) && !isdir(part)) return fail(L"無法建立備份目錄。", part);
        part[i] = L'\\';
    }
    return TRUE;
}
static BOOL hash_bytes(const BYTE *data, DWORD size, WCHAR *out) {
    HCRYPTHASH h;
    BYTE digest[32];
    DWORD n = 32, i;
    BOOL ok;
    if (!CryptCreateHash(provider, CALG_SHA_256, 0, 0, &h)) return fail(L"無法建立 SHA-256 校驗。", NULL);
    ok = CryptHashData(h, data, size, 0) && CryptGetHashParam(h, HP_HASHVAL, digest, &n, 0);
    CryptDestroyHash(h);
    if (!ok || n != 32) return fail(L"SHA-256 校驗失敗。", NULL);
    for (i = 0; i < 32; ++i) { out[2*i] = hex[digest[i] >> 4]; out[2*i+1] = hex[digest[i] & 15]; }
    out[64] = 0;
    return TRUE;
}
static BOOL matches(const WCHAR *actual, const char *expected) {
    DWORD i;
    for (i = 0; i < 64; ++i) if (actual[i] != (WCHAR)expected[i]) return FALSE;
    return TRUE;
}
static BOOL read_data(const WCHAR *path, DWORD size, BYTE **out) {
    HANDLE file;
    LARGE_INTEGER length;
    BYTE *data = NULL;
    DWORD read = 0;
    BOOL ok = FALSE;
    file = CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                       NULL, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return fail(L"無法讀取檔案。", path);
    if (GetFileSizeEx(file, &length) && length.QuadPart == size) {
        data = HeapAlloc(GetProcessHeap(), 0, size + 1); /* LR value can grow by one byte. */
        if (data) ok = ReadFile(file, data, size, &read, NULL) && read == size;
    }
    CloseHandle(file);
    if (!ok) {
        if (data) HeapFree(GetProcessHeap(), 0, data);
        return fail(L"檔案大小不符、記憶體不足或讀取失敗。", path);
    }
    *out = data;
    return TRUE;
}
static DWORD expected_size(int index, int mode) {
    return game_index >= 2 && index == 0 ? lr_sizes[lr_style][mode] : specs[index].size;
}
static BOOL verify_file(const WCHAR *path, int index, int mode) {
    BYTE *data;
    WCHAR actual[65];
    BOOL ok;
    DWORD size = expected_size(index, mode);
    if (!read_data(path, size, &data)) return FALSE;
    ok = hash_bytes(data, size, actual) && matches(actual, specs[index].hash[mode]);
    HeapFree(GetProcessHeap(), 0, data);
    return ok || fail(L"檔案校驗不符，已停止且不覆寫既有備份。", path);
}
static BOOL inspect(void) {
    int i;
    WCHAR actual[65];
    if (game_index >= 2) {
        WIN32_FILE_ATTRIBUTE_DATA attr;
        DWORD size;
        if (!join(states[0].path, game, L"steam_api.ini")) return FALSE;
        if (!GetFileAttributesExW(states[0].path, GetFileExInfoStandard, &attr) || attr.nFileSizeHigh)
            return fail(L"無法讀取 LR 設定檔。", states[0].path);
        size = attr.nFileSizeLow;
        if (size == 3558 || size == 3559) lr_style = 0;
        else if (size == 3591 || size == 3592) lr_style = 1;
        else return fail(L"無法辨識 LR 設定檔版本，未修改任何檔案。", states[0].path);
        specs_lr[0].size = size;
        specs_lr[0].hash[0] = lr_hashes[lr_style][0];
        specs_lr[0].hash[1] = lr_hashes[lr_style][1];
    }
    for (i = 0; i < 2; ++i) {
        if (states[i].data) HeapFree(GetProcessHeap(), 0, states[i].data);
        states[i].data = NULL;
        if (!join(states[i].path, game, specs[i].rel) ||
            !read_data(states[i].path, specs[i].size, &states[i].data) ||
            !hash_bytes(states[i].data, specs[i].size, actual)) return FALSE;
        if (matches(actual, specs[i].hash[0])) states[i].mode = 0;
        else if (matches(actual, specs[i].hash[1])) states[i].mode = 1;
        else return fail(L"無法辨識檔案版本，遊戲檔案均未修改。", states[i].path);
    }
    return TRUE;
}
static BOOL require_closed(void) {
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    PROCESSENTRY32W entry;
    BOOL present;
    DWORD error;
    if (snap == INVALID_HANDLE_VALUE) return fail(L"無法檢查執行中的程式。", NULL);
    entry.dwSize = sizeof(entry);
    present = Process32FirstW(snap, &entry);
    while (present) {
        if (!lstrcmpiW(entry.szExeFile, game_processes[game_index]) || !lstrcmpiW(entry.szExeFile, game_markers[game_index])) {
            CloseHandle(snap);
            return fail(L"請先關閉遊戲與啟動器，再切換語言。", NULL);
        }
        present = Process32NextW(snap, &entry);
    }
    error = GetLastError();
    CloseHandle(snap);
    return error == ERROR_NO_MORE_FILES || fail(L"無法完成程序檢查。", NULL);
}
static BOOL write_new(const WCHAR *path, const BYTE *data, DWORD size) {
    DWORD written = 0;
    BOOL ok;
    HANDLE file = CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);
    if (file == INVALID_HANDLE_VALUE) return fail(L"無法建立檔案，未覆寫既有檔案。", path);
    ok = WriteFile(file, data, size, &written, NULL) && written == size && FlushFileBuffers(file);
    CloseHandle(file);
    if (!ok) { DeleteFileW(path); return fail(L"寫入失敗，已移除本次未完成的暫存檔。", path); }
    return TRUE;
}
static BOOL ensure_backup(int index) {
    WCHAR digest[65];
    State *s = &states[index];
    DWORD a;
    if (!hash_bytes(s->data, specs[index].size, digest) ||
        !join(backup_folder, backup, digest) || !join(backup_path, backup_folder, specs[index].rel)) return FALSE;
    a = GetFileAttributesW(backup_path);
    if (a != INVALID_FILE_ATTRIBUTES) return verify_file(backup_path, index, s->mode);
    if (GetLastError() != ERROR_FILE_NOT_FOUND && GetLastError() != ERROR_PATH_NOT_FOUND)
        return fail(L"無法檢查備份。", backup_path);
    if (!parent_dirs(backup_path) || !write_new(backup_path, s->data, specs[index].size)) return FALSE;
    return verify_file(backup_path, index, s->mode);
}
static void patch(int index, int mode) {
    BYTE *p = states[index].data;
    if (game_index >= 2) {
        if (!index) {
            DWORD size = specs_lr[0].size, offset = lr_offsets[lr_style], i;
            DWORD old_len = size - lr_sizes[lr_style][0] + 7, new_len = mode ? 8 : 7;
            const char *value = mode ? "tchinese" : "english";
            if (new_len > old_len) {
                for (i = size; i > offset + old_len; --i) p[i] = p[i-1];
            } else if (new_len < old_len) {
                for (i = offset + old_len; i < size; ++i) p[i-1] = p[i];
            }
            for (i = 0; i < new_len; ++i) p[offset+i] = (BYTE)value[i];
            specs_lr[0].size = lr_sizes[lr_style][mode];
        }
        return;
    }
    if (game_index == 1) {
        if (!index) {
            p[0xcf5] = mode ? 0x1d : 0x28;
            p[0xcf6] = mode ? 0x00 : 0x08;
            p[0xcf9] = mode ? 0x00 : 0x06;
        } else {
            p[0x2b1b19] = mode ? 0x6a : 0x8b;
            p[0x2b1b1a] = mode ? 0x0a : 0x4c;
            p[0x2b1b1b] = mode ? 0x59 : 0x24;
            p[0x2b1b1c] = mode ? 0x90 : 0x04;
        }
        return;
    }
    if (!index) {
        p[0x17ff] = mode ? 0x1d : 0x28;
        p[0x1800] = mode ? 0x00 : 0x06;
        p[0x1803] = mode ? 0x00 : 0x06;
    } else {
        p[0x47b4] = mode ? 0x6a : 0x8b;
        p[0x47b5] = mode ? 0x0a : 0x4d;
        p[0x47b6] = mode ? 0x59 : 0xf0;
        p[0x6a01] = mode ? 0x00 : 0xc6;
    }
}
static BOOL stage_file(int index) {
    State *s = &states[index];
    WCHAR suffix[32];
    DWORD trial, i, pid = GetCurrentProcessId();
    for (trial = 0; trial < 16; ++trial) {
        lstrcpyW(suffix, L".ff13_");
        for (i = 0; i < 8; ++i) suffix[6+i] = hex[(pid >> (28 - i*4)) & 15];
        suffix[14] = hex[trial]; suffix[15] = 0;
        cat(suffix, 32, L".tmp");
        if ((DWORD)lstrlenW(s->path) + (DWORD)lstrlenW(suffix) >= CAP) return fail(L"暫存路徑過長。", s->path);
        lstrcpynW(s->temp, s->path, CAP); cat(s->temp, CAP, suffix);
        if (GetFileAttributesW(s->temp) != INVALID_FILE_ATTRIBUTES) continue;
        if (!write_new(s->temp, s->data, specs[index].size)) { s->temp[0] = 0; return FALSE; }
        return TRUE;
    }
    s->temp[0] = 0;
    return fail(L"無法取得未使用的暫存檔名。", s->path);
}
static BOOL switch_language(int mode) {
    int i, any = 0;
    HANDLE mutex;
    WCHAR actual[65];
    BOOL ok = FALSE, rollback_ok = TRUE;
    mutex = CreateMutexW(NULL, TRUE, L"Local\\FF13NativeLanguageSwitch");
    if (!mutex) return fail(L"無法取得切換鎖。", NULL);
    if (GetLastError() == ERROR_ALREADY_EXISTS) {
        CloseHandle(mutex); return fail(L"另一個語言切換工具正在執行。", NULL);
    }
    if (!require_closed() || !inspect()) goto done;
    for (i = 0; i < 2; ++i) {
        states[i].changed = !(game_index >= 2 && i == 1) && states[i].mode != mode;
        any |= states[i].changed;
    }
    if (!any) { ok = TRUE; goto done; }
    if (backup_enabled) {
        for (i = 0; i < 2; ++i) if (states[i].changed && !ensure_backup(i)) goto done;
    }
    for (i = 0; i < 2; ++i) if (states[i].changed) {
        patch(i, mode);
        if (!hash_bytes(states[i].data, specs[i].size, actual) || !matches(actual, specs[i].hash[mode])) {
            fail(L"切換資料校驗失敗。", states[i].path); goto rollback;
        }
        if (!stage_file(i) || !verify_file(states[i].temp, i, mode)) goto rollback;
    }
    if (!require_closed()) goto rollback;
    for (i = 0; i < 2; ++i) if (!verify_file(states[i].path, i, states[i].mode)) goto rollback;
    for (i = 0; i < 2; ++i) if (states[i].changed) {
        if (!MoveFileExW(states[i].temp, states[i].path, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH)) {
            fail(L"無法替換檔案，可能被其他程式鎖定。", states[i].path); goto rollback;
        }
        states[i].temp[0] = 0;
        states[i].committed = 1;
    }
    for (i = 0; i < 2; ++i) if (!verify_file(states[i].path, i, mode)) goto rollback;
    ok = TRUE;
    goto done;
rollback:
    lstrcpynW(saved_error, error_text, 4096);
    for (i = 1; i >= 0; --i) if (states[i].committed) {
        patch(i, states[i].mode);
        if (!stage_file(i) || !MoveFileExW(states[i].temp, states[i].path,
                MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH) ||
            !verify_file(states[i].path, i, states[i].mode)) rollback_ok = FALSE;
        else states[i].temp[0] = 0;
    }
    lstrcpynW(error_text, saved_error, 4096);
    if (rollback_ok) cat(error_text, 4096, L"\n\n已回復切換前狀態。");
    else if (backup_enabled) { cat(error_text, 4096, L"\n\n無法完整回復，請使用備份還原：\n"); cat(error_text, 4096, backup); }
    else cat(error_text, 4096, L"\n\n無法完整回復，請檢查遊戲檔案。本次未建立備份。");
done:
    for (i = 0; i < 2; ++i) if (states[i].temp[0]) DeleteFileW(states[i].temp);
    ReleaseMutex(mutex); CloseHandle(mutex);
    return ok;
}
static void status_message(void) {
    int i;
    message[0] = 0;
    cat(message, 4096, game_labels[game_index]); cat(message, 4096, L"\n\n");
    cat(message, 4096, game); cat(message, 4096, L"\n\n");
    for (i = 0; i < 2; ++i) {
        cat(message, 4096, specs[i].rel); cat(message, 4096, L"\n");
        cat(message, 4096, game_index >= 2 && i == 1 ? L"共用原始程式（不修改）" : labels[states[i].mode]);
        cat(message, 4096, L"\n\n");
    }
    cat(message, 4096, backup_enabled ? L"備份：已啟用。\n\n" : L"備份：未啟用（預設）。\n\n");
}
void WINAPI entry(void) {
    int argc, i, mode = -1, result = 1, choice;
    WCHAR **argv, *last;
    const WCHAR *game_arg = NULL, *backup_arg = NULL;
    DWORD n;
    argv = CommandLineToArgvW(GetCommandLineW(), &argc);
    if (!argv) ExitProcess(1);
    for (i = 1; i < argc; ++i) if (!lstrcmpiW(argv[i], L"--quiet")) quiet = 1;
    for (i = 1; i < argc; ++i) {
        if (!lstrcmpiW(argv[i], L"zh")) mode = 1;
        else if (!lstrcmpiW(argv[i], L"en")) mode = 0;
        else if (!lstrcmpiW(argv[i], L"status")) mode = 2;
        else if (!lstrcmpiW(argv[i], L"--game") && i+1 < argc) {
            ++i;
            if (!lstrcmpiW(argv[i], L"xiii")) game_index = 0;
            else if (!lstrcmpiW(argv[i], L"xiii2")) game_index = 1;
            else if (!lstrcmpiW(argv[i], L"lr") || !lstrcmpiW(argv[i], L"lr-zh")) game_index = 2;
            else if (!lstrcmpiW(argv[i], L"lr-en")) game_index = 2;
            else { fail(L"--game 請指定 xiii、xiii2、lr 或 lr-en。", NULL); goto done; }
        }
        else if (!lstrcmpiW(argv[i], L"--quiet")) continue;
        else if (!lstrcmpiW(argv[i], L"--backup")) backup_enabled = 1;
        else if (!lstrcmpiW(argv[i], L"--game-dir") && i+1 < argc) game_arg = argv[++i];
        else if (!lstrcmpiW(argv[i], L"--backup-dir") && i+1 < argc) { backup_arg = argv[++i]; backup_enabled = 1; }
        else { fail(L"參數錯誤。可用：zh、en、status、--game、--game-dir、--backup、--backup-dir、--quiet。", NULL); goto done; }
    }
    n = GetModuleFileNameW(NULL, module, CAP);
    if (!n || n >= CAP) { fail(L"無法取得工具所在路徑。", NULL); goto done; }
    last = NULL; for (i = 0; module[i]; ++i) if (module[i] == L'\\') last = module + i;
    if (!last) { fail(L"無法取得工具資料夾。", NULL); goto done; }
    last[1] = 0; /* Keep X:\ as an absolute root, never drive-relative X:. */
    if (!fullpath(game, game_arg ? game_arg : module)) goto done;
    if (game_index < 0) {
        int found = -1, count = 0, candidate;
        for (candidate = 0; candidate < 3; ++candidate) {
            if (!join(scratch, game, game_markers[candidate])) goto done;
            if (GetFileAttributesW(scratch) != INVALID_FILE_ATTRIBUTES) { found = candidate; ++count; }
        }
        if (count > 1) { fail(L"同目錄有多款遊戲程式，請用 --game 指定遊戲。", game); goto done; }
        if (count == 0) { fail(L"此目錄找不到支援的遊戲。請將本程式放入遊戲主目錄，或明確提供 --game-dir。", game); goto done; }
        game_index = found;
    }
    specs = game_index >= 2 ? specs_lr : (game_index ? specs_xiii2 : specs_xiii);
    if (backup_enabled) {
        if (backup_arg) { if (!fullpath(backup, backup_arg)) goto done; }
        else {
            if (!join(backup, game, L"original")) goto done;
            if (!join(scratch, backup, L"language_switcher")) goto done;
            if (game_index) { if (!join(backup, scratch, backup_names[game_index])) goto done; }
            else lstrcpynW(backup, scratch, CAP);
        }
    }
    if (!CryptAcquireContextW(&provider, NULL, NULL, PROV_RSA_AES, CRYPT_VERIFYCONTEXT | CRYPT_SILENT)) {
        fail(L"無法啟用 Windows SHA-256 校驗。", NULL); goto done;
    }
    if (!inspect()) goto done;
    if (mode < 0) {
        status_message(); cat(message, 4096, L"是：切換繁體中文\n否：切換英文\n取消：不變更\n\n只使用內建中文；不變更語音。請先關閉遊戲。 ");
        choice = MessageBoxW(NULL, message, title, MB_YESNOCANCEL | MB_ICONQUESTION);
        if (choice != IDYES && choice != IDNO) { result = 0; goto done; }
        mode = choice == IDYES ? 1 : 0;
    }
    if (mode == 2) status_message();
    else {
        if (!switch_language(mode)) goto done;
        lstrcpynW(message, game_labels[game_index], 4096);
        cat(message, 4096, L"\n目前已切換為："); cat(message, 4096, labels[mode]);
        if (backup_enabled) { cat(message, 4096, L"\n\n備份目錄：\n"); cat(message, 4096, backup); }
        else cat(message, 4096, L"\n\n未建立備份（預設）。");
        cat(message, 4096, L"\n\n文字、圖像、聲音資源及語音設定均未變更。");
    }
    if (!quiet) MessageBoxW(NULL, message, title, MB_OK | MB_ICONINFORMATION);
    result = 0;
done:
    if (result && !quiet) MessageBoxW(NULL, error_text, L"FF XIII 切換未完成", MB_OK | MB_ICONERROR);
    for (i = 0; i < 2; ++i) if (states[i].data) HeapFree(GetProcessHeap(), 0, states[i].data);
    if (provider) CryptReleaseContext(provider, 0);
    LocalFree(argv);
    ExitProcess((UINT)result);
}
