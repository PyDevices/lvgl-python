# Contributing to lvgl-python

lvgl-python owns the CPython runtime layer, the packaging, the tests and the
release policy. lvgl-bindings owns the generator and the API decisions. The
generated bindings and the `fs_driver.py` helper are vendored here at one exact
bindings commit: they are inputs, not hand-edited source.

| If the change concerns... | Start in... |
|---|---|
| API availability, generated wrappers, or the synced Python helpers | [lvgl-bindings](https://github.com/PyDevices/lvgl-bindings) |
| CPython object ownership, GIL or lock behavior, wheel packaging, CPython tests | this repository |
| A program's screens, board configuration or user interaction | the application's own repository |

Good first changes are a focused regression test for a lifecycle or conversion
bug, a fix to the docs, or a fix to the handwritten runtime when the generated
API already offers the surface you want. The docs for this package live with
[lvgl-bindings](https://github.com/PyDevices/lvgl-bindings/tree/main/docs), and
the [docs site](https://github.com/PyDevices/lvgl-bindings/blob/main/docs/index.md) is built from there.

## Where things are

```text
lvgl-python/
  LVGL_BINDINGS_COMMIT       exact source of the vendored bindings
  JPEGIO_COMMIT              exact source of src/jpegio/
  generated/lvgl_python.c    vendored binding, synced from lvgl-bindings
  generated/lvgl.pyi         type stubs, copied into the install
  lv_conf.h                  LVGL config for the build
  fs_driver.py               optional helper (import fs_driver)
  lvgl/                      LVGL C sources (git submodule)
  src/lvpy_runtime.c, .h     CPython glue: wrappers, converters, locking, the GIL
  src/lvpy_jpegio.c          registers the JPEG decoder at lv.init()
  src/jpegio/                jpegio's LVGL decoder and TJpgDec (synced)
  tests/                     unit tests
  scripts/                   sync, version and wheel scripts
  setup.py                   builds the one extension module
```

| Component | Role |
|-----------|------|
| [`generated/lvgl_python.c`](generated/lvgl_python.c) | Types, methods, module functions and callbacks |
| [`src/lvpy_runtime.c`](src/lvpy_runtime.c), [`src/lvpy_runtime.h`](src/lvpy_runtime.h) | Object wrappers (`py_lv_obj_t` maps an `lv_obj_t *` to Python and keeps its callback dicts), struct wrappers (`py_lv_struct_t`), conversion helpers, locking, GIL handling and callback ownership |
| `setup.py` | Defines the `lvgl` extension and compiles the runtime, the generated binding and all the LVGL C sources |
| `lvgl-bindings` | The generator, not needed to compile |

Do not edit `generated/lvgl_python.c`, [`generated/lvgl.pyi`](generated/lvgl.pyi), `fs_driver.py` or
`lv_conf.h` here. Change the generator or the canonical helper in
lvgl-bindings, regenerate there, and sync. Read `src/lvpy_runtime.h` first, then
follow one call from `import lvgl` into `generated/lvgl_python.c` and back
through `src/lvpy_runtime.c`; [`tests/test_lvgl_init.py`](tests/test_lvgl_init.py) is short and shows the
lifecycle contract the runtime has to keep.

## Build and test

You need only this clone and its `lvgl` submodule: [Build lvgl-python from source](https://github.com/PyDevices/lvgl-bindings/blob/main/docs/guides/build-lvgl-python-from-source.md)
has the toolchain and the editable install. Then:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

The tests cover the recorded bindings source, the installed `lvgl.pyi` stub,
initialization and deinitialization, widget creation, callback lifetime
([`tests/test_callback_lifetime.py`](tests/test_callback_lifetime.py), [`tests/test_struct_callback_lifetime.py`](tests/test_struct_callback_lifetime.py))
and teardown at interpreter exit. After changing native code
(`src/lvpy_runtime.c` or `generated/lvgl_python.c`), reinstall the editable
build before you test: an editable install doesn't recompile on import.

## Sync from lvgl-bindings

The vendored files track the latest synced lvgl-bindings commit. A normal
`pip install -e .` compiles them, so you don't need a lvgl-bindings clone to
build or test.

Clone [lvgl-bindings](https://github.com/PyDevices/lvgl-bindings) as a sibling
only to change the generator or regenerate bindings: to edit the model or the
CPython emitter in `binding/`, to run `./regenerate_all.sh --target cpython`,
or to run the shared smoke script `tools/test_lvgl_smoke.py`. To refresh the
vendored files, without a sibling clone, from an exact commit or a release tag:

```bash
./scripts/sync_from_lvgl_bindings.sh --ref <40-character-commit-sha>
./scripts/sync_from_lvgl_bindings.sh --ref v9.5.N
```

The script clones lvgl-bindings into a temporary directory, copies the
generated files, and updates the `lvgl` submodule pin. The JPEG decoder comes
the same way from
[micropython-pydevices](https://github.com/PyDevices/micropython-pydevices)'s
`modules/jpegio`, so a JPEG draws the same on every interpreter:

```bash
./scripts/sync_from_jpegio.sh --ref <40-character-commit-sha>
```

To change API coverage, regenerate in a lvgl-bindings clone, commit that
source, sync its exact SHA, and reinstall:

```bash
cd ../lvgl-bindings && ./regenerate_all.sh --target cpython
cd ../lvgl-python
./scripts/sync_from_lvgl_bindings.sh --ref <40-character-commit-sha>
.venv/bin/pip install -e .
```

## Releases

`lvgl-python` is the packaged CPython endpoint for the API lvgl-bindings
generates. Release inputs are immutable: every sync takes a full 40-character
bindings commit or a `vX.Y.Z` bindings tag and records the resolved commit in
`LVGL_BINDINGS_COMMIT`.

Generation, validation, synchronization and publication are separate actions:

- `lvgl-bindings/regenerate_all.sh` writes artifacts only.
- `lvgl-bindings/scripts/release_dry_run.sh` generates into temporary storage,
  verifies every artifact, runs the tests and computes the expected version,
  without committing, tagging, pushing, dispatching or publishing.
- This repository's **Sync and release** workflow defaults to `dry-run`.
  `sync` mode commits and pushes the synchronized sources. `release` mode
  commits, creates a GitHub Release and starts package publication.
- A normal push to either repository never starts a release.

### Version

Versions are `LVGL_MAJOR.LVGL_MINOR.N`, so the current line is `9.5.N`. `N` is
one greater than the highest existing `v9.5.*` tag here. Preview it without
changing anything:

```bash
./scripts/next_release_version.sh --verbose
```

### Dry run locally

Sync an exact bindings source, rebuild the extension, run its tests and the
matching canonical smoke suite, then look at the next version:

```bash
./scripts/sync_from_lvgl_bindings.sh --ref <40-character-bindings-sha>
python -m pip install -e .
python -m unittest discover -s tests -v
python ../lvgl-bindings/tools/test_lvgl_smoke.py
./scripts/next_release_version.sh --verbose
```

The sync changes only the local checkout: the vendored `generated/lvgl_python.c`,
`generated/lvgl.pyi`, `lv_conf.h`, the Python helpers, the LVGL submodule pin
and `LVGL_BINDINGS_COMMIT`.

### Run the workflow

Run **Sync and release** with two inputs: `lvgl_bindings_ref` (an exact full SHA
or a `vX.Y.Z` tag) and `mode` (`dry-run`, `sync` or `release`).

```bash
# Validate only; nothing external changes.
gh workflow run sync-and-release.yml --repo PyDevices/lvgl-python \
  -f lvgl_bindings_ref=<40-character-bindings-sha> -f mode=dry-run

# Commit and push the exact sync, without a release.
gh workflow run sync-and-release.yml --repo PyDevices/lvgl-python \
  -f lvgl_bindings_ref=<40-character-bindings-sha> -f mode=sync

# Commit, create a GitHub Release and publish the packages.
gh workflow run sync-and-release.yml --repo PyDevices/lvgl-python \
  -f lvgl_bindings_ref=<40-character-bindings-sha> -f mode=release
```

The **Release bindings** workflow in lvgl-bindings is the coordinated entry
point. It validates the exact source first and dispatches `mode=release` only
when its `publish` input is turned on.

### Package matrix

The release workflow uses the PyDevices reusable native and WebAssembly package
builder, and `pyproject.toml` keeps the platform policy:

- CPython 3.11 to 3.15 and free-threaded 3.15t, Linux x86_64 manylinux wheels.
- CPython 3.11 to 3.15 and free-threaded 3.15t, Windows AMD64 wheels.
- CPython 3.13 and 3.14, Android arm64-v8a and x86_64 wheels.
- Pyodide and WebAssembly wheels from the reusable release workflow.

Native wheel smoke tests import `lvgl`, call `init()` and call `deinit()`.
Android wheels are cross-built and checked on a device by the PyDevices Android
application workflow.

### Check a wheel locally

```bash
python -m pip install build
python -m build --wheel
python -m pip install --force-reinstall dist/pydevices_lvgl-*.whl
python -m unittest discover -s tests -v
```

The wheel must contain `lvgl.pyi` beside the native extension; the tests verify
the install. To reproduce the release platforms, use cibuildwheel: Linux
manylinux builds need Docker, Windows builds need native MSVC, and Android
builds need the Android SDK and NDK that cibuildwheel uses.

### Where publication stops

Only a published GitHub Release, or an explicit exact-tag retry, runs
`publish-release-packages.yml`. Implementation and dry-run validation create no
GitHub Release, so they cannot upload to TestPyPI.
