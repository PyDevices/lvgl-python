# SPDX-License-Identifier: MIT
"""lvgl on a free-threaded Python (3.13t and later).

- Importing lvgl leaves the GIL off. An extension that doesn't declare
  itself GIL-free turns the GIL back on for the whole process.
- With LVGL driven from one thread while other threads run Python (none of
  them touching LVGL), every frame LVGL draws is byte for byte the frame it
  draws with no other threads running.

Skipped on builds with a GIL.
"""

import json
import os
import subprocess
import sys
import sysconfig
import unittest


FREE_THREADED = bool(sysconfig.get_config_var("Py_GIL_DISABLED"))

_SCRIPT = r"""
import hashlib
import json
import sys
import threading

import lvgl as lv

out = {"gil_enabled_after_import": sys._is_gil_enabled()}

W, H = 160, 120
FRAMES = 200
WORKERS = int(sys.argv[1])

lv.init()
disp = lv.display_create(W, H)
disp.set_color_format(lv.COLOR_FORMAT.RGB565)
draw_buf = lv.draw_buf_create(W, H, lv.COLOR_FORMAT.RGB565, 0)
disp.set_draw_buffers(draw_buf, None)
disp.set_render_mode(lv.DISPLAY_RENDER_MODE.FULL)
frame = hashlib.sha256()

def flush(d, area, px_map):
    frame.update(px_map.__dereference__(W * H * 2))
    d.flush_ready()

disp.set_flush_cb(flush)

scr = lv.screen_active()
label = lv.label(scr)
label.align(lv.ALIGN.TOP_LEFT, 4, 4)
arc = lv.arc(scr)
arc.set_size(80, 80)
arc.align(lv.ALIGN.CENTER, 0, 10)
bar = lv.bar(scr)
bar.set_size(140, 10)
bar.align(lv.ALIGN.BOTTOM_MID, 0, -4)


def draw_all():
    global frame
    digests = []
    for i in range(FRAMES):
        label.set_text("frame %d" % i)
        arc.set_value(i % 100)
        bar.set_value((i * 7) % 100, 0)  # no animation
        frame = hashlib.sha256()
        scr.invalidate()
        lv.refr_now(disp)
        digests.append(frame.hexdigest())
    return digests


solo = draw_all()

stop = threading.Event()
spins = [0] * WORKERS

def work(n):
    # Plain Python only: allocation, dicts, strings, arithmetic.
    while not stop.is_set():
        d = {str(k): [k] * 8 for k in range(200)}
        s = sum(len(v) for v in d.values())
        spins[n] += s > 0

threads = [threading.Thread(target=work, args=(n,)) for n in range(WORKERS)]
for t in threads:
    t.start()
try:
    busy = [draw_all() for _ in range(3)]
finally:
    stop.set()
    for t in threads:
        t.join()

out["frames"] = len(solo)
out["distinct_solo_frames"] = len(set(solo))
out["rounds_matching_solo"] = sum(b == solo for b in busy)
out["workers_ran"] = all(spins)
out["gil_enabled_at_end"] = sys._is_gil_enabled()
lv.deinit()
print("RESULT " + json.dumps(out))
"""


def _run(workers):
    env = dict(os.environ)
    env.pop("PYTHON_GIL", None)  # let the module's declaration decide
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT, str(workers)],
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )
    for line in proc.stdout.splitlines():
        if line.startswith("RESULT "):
            return proc, json.loads(line[len("RESULT "):])
    return proc, None


@unittest.skipUnless(FREE_THREADED, "needs a free-threaded build")
class FreeThreadingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proc, cls.out = _run(workers=max(2, min(8, (os.cpu_count() or 2) - 1)))

    def setUp(self):
        if self.out is None:
            self.fail(
                "script did not finish (exit %s)\nstdout:\n%s\nstderr:\n%s"
                % (self.proc.returncode, self.proc.stdout, self.proc.stderr)
            )

    def test_import_leaves_the_gil_off(self):
        self.assertIs(self.out["gil_enabled_after_import"], False)
        self.assertIs(self.out["gil_enabled_at_end"], False)

    def test_frames_match_drawing_alone(self):
        self.assertTrue(self.out["workers_ran"])
        # The scene changes every frame, so a stuck or blank frame shows.
        self.assertEqual(self.out["distinct_solo_frames"], self.out["frames"])
        self.assertEqual(self.out["rounds_matching_solo"], 3)


if __name__ == "__main__":
    unittest.main()
