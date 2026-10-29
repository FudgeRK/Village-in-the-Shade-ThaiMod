/* Version-adaptive virtual keyboard memory patch for Village in the Shade.
 * The stored RVAs document the verified v1.20 layout only. Runtime patching
 * resolves every original glyph inside one validated keyboard-data window, so
 * a linker/layout change cannot make the mod write to an old hard-coded RVA.
 */
#pragma once
#include <stdint.h>
#include <windows.h>

typedef struct {
    uint32_t v120_rva;
    const char* thai;
    const char* orig;
    const char* desc;
} VirtualKeyPatchEntry;

static const VirtualKeyPatchEntry g_virtual_key_patches[] = {
    { 0x00E539BC, "ก", "あ", "Hira [ 0]" },
    { 0x00E539C0, "ข", "い", "Hira [ 1]" },
    { 0x00E539C4, "ฃ", "う", "Hira [ 2]" },
    { 0x00E539A4, "ค", "え", "Hira [ 3]" },
    { 0x00E539A8, "ฅ", "お", "Hira [ 4]" },
    { 0x00E539AC, "ล", "や", "Hira [ 5]" },
    { 0x00E539B0, "ว", "ゆ", "Hira [ 6]" },
    { 0x00E539D8, "ศ", "よ", "Hira [ 7]" },
    { 0x00E539DC, "๐", "が", "Hira [ 8]" },
    { 0x00E539E0, "๑", "ぎ", "Hira [ 9]" },
    { 0x00E539E4, "๒", "ぐ", "Hira [10]" },
    { 0x00E539C8, "๓", "げ", "Hira [11]" },
    { 0x00E539CC, "๔", "ご", "Hira [12]" },
    { 0x00E539D0, "ฆ", "か", "Hira [13]" },
    { 0x00E539D4, "ง", "き", "Hira [14]" },
    { 0x00E539F8, "จ", "く", "Hira [15]" },
    { 0x00E539FC, "ฉ", "け", "Hira [16]" },
    { 0x00E53A00, "ช", "こ", "Hira [17]" },
    { 0x00E53A04, "ษ", "ら", "Hira [18]" },
    { 0x00E539E8, "ส", "り", "Hira [19]" },
    { 0x00E539EC, "ห", "る", "Hira [20]" },
    { 0x00E539F0, "ฬ", "れ", "Hira [21]" },
    { 0x00E539F4, "อ", "ろ", "Hira [22]" },
    { 0x00E53A18, "๕", "ざ", "Hira [23]" },
    { 0x00E53A1C, "๖", "じ", "Hira [24]" },
    { 0x00E53A20, "๗", "ず", "Hira [25]" },
    { 0x00E53A24, "๘", "ぜ", "Hira [26]" },
    { 0x00E53A08, "๙", "ぞ", "Hira [27]" },
    { 0x00E53A0C, "ซ", "さ", "Hira [28]" },
    { 0x00E53A10, "ฌ", "し", "Hira [29]" },
    { 0x00E53A14, "ญ", "す", "Hira [30]" },
    { 0x00E53A38, "ฎ", "せ", "Hira [31]" },
    { 0x00E53A3C, "ฏ", "そ", "Hira [32]" },
    { 0x00E53A40, "ฮ", "わ", "Hira [33]" },
    { 0x00E53A44, " ", "を", "Hira [34]" },
    { 0x00E53A28, ".", "ん", "Hira [35]" },
    { 0x00E53A2C, "(", "だ", "Hira [36]" },
    { 0x00E53A30, ")", "ぢ", "Hira [37]" },
    { 0x00E53A34, "[", "づ", "Hira [38]" },
    { 0x00E53A58, "]", "で", "Hira [39]" },
    { 0x00E53A5C, "{", "ど", "Hira [40]" },
    { 0x00E53A60, "ฐ", "た", "Hira [41]" },
    { 0x00E53A64, "ฑ", "ち", "Hira [42]" },
    { 0x00E53A48, "ฒ", "つ", "Hira [43]" },
    { 0x00E53A4C, "ณ", "て", "Hira [44]" },
    { 0x00E53A50, "ด", "と", "Hira [45]" },
    { 0x00E53A54, "0", "ぁ", "Hira [46]" },
    { 0x00E53A78, "1", "ぃ", "Hira [47]" },
    { 0x00E53A7C, "2", "ぅ", "Hira [48]" },
    { 0x00E53A80, "3", "ぇ", "Hira [49]" },
    { 0x00E53A84, "4", "ぉ", "Hira [50]" },
    { 0x00E53A68, "}", "ば", "Hira [51]" },
    { 0x00E53A6C, "+", "び", "Hira [52]" },
    { 0x00E53A70, "=", "ぶ", "Hira [53]" },
    { 0x00E53A74, "*", "べ", "Hira [54]" },
    { 0x00E53A98, ":", "ぼ", "Hira [55]" },
    { 0x00E53A9C, "ต", "な", "Hira [56]" },
    { 0x00E53AA0, "ถ", "に", "Hira [57]" },
    { 0x00E53AA4, "ท", "ぬ", "Hira [58]" },
    { 0x00E53A88, "ธ", "ね", "Hira [59]" },
    { 0x00E53A8C, "น", "の", "Hira [60]" },
    { 0x00E53A90, "5", "ゃ", "Hira [61]" },
    { 0x00E53A94, "6", "ゅ", "Hira [62]" },
    { 0x00E53AB8, "7", "ょ", "Hira [63]" },
    { 0x00E53ABC, "8", "っ", "Hira [64]" },
    { 0x00E53AC0, "9", "ゎ", "Hira [65]" },
    { 0x00E53AC4, ";", "ぱ", "Hira [66]" },
    { 0x00E53AA8, "\"", "ぴ", "Hira [67]" },
    { 0x00E53AAC, "'", "ぷ", "Hira [68]" },
    { 0x00E53AB0, "<", "ぺ", "Hira [69]" },
    { 0x00E53AB4, ">", "ぽ", "Hira [70]" },
    { 0x00E53AD8, "บ", "は", "Hira [71]" },
    { 0x00E53ADC, "ป", "ひ", "Hira [72]" },
    { 0x00E53AE0, "ผ", "ふ", "Hira [73]" },
    { 0x00E53AE4, "ฝ", "へ", "Hira [74]" },
    { 0x00E53AC8, "พ", "ほ", "Hira [75]" },
    { 0x00E53ACC, ",", "・", "Hira [76]" },
    { 0x00E53AD0, "-", "。", "Hira [77]" },
    { 0x00E53AD4, "!", "、", "Hira [78]" },
    { 0x00E53AF8, "?", "！", "Hira [79]" },
    { 0x00E53AFC, "/", "？", "Hira [80]" },
    { 0x00E53B00, "ー", "ー", "Hira [81]" },
    { 0x00E53B04, "～", "～", "Hira [82]" },
    { 0x00E53AE8, "＝", "＝", "Hira [83]" },
    { 0x00E53AEC, "♥", "♥", "Hira [84]" },
    { 0x00E53AF0, "★", "★", "Hira [85]" },
    { 0x00E53AF4, "ฟ", "ま", "Hira [86]" },
    { 0x00E53B18, "ภ", "み", "Hira [87]" },
    { 0x00E53B1C, "ม", "む", "Hira [88]" },
    { 0x00E53B20, "ย", "め", "Hira [89]" },
    { 0x00E53B24, "ร", "も", "Hira [90]" },
    { 0x00E53B08, "ะ", "ア", "Kata [ 0]" },
    { 0x00E53B0C, "า", "イ", "Kata [ 1]" },
    { 0x00E53B10, "ำ", "ウ", "Kata [ 2]" },
    { 0x00E53B14, "ิ", "エ", "Kata [ 3]" },
    { 0x00E53B38, "ี", "オ", "Kata [ 4]" },
    { 0x00E53B3C, "0", "ヤ", "Kata [ 5]" },
    { 0x00E53B40, "1", "ユ", "Kata [ 6]" },
    { 0x00E53B44, "2", "ヨ", "Kata [ 7]" },
    { 0x00E53B28, "๐", "ガ", "Kata [ 8]" },
    { 0x00E53B2C, "๑", "ギ", "Kata [ 9]" },
    { 0x00E53B30, "๒", "グ", "Kata [10]" },
    { 0x00E53B34, "๓", "ゲ", "Kata [11]" },
    { 0x00E53B58, "๔", "ゴ", "Kata [12]" },
    { 0x00E53B5C, "ึ", "カ", "Kata [13]" },
    { 0x00E53B60, "ื", "キ", "Kata [14]" },
    { 0x00E53B64, "ุ", "ク", "Kata [15]" },
    { 0x00E53B48, "ู", "ケ", "Kata [16]" },
    { 0x00E53B4C, "เ", "コ", "Kata [17]" },
    { 0x00E53B50, "3", "ラ", "Kata [18]" },
    { 0x00E53B54, "4", "リ", "Kata [19]" },
    { 0x00E53B78, "5", "ル", "Kata [20]" },
    { 0x00E53B7C, "6", "レ", "Kata [21]" },
    { 0x00E53B80, "7", "ロ", "Kata [22]" },
    { 0x00E53B84, "๕", "ザ", "Kata [23]" },
    { 0x00E53B68, "๖", "ジ", "Kata [24]" },
    { 0x00E53B6C, "๗", "ズ", "Kata [25]" },
    { 0x00E53B70, "๘", "ゼ", "Kata [26]" },
    { 0x00E53B74, "๙", "ゾ", "Kata [27]" },
    { 0x00E53B98, "แ", "サ", "Kata [28]" },
    { 0x00E53B9C, "โ", "シ", "Kata [29]" },
    { 0x00E53BA0, "ใ", "ス", "Kata [30]" },
    { 0x00E53BA4, "ไ", "セ", "Kata [31]" },
    { 0x00E53B88, "็", "ソ", "Kata [32]" },
    { 0x00E53B8C, "8", "ワ", "Kata [33]" },
    { 0x00E53B90, "9", "ヲ", "Kata [34]" },
    { 0x00E53B94, " ", "ン", "Kata [35]" },
    { 0x00E53BB8, "[", "ダ", "Kata [36]" },
    { 0x00E53BBC, "]", "ヂ", "Kata [37]" },
    { 0x00E53BC0, "{", "ヅ", "Kata [38]" },
    { 0x00E53BC4, "}", "デ", "Kata [39]" },
    { 0x00E53BA8, "<", "ド", "Kata [40]" },
    { 0x00E53BAC, "ั", "タ", "Kata [41]" },
    { 0x00E53BB0, "่", "チ", "Kata [42]" },
    { 0x00E53BB4, "้", "ツ", "Kata [43]" },
    { 0x00E53BD8, "๊", "テ", "Kata [44]" },
    { 0x00E53BDC, "๋", "ト", "Kata [45]" },
    { 0x00E53BE0, "+", "ァ", "Kata [46]" },
    { 0x00E53BE4, "-", "ィ", "Kata [47]" },
    { 0x00E53BC8, "*", "ゥ", "Kata [48]" },
    { 0x00E53BCC, "/", "ェ", "Kata [49]" },
    { 0x00E53BD0, "=", "ォ", "Kata [50]" },
    { 0x00E53BD4, ">", "バ", "Kata [51]" },
    { 0x00E53BF8, "\"", "ビ", "Kata [52]" },
    { 0x00E53BFC, "'", "ブ", "Kata [53]" },
    { 0x00E53C00, ":", "ベ", "Kata [54]" },
    { 0x00E53C04, ";", "ボ", "Kata [55]" },
    { 0x00E53BE8, "์", "ナ", "Kata [56]" },
    { 0x00E53BEC, "ๆ", "ニ", "Kata [57]" },
    { 0x00E53BF0, "ฯ", "ヌ", "Kata [58]" },
    { 0x00E53BF4, "ฺ", "ネ", "Kata [59]" },
    { 0x00E53C18, "ํ", "ノ", "Kata [60]" },
    { 0x00E53C1C, "%", "ャ", "Kata [61]" },
    { 0x00E53C20, "^", "ュ", "Kata [62]" },
    { 0x00E53C24, "&", "ョ", "Kata [63]" },
    { 0x00E53C08, "(", "ッ", "Kata [64]" },
    { 0x00E53C0C, ")", "ヮ", "Kata [65]" },
    { 0x00E53C10, "~", "パ", "Kata [66]" },
    { 0x00E53C14, "\\", "ピ", "Kata [67]" },
    { 0x00E53C38, "|", "プ", "Kata [68]" },
    { 0x00E53C3C, "_", "ペ", "Kata [69]" },
    { 0x00E53C40, "฿", "ポ", "Kata [70]" },
    { 0x00E53C44, "๎", "ハ", "Kata [71]" },
    { 0x00E53C28, "๏", "ヒ", "Kata [72]" },
    { 0x00E53C2C, "๚", "フ", "Kata [73]" },
    { 0x00E53C30, "๛", "ヘ", "Kata [74]" },
    { 0x00E53C34, "฿", "ホ", "Kata [75]" },
    { 0x00E53ACC, ",", "・", "Kata [76]" },
    { 0x00E53AD0, "-", "。", "Kata [77]" },
    { 0x00E53AD4, "!", "、", "Kata [78]" },
    { 0x00E53AF8, "?", "！", "Kata [79]" },
    { 0x00E53AFC, "/", "？", "Kata [80]" },
    { 0x00E53B00, "ー", "ー", "Kata [81]" },
    { 0x00E53B04, "～", "～", "Kata [82]" },
    { 0x00E53AE8, "＝", "＝", "Kata [83]" },
    { 0x00E53AEC, "♥", "♥", "Kata [84]" },
    { 0x00E53AF0, "★", "★", "Kata [85]" },
    { 0x00E53C58, "ฤ", "マ", "Kata [86]" },
    { 0x00E53C5C, "ฦ", "ミ", "Kata [87]" },
    { 0x00E53C60, ".", "ム", "Kata [88]" },
    { 0x00E53C64, ",", "メ", "Kata [89]" },
    { 0x00E53C48, "-", "モ", "Kata [90]" },
};
#define NUM_VIRTUAL_KEY_PATCHES (sizeof(g_virtual_key_patches) / sizeof(g_virtual_key_patches[0]))

