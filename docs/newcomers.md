# Newcomer's guide to the lvgl-python codebase

`lvgl-python` packages LVGL for CPython as the native `lvgl` extension
distributed under the `pydevices-lvgl` project name. It is one endpoint of a
shared binding family: it exposes the same intentional Python-shaped API as
the MicroPython and CircuitPython targets, but it does **not** embed or run a
MicroPython interpreter.

The most important boundary is ownership. This repository owns the CPython
runtime layer, packaging, tests, and release policy. The sibling
`lvgl-bindings` repository owns the generator and canonical API decisions.
Generated binding files and the `display_driver.py`/`fs_driver.py` helpers are
vendored here at one exact upstream commit; they are inputs to this project,
not ordinary hand-edited source files.

## A mental model

```text
lvgl-bindings (generator and API policy)
        |
        | explicit sync at a recorded 40-character commit
        v
lvgl-python repository
  |-- generated/lvgl_python.c and lvgl.pyi      generated binding surface
  |-- src/lvpy_runtime.c                        CPython ownership, callbacks, locking
  |-- lvgl/                                     pinned upstream C submodule
  `-- setup.py                                  compiles one CPython extension
        |
        v
import lvgl as lv
  |-- generated wrappers convert Python arguments and results
  |-- runtime wrappers manage objects, structs, GIL, and callback lifetime
  `-- LVGL C core owns widgets, displays, rendering, and event dispatch
```

Most users install a prebuilt `pydevices-lvgl` wheel from TestPyPI, then use
`import lvgl as lv`; they do not clone this repository, initialize its
submodule, or compile LVGL. The build tree exists for binding/runtime
contributors and release automation, not as the normal application setup.

```bash
pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ pydevices-lvgl
```

An application may provide its own display backend. In the PyDevices
convenience path it imports `display_driver`, which is a synced adapter around
`appdev.App` and `board_config`; it is deliberately outside the core extension
and is not required for a standalone backend.

## Repository map

| Path | Purpose |
|---|---|
| `generated/lvgl_python.c` | Vendored generated Python-to-LVGL wrappers, types, constants, and callback entry points. |
| `generated/lvgl.pyi` | Type stubs installed beside the extension wheel. |
| `src/lvpy_runtime.c`, `src/lvpy_runtime.h` | Handwritten CPython-specific implementation: object/struct wrappers, conversion helpers, locking, GIL handling, and callback ownership. |
| `lvgl/` | Pinned upstream LVGL C git submodule compiled into the extension. |
| `lv_conf.h` | LVGL build configuration for the CPython target. |
| `setup.py` | Defines the `lvgl` extension and compiles runtime, generated bindings, and all LVGL C sources. |
| `display_driver.py`, `fs_driver.py` | Synced PyDevices helpers; change their canonical copies in `lvgl-bindings`. |
| `LVGL_BINDINGS_COMMIT` | Exact 40-character source commit used for the vendored binding inputs. |
| `tests/` | Native-extension lifecycle and wheel-installation contracts. |
| `docs/building.md` | Authoritative local build, sync, Android, and Pyodide instructions. |
| `docs/publishing.md` | Release safety model and platform-wheel policy. |
| `scripts/sync_from_lvgl_bindings.sh` | Explicit upstream sync tool; it records the resolved source and updates the submodule pin. |

## Follow a normal PyDevices application

The usual PyDevices entry point imports `display_driver` before `lvgl`. That
adapter selects the active board configuration and wires display flush, input,
and LVGL event-loop coordination; the application then creates widgets.

```python
import display_driver  # wires LVGL display, input, and event loop
import lvgl as lv

scr = lv.screen_active()
label = lv.label(scr)
label.set_text("Hello from PyDevices LVGL!")
label.center()
```

1. Installing the supported wheel provides the binary module named `lvgl` and
   the bundled `display_driver` helper.
2. Importing `display_driver` first establishes the PyDevices display/input
   integration. It owns LVGL ticking and refresh coordination for this path.
