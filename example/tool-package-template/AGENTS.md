# Tool Package Authoring Rules

These rules apply to coding agents modifying this package.

1. Keep `api_version: aidd.sciminer/tool-package.v2`; new tools must use standard
   Artifact contracts, not legacy semantic mappings.
2. Never embed credentials, access tokens, private addresses, or absolute host
   paths. Consume deployment-specific values through platform-managed settings.
3. Keep CPU, NVIDIA CUDA, and Hygon DCU variants on one standard input/output
   contract. Hardware-specific optimization must not alter Artifact meaning.
4. Mark hardware as `validated` only after its contract and golden sample pass on
   that hardware. Use `adapted_pending_hardware_validation` for adapted but
   unavailable hardware.
5. Declare NVIDIA device and minimum driver requirements. Keep Hygon DCU device and
   driver requirements explicit without claiming completed hardware validation.
6. Keep `runner/entrypoint.sh` as a thin delegate to the model-side
   `platform_run.sh`; do not put model adapters or legacy inference here.
7. Add or update contract tests, `README.md`, `LICENSE`, and the golden sample's
   source, license, SHA-256, preprocessing rules, and numeric tolerances with every
   generated package.
8. Run `python -m app.tool_packages.validator <package-path>` and the package-local
   tests before handing off changes.
