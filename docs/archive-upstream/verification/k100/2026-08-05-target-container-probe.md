# K100 Target Container Probe - 2026-08-05

## Scope

- Host context: commercial K100 test machine.
- Container: `model_test`.
- Base image tag reported by user: `2.7.1-ubuntu22.04-dtk26.04-py3.11`.
- Purpose: identify runtime ABI for MolP-PC binary delivery and model compatibility testing.

## Probe Output

```text
PRETTY_NAME="Ubuntu 22.04.5 LTS"
NAME="Ubuntu"
VERSION_ID="22.04"
VERSION="22.04.5 LTS (Jammy Jellyfish)"
VERSION_CODENAME=jammy
ID=ubuntu
ID_LIKE=debian
HOME_URL="https://www.ubuntu.com/"
SUPPORT_URL="https://help.ubuntu.com/"
BUG_REPORT_URL="https://bugs.launchpad.net/ubuntu/"
PRIVACY_POLICY_URL="https://www.ubuntu.com/legal/terms-and-policies/privacy-policy"
UBUNTU_CODENAME=jammy
x86_64
Python 3.11.9
executable = /usr/local/bin/python
version = 3.11.9 (main, Apr  5 2026, 19:32:29) [GCC 11.4.0]
platform = Linux-4.19.90-89.11.v2401.ky10.x86_64-x86_64-with-glibc2.35
SOABI = cpython-311-x86_64-linux-gnu
EXT_SUFFIX = .cpython-311-x86_64-linux-gnu.so
numpy FOUND
pandas FOUND
scipy FOUND
sklearn missing
torch FOUND
dgl missing
rdkit missing
onnxruntime FOUND
/usr/bin/gcc
gcc (Ubuntu 11.4.0-1ubuntu1~22.04.3) 11.4.0
ldd (Ubuntu GLIBC 2.35-0ubuntu3.8) 2.35
```

## Dependency Import Probe

Additional package-version probing failed while importing `torch`:

```text
python 3.11.9 (main, Apr  5 2026, 19:32:29) [GCC 11.4.0]
numpy 1.25.0
pandas 2.3.3
scipy 1.15.3
Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "<string>", line 1, in <listcomp>
  File "/usr/local/lib/python3.11/importlib/__init__.py", line 126, in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
  File "<frozen importlib._bootstrap>", line 1204, in _gcd_import
  File "<frozen importlib._bootstrap>", line 1176, in _find_and_load
  File "<frozen importlib._bootstrap>", line 1147, in _find_and_load_unlocked
  File "<frozen importlib._bootstrap>", line 690, in _load_unlocked
  File "<frozen importlib._bootstrap_external>", line 940, in exec_module
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "/usr/local/lib/python3.11/site-packages/torch/__init__.py", line 410, in <module>
    from torch._C import *  # noqa: F403
ImportError: librocm_smi64.so.2: cannot open shared object file: No such file or directory
```

The missing library does exist in the container filesystem:

```text
/opt/dtk-26.04/.hyhal/rocm_smi/lib/librocm_smi64.so
/opt/dtk-26.04/.hyhal/rocm_smi/lib/librocm_smi64.so.2
/opt/dtk-26.04/.hyhal/rocm_smi/lib/librocm_smi64.so.2.8
```

## Interpretation

- Compiled Python extensions for the commercial container must target
  `cpython-311-x86_64-linux-gnu` and produce files ending in
  `.cpython-311-x86_64-linux-gnu.so`.
- The container uses Ubuntu 22.04 userland with glibc 2.35 and GCC 11.4.0, running
  on a Kylin kernel.
- The first probe used `importlib.util.find_spec`, so `torch FOUND` only means a
  package path exists. A real import currently fails because `librocm_smi64.so.2`
  is missing from the dynamic linker path or the container filesystem.
- The base Python runtime can import `numpy`, `pandas`, and `scipy`; `torch` is
  not yet usable until the ROCm/DTK runtime library issue is resolved.
- `librocm_smi64.so.2` is present under `/opt/dtk-26.04/.hyhal/rocm_smi/lib`, so
  the most likely next hypothesis is a missing `LD_LIBRARY_PATH` or linker cache
  entry rather than a missing runtime package.
- `scikit-learn`, `dgl`, and `rdkit` are not currently importable. MolP-PC needs
  `scikit-learn`; other models may need `dgl` or chemistry packages.
- Existing cp38/cp310 binary wheels from the 4090 environment cannot be reused as
  Python extension modules in this py3.11 container. They can only be used as
  dependency references or for an internal legacy-env probe.

## Next Actions

1. Retry `torch` import with `/opt/dtk-26.04/.hyhal/rocm_smi/lib` prepended to
   `LD_LIBRARY_PATH`.
2. If another DTK/ROCm library fails next, collect the missing library name and
   locate it with `find / -name '<library>'`.
3. Probe exact installed package metadata without importing `torch`.
4. Decide whether to run MolP-PC legacy cp38 environment as a temporary internal
   compatibility probe.
5. Build MolP-PC binary delivery against this ABI in a trusted builder based on
   `2.7.1-ubuntu22.04-dtk26.04-py3.11`.