#define KEYBOARD_SEARCH_RADIUS 0x800

static int keyboard_slot_equals(uintptr_t address, const char* text)
{
    size_t len = strlen(text);
    const uint8_t* slot = (const uint8_t*)address;
    return len == 3 && slot[3] == 0 && memcmp(slot, text, 3) == 0;
}

static int keyboard_is_first_orig(size_t index)
{
    for (size_t i = 0; i < index; i++) {
        if (strcmp(g_virtual_key_patches[i].orig, g_virtual_key_patches[index].orig) == 0) {
            return 0;
        }
    }
    return 1;
}

static size_t keyboard_unique_orig_count(void)
{
    size_t count = 0;
    for (size_t i = 0; i < NUM_VIRTUAL_KEY_PATCHES; i++) {
        if (keyboard_is_first_orig(i)) count++;
    }
    return count;
}

static size_t keyboard_find_slot_count(uintptr_t start, uintptr_t end,
                                       const char* orig, uintptr_t* first)
{
    size_t count = 0;
    uintptr_t p = (start + 3) & ~(uintptr_t)3;
    if (first) *first = 0;

    for (; p + 4 <= end; p += 4) {
        if (keyboard_slot_equals(p, orig)) {
            if (count == 0 && first) *first = p;
            count++;
        }
    }
    return count;
}