3. Importing `lvgl` exposes the generated module surface and runtime support
   types: LVGL-style enum namespaces, functions, object constructors, and
   struct methods rather than a separate Python UI model.
4. Widget constructors and methods enter generated wrappers. They validate and
   convert Python values, take the runtime's LVGL lock where needed, and call
   the corresponding LVGL C API.

For a custom backend without PyDevices board configuration, use the raw LVGL
setup in the root README instead of adapting this convenience-path example.

The public API is generated, but the lifecycle, ownership, and concurrency
behavior in that path are CPython runtime work. Those concerns belong in
`src/lvpy_runtime.*`, not in an ad hoc edit to the generated file.

## Boundaries and invariants

- Do not manually edit `generated/lvgl_python.c`, `generated/lvgl.pyi`,
  `display_driver.py`, `fs_driver.py`, or `lv_conf.h`. Change the generator or
  canonical helper in `lvgl-bindings`, regenerate there, then use the explicit
  sync workflow here.
- `LVGL_BINDINGS_COMMIT` is a reproducible-source record, not a loose version
  hint. A sync accepts an immutable full commit SHA or release tag and records
  the resolved 40-character commit.
- Keep a Python reference to any widget that owns callbacks for as long as
  LVGL may call them. With `user_data=None`, callback state is retained on the
  wrapper, but an application that drops the widget can still lose the Python
  object it needs.
- Pair `lv.init()` and `lv.deinit()` in standalone programs. Tests cover this
  lifecycle, including callback cleanup during interpreter shutdown.
- The binding intentionally omits unsafe C signatures such as unbounded
  pointer-to-pointer or variadic APIs unless conversion is reviewed. Do not
  restore one merely to make the C surface look complete.
- The project shares naming and selected API policy with other runtimes, but
  it is a CPython extension. A feature's availability may be explicitly
  different on another target.
- The extension does not choose a display, event loop, or board. Treat the
  PyDevices `display_driver` path as one integration, not as a requirement of
  `import lvgl`.

## When you need the source tree

Only work on a source checkout when you are changing the generated binding,
the CPython runtime, packaging, or the release process. In that case,
[building.md](building.md) is the authoritative platform-specific build and
test guide; it covers the LVGL submodule and editable native build. It is not
needed to use a published wheel.

The focused test suite verifies the recorded bindings source, the installed
`lvgl.pyi` stub, initialization/deinitialization, widget creation, and
teardown callbacks at interpreter exit. Read [publishing.md](publishing.md)
before changing sync, version, wheel-matrix, or TestPyPI release behavior:
normal pushes do not publish a wheel.

## Safe first contributions

Good first changes are a focused regression test for a CPython lifecycle or
conversion bug, a clarification in the build documentation, or a fix to the
handwritten runtime layer when the generated API already expresses the desired
surface. Confirm which repository owns the change before editing:

| If the change concerns… | Start in… |
|---|---|
| API availability, generated wrappers, or synced Python helpers | `lvgl-bindings` |
| CPython object ownership, GIL/lock behavior, wheel packaging, or CPython tests | `lvgl-python` |
| A PyDevices application's screens, board configuration, or user interaction | that consuming application/repository |

After changing any native code, rebuild the editable extension and run the
focused tests. If a proposed change moves generated files or the `lvgl`
submodule, use the documented sync path rather than staging a hand-picked
mixture of outputs.

## Where to learn next

Read `src/lvpy_runtime.h` first, then follow one call from `import lvgl` into
`generated/lvgl_python.c` and back through `src/lvpy_runtime.c`.
`tests/test_lvgl_init.py` is short and shows the lifecycle contract the runtime
has to keep.

For the user-facing surface, both setup paths are in the
[README](../README.md#usage). For how the binding is generated and which API
decisions it makes, go to
[lvgl-bindings](https://github.com/PyDevices/lvgl-bindings). Building from
source is in [building.md](building.md), and releases are in
[publishing.md](publishing.md).
