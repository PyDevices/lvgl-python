// The JPEG decoder for LVGL on CPython: jpegio's, the same one MicroPython and
// CircuitPython use, synced from micropython-pydevices at JPEGIO_COMMIT
// (scripts/sync_from_jpegio.sh). It decodes the whole image when it opens, so
// LVGL can scale, rotate and CONTAIN a JPEG; LVGL's own TJPGD decodes tiles
// and can't. lv.init() calls this right after lv_init(), through the
// LVPY_AFTER_LV_INIT hook in the generated module (setup.py defines it).

#include "jpegio/lvgl_decoder.h"

void lvpy_register_jpegio(void) {
    (void)jpegio_lvgl_decoder_register();
}