static size_t keyboard_score_window(uintptr_t start, uintptr_t end)
{
    size_t score = 0;
    for (size_t i = 0; i < NUM_VIRTUAL_KEY_PATCHES; i++) {
        if (!keyboard_is_first_orig(i)) continue;
        if (keyboard_find_slot_count(start, end, g_virtual_key_patches[i].orig, NULL) == 1) {
            score++;
        }
    }
    return score;
}

static int keyboard_locate_window(uintptr_t base, uintptr_t* out_start,
                                  uintptr_t* out_end, void (*log_fn)(const char*, ...))
{
    IMAGE_DOS_HEADER* dos = (IMAGE_DOS_HEADER*)base;
    if (dos->e_magic != IMAGE_DOS_SIGNATURE) return 0;

    IMAGE_NT_HEADERS* nt = (IMAGE_NT_HEADERS*)(base + dos->e_lfanew);
    if (nt->Signature != IMAGE_NT_SIGNATURE) return 0;

    IMAGE_SECTION_HEADER* sh = IMAGE_FIRST_SECTION(nt);
    size_t expected = keyboard_unique_orig_count();
    size_t best_score = 0;
    int best_ties = 0;
    uintptr_t best_start = 0;
    uintptr_t best_end = 0;

    for (WORD s = 0; s < nt->FileHeader.NumberOfSections; s++) {
        if (memcmp(sh[s].Name, ".rdata", 6) != 0) continue;

        uintptr_t sec_start = base + sh[s].VirtualAddress;
        size_t sec_size = sh[s].Misc.VirtualSize ? sh[s].Misc.VirtualSize : sh[s].SizeOfRawData;
        uintptr_t sec_end = sec_start + sec_size;
        uintptr_t p = (sec_start + 3) & ~(uintptr_t)3;

        /* "あ" is only a probe. Every mapped source glyph must still resolve
         * exactly once inside the selected window before any memory is changed.
         */
        for (; p + 4 <= sec_end; p += 4) {
            if (!keyboard_slot_equals(p, g_virtual_key_patches[0].orig)) continue;

            uintptr_t window_start = (p > sec_start + KEYBOARD_SEARCH_RADIUS)
                ? p - KEYBOARD_SEARCH_RADIUS : sec_start;
            uintptr_t window_end = (p + KEYBOARD_SEARCH_RADIUS < sec_end)
                ? p + KEYBOARD_SEARCH_RADIUS : sec_end;
            size_t score = keyboard_score_window(window_start, window_end);

            if (score > best_score) {
                best_score = score;
                best_ties = 1;
                best_start = window_start;
                best_end = window_end;
            } else if (score == best_score) {
                best_ties++;
            }
        }
        break;
    }

    if (best_score != expected || best_ties != 1) {
        if (log_fn) {
            log_fn("[KEYBOARD SCAN] Safe layout resolution failed (%d/%d glyphs, candidates=%d); keyboard patch skipped.",
                   (int)best_score, (int)expected, best_ties);
        }
        return 0;
    }

    *out_start = best_start;
    *out_end = best_end;
    if (log_fn) {
        log_fn("[KEYBOARD SCAN] Validated version-adaptive keyboard window (RVA 0x%X-0x%X, %d glyphs).",
               (unsigned int)(best_start - base), (unsigned int)(best_end - base), (int)expected);
    }
    return 1;
}

