# SPDX-License-Identifier: MIT
"""Lifetime of Python callbacks registered with add_event_cb.

A callback lives exactly as long as its registration: it is released when
the widget is deleted or the event is removed, and it keeps working while
the widget exists even if the application dropped the widget's Python
wrapper. The checks run in one subprocess under MALLOC_PERTURB_ so a
use-after-free in the release path shows up as a crash rather than luck.
"""

import json
import os
import subprocess
import sys
import unittest


_SCRIPT = r"""
import gc
import json
import sys
import weakref

import lvgl as lv

lv.init()
disp = lv.display_create(64, 64)
disp.set_color_format(lv.COLOR_FORMAT.RGB565)
buf = lv.draw_buf_create(64, 64, lv.COLOR_FORMAT.RGB565, 0)
disp.set_draw_buffers(buf, None)
disp.set_render_mode(lv.DISPLAY_RENDER_MODE.PARTIAL)

out = {}


class Handler:
    def __init__(self):
        self.calls = 0

    def __call__(self, e):
        self.calls += 1


def fresh_screen():
    scr = lv.obj(None)
    lv.screen_load(scr)
    return scr


# A. The widget is deleted and its wrapper dropped: the callback goes too.
scr = fresh_screen()
btn = lv.button(scr)
h = Handler()
ref = weakref.ref(h)
btn.add_event_cb(h, lv.EVENT.CLICKED, None)
del h
fresh_screen()
scr.delete()
del btn, scr
gc.collect()
out["deleted_widget_callback_alive"] = ref() is not None

# B. The widget is alive: the callback fires, and dropping the wrapper does
# not end it; a wrapper recreated from LVGL reaches the same registration.
scr = fresh_screen()
btn = lv.button(scr)
h = Handler()
ref = weakref.ref(h)
btn.add_event_cb(h, lv.EVENT.CLICKED, None)
del h
btn.send_event(lv.EVENT.CLICKED, None)
out["referenced_widget_calls"] = ref().calls if ref() else None
events_before = btn.get_event_count()
del btn
gc.collect()
out["live_widget_callback_alive_after_wrapper_dropped"] = ref() is not None
again = scr.get_child(0)
again.send_event(lv.EVENT.CLICKED, None)
out["live_widget_calls_after_wrapper_recreated"] = ref().calls if ref() else None
out["event_count_grew_on_wrapper_recreation"] = again.get_event_count() - events_before
fresh_screen()
scr.delete()
del scr, again
gc.collect()
out["live_widget_callback_alive_after_delete"] = ref() is not None

# C. A DELETE callback registered after the wrapper's own delete hook still
# runs during the delete, and is released afterwards.
scr = fresh_screen()
btn = lv.button(scr)
seen = []


def on_delete(e):
    seen.append(int(e.get_code()))


ref = weakref.ref(on_delete)
btn.add_event_cb(on_delete, lv.EVENT.DELETE, None)
del on_delete
fresh_screen()
scr.delete()
del btn, scr
gc.collect()
out["delete_callback_codes"] = seen
out["delete_callback_alive"] = ref() is not None

# D. A callback that deletes its own widget (a close button).
scr = fresh_screen()
btn = lv.button(scr)
done = []


class Closer:
    def __init__(self, scr):
        self.scr = scr

    def __call__(self, e):
        fresh_screen()
        self.scr.delete()
        done.append(True)


closer = Closer(scr)
ref = weakref.ref(closer)
btn.add_event_cb(closer, lv.EVENT.CLICKED, None)
del closer, scr
btn.send_event(lv.EVENT.CLICKED, None)
del btn
gc.collect()
out["closer_ran"] = len(done)
out["closer_alive"] = ref() is not None

# E. Removing the event releases the callback.
scr = fresh_screen()
btn = lv.button(scr)
h = Handler()
ref = weakref.ref(h)
btn.add_event_cb(h, lv.EVENT.CLICKED, None)
del h
btn.remove_event(btn.get_event_count() - 1)
gc.collect()
out["removed_callback_alive"] = ref() is not None
fresh_screen()
scr.delete()
del btn, scr

# F. A dict passed as user_data is held for the registration and let go
# when the widget is deleted.
d = {}
base = sys.getrefcount(d)
scr = fresh_screen()
btn = lv.button(scr)
btn.add_event_cb(Handler(), lv.EVENT.CLICKED, d)
out["user_dict_extra_refs_while_registered"] = sys.getrefcount(d) - base
fresh_screen()
scr.delete()
del btn, scr
gc.collect()
out["user_dict_extra_refs_after_delete"] = sys.getrefcount(d) - base

lv.deinit()
print(json.dumps(out))
"""


class CallbackLifetimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        env = dict(os.environ)
        env.setdefault("SDL_VIDEODRIVER", "dummy")
        env.setdefault("MALLOC_PERTURB_", "165")
        result = subprocess.run(
            [sys.executable, "-c", _SCRIPT],
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, "callback lifetime script failed (rc=%r); stdout=%r stderr=%r" % (
            result.returncode,
            result.stdout,
            result.stderr,
        )
        cls.out = json.loads(result.stdout.strip().splitlines()[-1])

    def test_callback_released_when_widget_deleted(self):
        self.assertFalse(self.out["deleted_widget_callback_alive"])

    def test_callback_fires_while_widget_referenced(self):
        self.assertEqual(self.out["referenced_widget_calls"], 1)

    def test_callback_outlives_a_dropped_wrapper_while_widget_lives(self):
        self.assertTrue(self.out["live_widget_callback_alive_after_wrapper_dropped"])
        self.assertEqual(self.out["live_widget_calls_after_wrapper_recreated"], 2)
        self.assertEqual(self.out["event_count_grew_on_wrapper_recreation"], 0)
        self.assertFalse(self.out["live_widget_callback_alive_after_delete"])

    def test_delete_callback_runs_then_is_released(self):
        import lvgl as lv

        self.assertEqual(self.out["delete_callback_codes"], [int(lv.EVENT.DELETE)])
        self.assertFalse(self.out["delete_callback_alive"])

    def test_callback_may_delete_its_own_widget(self):
        self.assertEqual(self.out["closer_ran"], 1)
        self.assertFalse(self.out["closer_alive"])

    def test_callback_released_when_event_removed(self):
        self.assertFalse(self.out["removed_callback_alive"])

    def test_user_data_dict_held_only_while_registered(self):
        self.assertEqual(self.out["user_dict_extra_refs_while_registered"], 1)
        self.assertEqual(self.out["user_dict_extra_refs_after_delete"], 0)


if __name__ == "__main__":
    unittest.main()
