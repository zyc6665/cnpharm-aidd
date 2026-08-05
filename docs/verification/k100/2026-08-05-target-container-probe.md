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

## Interpretation

- Compiled Python extensions for the commercial container must target
  `cpython-311-x86_64-linux-gnu` and produce files ending in
  `.cpython-311-x86_64-linux-gnu.so`.
- The container uses Ubuntu 22.04 userland with glibc 2.35 and GCC 11.4.0, running
  on a Kylin kernel.
- The base Python runtime already has `numpy`, `pandas`, `scipy`, `torch`, and
  `onnxruntime` importable.
- `scikit-learn`, `dgl`, and `rdkit` are not currently importable. MolP-PC needs
  `scikit-learn`; other models may need `dgl` or chemistry packages.
- Existing cp38/cp310 binary wheels from the 4090 environment cannot be reused as
  Python extension modules in this py3.11 container. They can only be used as
  dependency references or for an internal legacy-env probe.

## Next Actions

1. Probe exact package versions inside `model_test`, especially `torch` and
   `onnxruntime`.
2. Decide whether to run MolP-PC legacy cp38 environment as a temporary internal
   compatibility probe.
3. Build MolP-PC binary delivery against this ABI in a trusted builder based on
   `2.7.1-ubuntu22.04-dtk26.04-py3.11`.