static void patch_virtual_keyboard_in_memory(uintptr_t base, void (*log_fn)(const char*, ...))
{
    uintptr_t window_start = 0;
    uintptr_t window_end = 0;
    uintptr_t resolved[NUM_VIRTUAL_KEY_PATCHES];
    uintptr_t patch_start = UINTPTR_MAX;
    uintptr_t patch_end = 0;

    if (!keyboard_locate_window(base, &window_start, &window_end, log_fn)) return;

    /* Resolve and validate the complete patch set before making .rdata writable. */
    for (size_t i = 0; i < NUM_VIRTUAL_KEY_PATCHES; i++) {
        uintptr_t address = 0;
        size_t matches = keyboard_find_slot_count(window_start, window_end,
                                                  g_virtual_key_patches[i].orig, &address);
        if (matches != 1 || strlen(g_virtual_key_patches[i].thai) > 3) {
            if (log_fn) {
                log_fn("[KEYBOARD PATCH] Validation failed for %s (matches=%d); no keyboard memory changed.",
                       g_virtual_key_patches[i].desc, (int)matches);
            }
            return;
        }

        resolved[i] = address;
        if (address < patch_start) patch_start = address;
        if (address + 4 > patch_end) patch_end = address + 4;
    }

    for (size_t i = 0; i < NUM_VIRTUAL_KEY_PATCHES; i++) {
        for (size_t j = 0; j < i; j++) {
            if (resolved[i] == resolved[j] &&
                strcmp(g_virtual_key_patches[i].thai, g_virtual_key_patches[j].thai) != 0) {
                if (log_fn) {
                    log_fn("[KEYBOARD PATCH] Conflicting replacement for %s; no keyboard memory changed.",
                           g_virtual_key_patches[i].orig);
                }
                return;
            }
        }
    }

    size_t patch_len = (size_t)(patch_end - patch_start);
    DWORD old_protect;

    if (VirtualProtect((LPVOID)patch_start, patch_len, PAGE_READWRITE, &old_protect)) {
        int count = 0;
        for (size_t i = 0; i < NUM_VIRTUAL_KEY_PATCHES; i++) {
            int already_written = 0;
            for (size_t j = 0; j < i; j++) {
                if (resolved[i] == resolved[j]) {
                    already_written = 1;
                    break;
                }
            }
            if (already_written) continue;

            char* dest = (char*)resolved[i];
            const char* src = g_virtual_key_patches[i].thai;
            size_t src_len = strlen(src);
            memset(dest, 0, 4);
            memcpy(dest, src, src_len);
            count++;
        }
        VirtualProtect((LPVOID)patch_start, patch_len, old_protect, &old_protect);
        if (log_fn) {
            log_fn("[KEYBOARD PATCH] Safely patched %d unique virtual keyboard glyphs to Thai.", count);
        }
    } else {
        if (log_fn) {
            log_fn("[KEYBOARD PATCH] ERROR: Failed to make validated keyboard memory writable at 0x%p.",
                   (void*)patch_start);
        }
    }
}
