# K100 Target Container Probe Template

Use this probe before uploading any model source or binary bundle to a K100 test
container. The probe records the ABI that compiled Python extensions must match.

```bash
docker exec -it <container> bash -lc '
set -euo pipefail
cat /etc/os-release
uname -m
python -V
python - <<"PY"
import sys, sysconfig, platform, importlib.util
print("executable =", sys.executable)
print("version =", sys.version)
print("platform =", platform.platform())
print("SOABI =", sysconfig.get_config_var("SOABI"))
print("EXT_SUFFIX =", sysconfig.get_config_var("EXT_SUFFIX"))
for name in ["numpy", "pandas", "scipy", "sklearn", "torch", "dgl", "rdkit", "onnxruntime"]:
    print(name, "FOUND" if importlib.util.find_spec(name) else "missing")
PY
command -v gcc && gcc --version | head -1 || true
ldd --version | head -1
find /usr /opt -maxdepth 3 -iname "*dtk*" -o -iname "*k100*" 2>/dev/null | head -80 || true
'
```

Record the output under `docs/verification/k100/YYYY-MM-DD-target-container-probe.md`.

