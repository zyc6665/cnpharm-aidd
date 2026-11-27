#!/usr/bin/env python3
"""GROMACS ligand parameterisation (offline): Mode 0 custom bundle, Mode 1 acpype/GAFF2.
External tools are injected; RDKit is imported only on the execution path."""
from __future__ import annotations
import math
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
ALLOWED_CHARGE_METHODS = ("bcc", "gas")
DEFAULT_LIGAND_RESNAME = "LIG"
MAX_ZIP_FILES = 32
MAX_ZIP_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
STANDARD_AMINO_ACIDS = frozenset(
    "ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL".split())
RESERVED_RESNAMES = STANDARD_AMINO_ACIDS | frozenset((
    "00C 01W 02K 02L 03Y 07O 08P 0A0 0A1 0A2 0A8 0AA 0AB 0AC 0AF 0AG 0AH 0AK 0BN 0CS 0E5 0EA 0FL 0NC 0WZ 0Y8 143 193 "
    "1OP 1PA 1PI 1TQ 1TY 1X6 200 23F 23S 26B 2AD 2AG 2AO 2AS 2CO 2DO 2FM 2HF 2KK 2KP 2LU 2ML 2MR 2MT 2OR 2PI 2QZ 2R3 "
    "2SI 2TL 2TY 2VA 2XA 32S 32T 33X 3AH 3AR 3CF 3GA 3MD 3NF 3QN 3TY 3XH 4BF 4CF 4CY 4DP 4FB 4FW 4HT 4IN 4MM 4PH 4U7 "
    "56A 5AB 5CS 5CW 5HP 6CL 6CW 6GL 6HN 7JA 9NE 9NF 9NR 9NV A5N A66 AA3 AA4 AAR AB7 ABA ACB ACE ACL ADD AEA AEI AFA "
    "AGM AGT AHB AHH AHO AHP AHS AHT AIB AKL AKZ ALC ALM ALN ALO ALS ALT ALV ALY AN8 APE APH API APK APM APP AR2 AR4 "
    "AR7 ARM ARN ARO ARV AS2 AS9 ASA ASB ASF ASH ASI ASK ASL ASM ASQ ASX AVN AYA AZK AZS AZY B1F B2A B2F B2I B2V B3A "
    "B3D B3E B3K B3L B3M B3Q B3S B3T B3U B3X B3Y BB6 BB7 BB8 BB9 BBC BCS BE2 BFD BG1 BH2 BHD BIF BIL BIU BJH BL2 BLE "
    "BLY BMT BNN BNO BOR BPE BSE BTA BTC BTR BUC BUG C1X C22 C3Y C4R C5C C66 C6C CA CAF CAL CAS CAV CAY CCL CCS CDE "
    "CDV CEA CGA CGU CHF CHG CHP CHS CIR CL CLE CLG CLH CME CMH CML CMT CPC CPI CR5 CS0 CS1 CS3 CS4 CSA CSB CSD CSE "
    "CSJ CSO CSP CSR CSS CSU CSW CSX CSZ CTE CTH CUC CWR CXM CY0 CY1 CY3 CY4 CYA CYD CYF CYG CYJ CYM CYN CYQ CYR CYX "
    "CZ2 CZZ D11 D3P D4P DA2 DAB DAH DAL DAR DAS DBB DBS DBU DBY DBZ DC2 DCL DCY DDE DFI DFO DGH DGL DGN DHA DHI DHL "
    "DHN DHP DHV DI7 DIL DIR DIV DLE DLS DLY DM0 DMH DMK DMT DNE DNL DNP DNS DOA DOD DOH DON DPL DPN DPP DPQ DPR DSE "
    "DSG DSN DSP DTH DTR DTY DVA DYS ECC EFC EHP ESB ESC EXY EYS F2F FAK FB5 FB6 FCL FE FGA FGL FGP FH7 FHL FHO FLA "
    "FLE FLT FME FOE FOR FP9 FRD FT6 FTR FTY FVA FZN GAU GCM GFT GGL GHG GHP GL3 GLH GLJ GLK GLM GLQ GLX GLZ GMA GND "
    "GPL GSC GSU GT9 GVL H14 H20 H2O H5M HAC HAR HBN HCS HFA HGL HHI HHO HIA HIC HID HIE HIH HIP HIQ HL2 HLU HMR HOH "
    "HPC HPE HPH HPQ HQA HRG HRP HS8 HS9 HSD HSE HSH HSL HSO HSP HTI HTN HTR HV5 HVA HY3 HYP HZP I2M I58 IAM IAR IAS "
    "IEL IGL IIL ILG ILX IML IOY IPG IT1 IYR IYT IZO JJJ JJK JJL K K1R KCX KGC KNB KOR KPI KST KYN KYQ L2A LA2 LAA "
    "LAL LBY LCK LCX LCZ LDH LED LEF LEH LEI LEM LEN LET LEX LHC LLP LLY LME LMF LMQ LP6 LPD LPG LPL LPS LSO LTA LTR "
    "LVG LVN LYF LYK LYM LYN LYR LYX LYZ M0H M2L M2S M30 M3L MA MAA MAI MBQ MC1 MCG MCL MCS MD3 MD6 MDF MDH MEA MED "
    "MEG MEN MEQ MEU MF3 MG MGG MGN MGY MHL MHO MHS MIS MK8 ML3 MLE MLL MLY MLZ MME MMO MND MNL MNV MOD MP8 MPH MPJ "
    "MPQ MSA MSE MSL MSO MSP MT2 MTY MVA N10 N2C N7P N80 N8P NA NA8 NAL NAM NB8 NBQ NC1 NCB NCY NDF NEM NEP NFA NH2 "
    "NHL NIY NLE NLN NLO NLP NLQ NMA NMC NME NMM NNH NPH NPI NSK NTR NTY NVA NYS NZH O12 OAR OAS OBF OBS OCS OCY OH2 "
    "OHH OHI OHS OIC OLE OLT OLZ OMT ONH ONL OPR ORN ORQ OSE OTB OTH OXX P1L P2Y PAQ PAS PAT PAU PBB PBF PCA PCC PCE "
    "PCS PDL PEC PF5 PFF PFX PG1 PG9 PGL PGY PH6 PHA PHD PHI PHL PHM PIV PLE PM3 POM PPN PR3 PR9 PRS PSA PSH PTA PTH "
    "PTM PTR PVH PVL PYA PYL PYX QCS QLN QMM QPA QPH R1A R4K RE0 RE3 RON RVX RZ4 S1H S2C S2D S2P SAC SAH SAR SBL SCH "
    "SCS SCY SD2 SDP SE7 SEB SEC SEG SEL SEM SEN SEP SET SGB SHC SHP SHR SIB SLR SLZ SMC SME SMF SNC SNN SOC SOL SOY "
    "SPC SRZ STY SUB SUN SVA SVV SVW SVX SVY SVZ SYS T11 T3P T4P T5P T66 TA4 TAV TBG TBM TCQ TCR TDD TFQ TH6 THC THO "
    "THZ TIH TIP TMB TMD TNB TNR TOQ TPH TPL TPO TPQ TQI TQQ TRF TRG TRN TRO TRQ TRW TRX TRY TST TTQ TTS TXY TY1 TY2 "
    "TY3 TY5 TYB TYI TYJ TYN TYO TYQ TYS TYT TYW TYX TYY TZB TZO UMA UN1 UN2 UNK VAD VAF VB1 VDL VLL VLM VMS VOL WAT "
    "WLU WPA WRP WVL X2W XCN XCP XDT XPL XPR XSN XX1 YCM YOF YTH Z01 ZAL ZCL ZFB ZN ZU0 ZZJ").split())
_GLOBAL_SECTIONS = frozenset("atomtypes bondtypes pairtypes angletypes dihedraltypes constrainttypes "
                             "nonbond_params implicit_genborn_params cmaptypes".split())
_SUPPORTED_COMPRESSION = frozenset({zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED})
_INCLUDE_RE = re.compile(r'^\s*#\s*include\b\s*[<"]([^>"]+)[>"]')
_SECTION_RE = re.compile(r"^\s*\[\s*([A-Za-z0-9_]+)\s*\]")
_DIRECTIVE_RE = re.compile(r"^\s*#\s*([A-Za-z]+)\b")
_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_CONDITIONAL_DIRECTIVES = frozenset({"ifdef", "ifndef", "else", "elif", "endif", "define", "undef"})
_POSITION_RESTRAINT_SECTIONS = frozenset({"position_restraints"})
class LigandParameterizationError(ValueError):
    pass
@dataclass(frozen=True)
class LigandPrepConfig:
    mode: str = "auto"
    ligand_resname: str = DEFAULT_LIGAND_RESNAME
    net_charge: int | None = None
    charge_method: str = "bcc"
    ligand_index: int = 0
    amber_root: str = "/opt/amber"
    acpype_bin: str = "acpype"
@dataclass(frozen=True)
class ParameterizedLigand:
    mode: str
    ligand_resname: str
    atomtypes_itp: Path | None
    ligand_itp: Path
    ligand_gro: Path
    posre_itp: Path | None
    template_sdf: Path | None
    net_charge: int
    atom_count: int
    charge_method: str
    moleculetype: str = ""
def validate_ligand_resname(resname: str) -> str:
    if not isinstance(resname, str) or not re.fullmatch(r"[A-Z0-9]{1,3}", resname or ""):
        raise LigandParameterizationError("ligand resname must be 1-3 uppercase alphanumerics")
    if resname in RESERVED_RESNAMES:
        raise LigandParameterizationError(f"reserved residue name: {resname}")
    return resname
def _normalise_relative_path(raw: str) -> str:
    text = str(raw).strip().replace("\\", "/")
    if not text or text.startswith("/") or _DRIVE_RE.match(text):
        raise LigandParameterizationError(f"absolute or empty path rejected: {raw!r}")
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if ".." in parts or not parts:
        raise LigandParameterizationError(f"unsafe path rejected: {raw!r}")
    return "/".join(parts)
def _ensure_within(target: Path, root: Path) -> None:
    # resolve() follows symlinks, so this also rejects a parent that links outside the root.
    try:
        Path(target).resolve().relative_to(Path(root).resolve())
    except ValueError as exc:
        raise LigandParameterizationError(f"path escapes extraction root: {target}") from exc
def _relative_parents(relative: str) -> list[str]:
    parts = relative.split("/")
    return ["/".join(parts[:index]) for index in range(1, len(parts))]
def _register_zip_directory(spellings: dict[str, str], relative: str, member: str) -> None:
    # Explicit directory entries and implicit parents share one casefold namespace: "params" vs "PARAMS" collide.
    key = relative.casefold()
    existing = spellings.get(key)
    if existing is not None and existing != relative:
        raise LigandParameterizationError(
            f"case-insensitive directory duplicate: {existing!r} vs {relative!r} (member {member})")
    spellings[key] = relative
def _publish_directory(staging: Path, dest_dir: Path) -> None:
    # The staging tree lives in dest_dir's parent, so the swap is a same-filesystem rename; replacing a tree
    # takes two renames, so failures roll back from the backup, which is kept if the target reappeared.
    dest_dir = Path(dest_dir)
    if not dest_dir.exists():
        os.replace(staging, dest_dir)
        return
    backup = Path(tempfile.mkdtemp(prefix=f".{dest_dir.name}.bak-", dir=str(dest_dir.parent)))
    backup.rmdir()
    os.replace(dest_dir, backup)
    try:
        os.replace(staging, dest_dir)
    except BaseException as exc:
        if dest_dir.exists():
            raise LigandParameterizationError(
                f"cannot publish {dest_dir}: target reappeared; previous results kept at {backup}") from exc
        os.replace(backup, dest_dir)
        raise
    shutil.rmtree(backup, ignore_errors=True)
def safe_extract_topology_zip(zip_path: Path, dest_dir: Path) -> list[Path]:
    # Staging dir + atomic publish; rejects traversal, symlinks, duplicates and zip bombs.
    # All member validation happens before a single directory or file is created under staging.
    zip_path, dest_dir = Path(zip_path), Path(dest_dir).resolve()
    if not zip_path.is_file() or not zipfile.is_zipfile(zip_path):
        raise LigandParameterizationError(f"not a zip archive: {zip_path}")
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{dest_dir.name}.tmp-", dir=str(dest_dir.parent)))
    try:
        with zipfile.ZipFile(zip_path) as archive:
            members = archive.infolist()
            if len(members) > MAX_ZIP_FILES:
                raise LigandParameterizationError(f"too many zip entries (limit {MAX_ZIP_FILES})")
            planned, seen_keys, file_keys, dir_spellings = [], set(), set(), {}
            declared = 0
            for info in members:
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise LigandParameterizationError(f"symlink member rejected: {info.filename}")
                relative = _normalise_relative_path(info.filename)
                key, parents = relative.casefold(), _relative_parents(relative)
                if key in seen_keys:
                    raise LigandParameterizationError(f"duplicate zip member: {info.filename}")
                seen_keys.add(key)
                if info.is_dir():
                    # A directory (or any of its implicit parents) may not reuse a file path: a later
                    # `params/empty/` after a file named `params` would need `params` to be both.
                    if key in file_keys or any(parent.casefold() in file_keys for parent in parents):
                        raise LigandParameterizationError(f"directory collides with a file: {info.filename}")
                    _register_zip_directory(dir_spellings, relative, info.filename)
                    for parent in parents:
                        _register_zip_directory(dir_spellings, parent, info.filename)
                    continue
                if info.compress_type not in _SUPPORTED_COMPRESSION:
                    raise LigandParameterizationError(f"unsupported compression: {info.filename}")
                if key in dir_spellings:
                    raise LigandParameterizationError(f"file collides with a directory: {info.filename}")
                for parent in parents:
                    if parent.casefold() in file_keys:
                        raise LigandParameterizationError(f"file collides with a directory: {info.filename}")
                    _register_zip_directory(dir_spellings, parent, info.filename)
                file_keys.add(key)
                declared += max(0, int(info.file_size))
                if declared > MAX_ZIP_UNCOMPRESSED_BYTES:
                    raise LigandParameterizationError("zip exceeds uncompressed size limit")
                _ensure_within(staging.joinpath(*relative.split("/")), staging)
                planned.append((info, relative))
            budget = MAX_ZIP_UNCOMPRESSED_BYTES
            for info, relative in planned:
                target = staging.joinpath(*relative.split("/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open("wb") as sink:
                    for chunk in iter(lambda: source.read(65536), b""):
                        budget -= len(chunk)
                        if budget < 0:
                            raise LigandParameterizationError("zip exceeds uncompressed size limit")
                        sink.write(chunk)
        _publish_directory(staging, dest_dir)
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)
    return [dest_dir.joinpath(*relative.split("/")) for _, relative in planned]
def _resolve_include_target(base_dir: Path, raw: str, root: Path, source: Path) -> Path:
    relative = _normalise_relative_path(raw)
    target = base_dir.joinpath(*relative.split("/")).resolve()
    if target != root and root not in target.parents:
        raise LigandParameterizationError(f"#include escapes bundle root: {relative} (from {source})")
    if not target.is_file():
        raise LigandParameterizationError(f"#include target missing: {relative} (from {source})")
    return target
def validate_itp_security(itp_path: Path, *, root: Path | None = None, _visited: dict[Path, bool] | None = None,
                          _visiting: set[Path] | None = None, _require_section: bool = True) -> bool:
    # Validate every #include recursively; relative targets resolve from the *including* file's directory.
    # `_visiting` is the recursion stack (a repeat there is a real cycle); `_visited` caches validated files.
    # A pure #include wrapper or a data-row-only sub-file needs no section of its own: the requirement is
    # judged on the entry file's whole expanded graph, while every file still gets path/cycle/non-empty checks.
    path = Path(itp_path)
    if not path.is_file():
        raise LigandParameterizationError(f"topology file not found: {path}")
    resolved = path.resolve()
    root_path = Path(root).resolve() if root is not None else None
    if root_path is not None and resolved != root_path and root_path not in resolved.parents:
        raise LigandParameterizationError(f"topology file escapes bundle root: {path}")
    entry, visited, visiting = (
        _visiting is None, {} if _visited is None else _visited, set() if _visiting is None else _visiting)
    if resolved in visiting:
        raise LigandParameterizationError(f"recursive #include cycle at {path}")
    if resolved in visited:
        return visited[resolved]
    visiting.add(resolved)
    has_section = has_content = False
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        code = line.split(";", 1)[0].strip()
        match = _INCLUDE_RE.match(code)
        if match and root_path is not None:
            target = _resolve_include_target(resolved.parent, match.group(1), root_path, path)
            has_section = validate_itp_security(target, root=root_path, _visited=visited, _visiting=visiting) \
                or has_section
        if not code or code.startswith("#"):
            continue
        has_content = True
        has_section = has_section or bool(_SECTION_RE.match(code))
    visiting.discard(resolved)
    visited[resolved] = has_section
    if not has_section and ((entry and _require_section) or not has_content):
        raise LigandParameterizationError(f"no GROMACS section in {path}")
    return has_section
def _section_blocks(text: str) -> tuple[list[tuple[str, list[str], int, int]], int, bool]:
    # Each block carries its start depth and the deepest nesting it reaches, so conditional guards are caught.
    depth, blocks, name, lines, start_depth, max_depth = 0, [], "preamble", [], 0, 0
    has_conditionals = False
    for line in text.splitlines():
        directive = _DIRECTIVE_RE.match(line.strip())
        keyword = directive.group(1).lower() if directive else ""
        if keyword in _CONDITIONAL_DIRECTIVES:
            has_conditionals = True
        current = depth
        if keyword in ("ifdef", "ifndef"):
            depth += 1
        elif keyword == "endif":
            depth -= 1
            if depth < 0:
                raise LigandParameterizationError("unbalanced conditional compilation: unexpected #endif")
        match = _SECTION_RE.match(line)
        if match:
            blocks.append((name, lines, start_depth, max_depth))
            name, lines, start_depth, max_depth = match.group(1).lower(), [line], current, current
        else:
            lines.append(line)
            max_depth = max(max_depth, depth)
    blocks.append((name, lines, start_depth, max_depth))
    return blocks, depth, has_conditionals
def inline_itp_includes(itp_path: Path, *, root: Path, seen: set[Path] | None = None) -> str:
    # Expand every validated relative #include in place, depth first (GROMACS preprocessing order),
    # keeping conditional directives intact. `seen` collects every expanded file, so callers can tell
    # whether an extra source (e.g. a .prm) is already in the text and must not be appended twice.
    resolved, root_path = Path(itp_path).resolve(), Path(root).resolve()
    if resolved != root_path and root_path not in resolved.parents:
        raise LigandParameterizationError(f"topology file escapes bundle root: {itp_path}")
    expanded_files = set() if seen is None else seen
    def expand(current: Path, stack: tuple[Path, ...]) -> list[str]:
        if current in stack:
            raise LigandParameterizationError(f"recursive #include cycle at {current}")
        expanded_files.add(current)
        expanded: list[str] = []
        for line in current.read_text(encoding="utf-8", errors="ignore").splitlines():
            match = _INCLUDE_RE.match(line.split(";", 1)[0].strip())
            if match is None:
                expanded.append(line)
                continue
            target = _resolve_include_target(current.parent, match.group(1), root_path, current)
            expanded.extend(expand(target, (*stack, current)))
        return expanded
    return "\n".join(expand(resolved, ())) + "\n"
def _split_atomtypes_texts(sources: list[tuple[Path, str]], *, out_atomtypes_itp: Path,
                           out_clean_itp: Path) -> tuple[Path | None, Path]:
    clean_lines, global_lines, header_lines = [], [], []
    for position, (path, text) in enumerate(sources):
        blocks, final_depth, has_conditionals = _section_blocks(text)
        if final_depth != 0:
            raise LigandParameterizationError(f"unbalanced conditional compilation in {path}")
        has_globals = any(name in _GLOBAL_SECTIONS for name, _lines, _start, _max in blocks)
        if has_globals and has_conditionals:
            # Relocating global sections past #define/#ifdef would change macro scope: refuse instead of guessing.
            raise LigandParameterizationError(
                f"conditional directives interleave with global parameter sections in {path}")
        for name, lines, start_depth, end_depth in blocks:
            if name in _GLOBAL_SECTIONS:
                if start_depth or end_depth:
                    raise LigandParameterizationError(f"[{name}] is inside conditional compilation in {path}")
                global_lines.extend([*lines, ""])
            elif position == 0:
                clean_lines.extend(lines)
            elif name == "preamble":
                keep = [line for line in lines if not line.strip() or line.strip().startswith(";")]
                if len(keep) != len(lines):
                    raise LigandParameterizationError(f"non-comment preamble of {path} cannot be relocated")
                header_lines.extend(keep)
    out_clean = Path(out_clean_itp)
    out_clean.parent.mkdir(parents=True, exist_ok=True)
    clean_text = "\n".join(clean_lines).strip()
    out_clean.write_text(clean_text + "\n" if clean_text else "", encoding="utf-8")
    if not global_lines:
        return None, out_clean
    out_atomtypes = Path(out_atomtypes_itp)
    out_atomtypes.parent.mkdir(parents=True, exist_ok=True)
    out_atomtypes.write_text("\n".join([*header_lines, *global_lines]).strip() + "\n", encoding="utf-8")
    return out_atomtypes, out_clean
def split_atomtypes_from_itp(source_itp: Path, *, out_atomtypes_itp: Path, out_clean_itp: Path,
                             extra_prm: Path | None = None) -> tuple[Path | None, Path]:
    sources = [Path(source_itp)] + ([Path(extra_prm)] if extra_prm else [])
    texts: list[tuple[Path, str]] = []
    for path in sources:
        if not path.is_file():
            raise LigandParameterizationError(f"topology file not found: {path}")
        texts.append((path, path.read_text(encoding="utf-8", errors="ignore")))
    return _split_atomtypes_texts(texts, out_atomtypes_itp=out_atomtypes_itp, out_clean_itp=out_clean_itp)
def _has_include(text: str) -> bool:
    return any(_INCLUDE_RE.match(line.split(";", 1)[0].strip()) for line in text.splitlines())
def _delivered_sections(path: Path, label: str) -> list[str]:
    if not path.is_file():
        raise LigandParameterizationError(f"{label} ITP missing after splitting: {path}")
    text = path.read_text(encoding="utf-8", errors="ignore")
    if _has_include(text):
        raise LigandParameterizationError(f"delivered topology still contains #include: {path}")
    blocks, final_depth, _conditionals = _section_blocks(text)
    if final_depth != 0:
        raise LigandParameterizationError(f"unbalanced conditional compilation in {path}")
    names = [name for name, _lines, _start, _max in blocks if name != "preamble"]
    # GROMACS already read the force-field [ defaults ] by the time it includes us; a second one is fatal.
    if "defaults" in names:
        raise LigandParameterizationError(f"[ defaults ] is not allowed in delivered topology: {path}")
    return names
def validate_delivered_topology(ligand_itp: Path, atomtypes_itp: Path | None) -> None:
    # GROMACS must read exactly the graph we validated: delivered files are self-contained (includes
    # inlined), globals live only in the atomtypes ITP, and [ atomtypes ] precedes dependents.
    ligand_path = Path(ligand_itp)
    ligand_sections = _delivered_sections(ligand_path, "ligand")
    leaked = sorted({name for name in ligand_sections if name in _GLOBAL_SECTIONS})
    if leaked:
        raise LigandParameterizationError(f"global parameter sections leaked into {ligand_path}: {leaked}")
    if atomtypes_itp is None:
        return
    atomtypes_path = Path(atomtypes_itp)
    names = _delivered_sections(atomtypes_path, "atomtypes")
    unexpected = sorted({name for name in names if name not in _GLOBAL_SECTIONS})
    if unexpected:
        raise LigandParameterizationError(f"non-global sections in {atomtypes_path}: {unexpected}")
    if "atomtypes" not in names:
        raise LigandParameterizationError(f"no [ atomtypes ] section in {atomtypes_path}")
    for name in names:
        if name != "atomtypes" and name in _GLOBAL_SECTIONS and names.index(name) < names.index("atomtypes"):
            raise LigandParameterizationError(f"[{name}] precedes [ atomtypes ] in {atomtypes_path}")
def _prepare_delivered_posre(posre_path: Path, *, root: Path, out_path: Path, seen: set[Path] | None = None) -> Path:
    # The .top re-includes the posre file by name, so the delivered copy must resolve next to it: expand the
    # validated graph and keep only position-restraint sections (a stray [ atomtypes ]/[ defaults ] would
    # corrupt the topology). `seen` is the expanded closure, compared against the ligand ITP's inlined graph.
    text = inline_itp_includes(posre_path, root=root, seen=seen)
    validate_itp_security(posre_path, root=root)
    delivered = Path(out_path)
    if _has_include(text):
        raise LigandParameterizationError(f"delivered posre ITP still contains #include: {delivered}")
    blocks, final_depth, _conditionals = _section_blocks(text)
    if final_depth != 0:
        raise LigandParameterizationError(f"unbalanced conditional compilation in {delivered}")
    names = [name for name, _lines, _start, _max in blocks if name != "preamble"]
    unexpected = sorted({name for name in names if name not in _POSITION_RESTRAINT_SECTIONS})
    if unexpected:
        raise LigandParameterizationError(f"posre ITP carries non-restraint sections {unexpected}: {delivered}")
    if "position_restraints" not in names:
        raise LigandParameterizationError(f"no [ position_restraints ] section in {delivered}")
    delivered.parent.mkdir(parents=True, exist_ok=True)
    delivered.write_text(text, encoding="utf-8")
    return delivered
def detect_moleculetype_name(itp_path: Path) -> str:
    path = Path(itp_path)
    if not path.is_file():
        raise LigandParameterizationError(f"topology file not found: {path}")
    in_section = False
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        stripped = line.split(";", 1)[0].strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _SECTION_RE.match(stripped)
        if match:
            in_section = match.group(1).lower() == "moleculetype"
        elif in_section:
            return stripped.split()[0]
    raise LigandParameterizationError(f"no [ moleculetype ] entry in {itp_path}")
def _closure_has_section(path: Path, *, root: Path, section: str) -> bool:
    # A pure #include wrapper has no section of its own: judge the whole expanded graph.
    text = inline_itp_includes(path, root=root)
    return any(match and match.group(1).lower() == section for match in map(_SECTION_RE.match, text.splitlines()))
def _referenced_files(paths: list[Path], *, root: Path) -> set[Path]:
    # Expanded #include closures minus the files themselves: an include target is a fragment, not an entry.
    referenced: set[Path] = set()
    for path in (p for p in paths if p.suffix.lower() in (".itp", ".prm", ".top", ".rtp")):
        entry, closure = Path(path).resolve(), {Path(path).resolve()}
        inline_itp_includes(path, root=root, seen=closure)
        referenced |= closure - {entry}
    return referenced
def _select_entry(paths: list[Path], *, root: Path, section: str, referenced: set[Path]) -> Path | None:
    # Prefer files whose expanded closure owns the section, then a root entry no sibling includes.
    matching = [path for path in paths if _closure_has_section(path, root=root, section=section)]
    pool = matching or list(paths)
    roots = [path for path in pool if path.resolve() not in referenced]
    return (roots or pool or [None])[0]
def _read_gro(path: Path) -> tuple[list[str], str]:
    path = Path(path)
    if not path.is_file():
        raise LigandParameterizationError(f".gro not found: {path}")
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    try:
        count = int(lines[1].strip()) if len(lines) >= 2 else -1
    except ValueError as exc:
        raise LigandParameterizationError(f"invalid .gro atom count: {path}") from exc
    if count < 0 or len(lines) < 3 + count:
        raise LigandParameterizationError(f"invalid or truncated .gro: {path}")
    tokens = lines[2 + count].split()
    if len(tokens) not in (3, 9):
        raise LigandParameterizationError(f"invalid .gro box vector: {' '.join(tokens)!r}")
    try:
        if not all(math.isfinite(float(token)) for token in tokens):
            raise ValueError
    except ValueError as exc:
        raise LigandParameterizationError(f"invalid .gro box vector: {' '.join(tokens)!r}") from exc
    atoms = lines[2:2 + count]
    for line in atoms:
        _gro_atom(line)  # every atom line is parsed here too: Mode 0 never delivers unvalidated coordinates
    return atoms, " ".join(tokens)
def _gro_column_width(field: str) -> int | None:
    # GROMACS (groio.cpp) takes one width for all coordinates from the first value: 5 + decimals (%8.3f -> 8).
    dot = field.find(".")
    if dot < 0:
        return None
    digits = 0
    for char in field[dot + 1:]:
        if not char.isdigit():
            break
        digits += 1
    width = 5 + digits
    return width if digits and width <= 12 else None
def _gro_fixed_floats(chunk: str, width: int, count: int, line: str) -> list[float]:
    # Strict fixed-column slices only: a misaligned field must fail, never be "repaired" from a regex.
    if len(chunk) < width * count:
        raise LigandParameterizationError(f"invalid .gro coordinates: {line!r}")
    values = []
    for slot in range(count):
        try:
            values.append(float(chunk[slot * width:(slot + 1) * width]))
        except ValueError as exc:
            raise LigandParameterizationError(f"invalid .gro coordinates: {line!r}") from exc
    if not all(math.isfinite(value) for value in values):
        raise LigandParameterizationError(f"non-finite .gro coordinates: {line!r}")
    return values
def _gro_atom(line: str) -> tuple[str, tuple[float, float, float]]:
    # GRO cols 1-20 are fixed; coordinates share one width per value, optional velocities follow at that width.
    if len(line) < 20:
        raise LigandParameterizationError(f"invalid .gro atom line: {line!r}")
    width = _gro_column_width(line[20:])
    if width is None:
        raise LigandParameterizationError(f"invalid .gro coordinates: {line!r}")
    coordinates = _gro_fixed_floats(line[20:20 + 3 * width], width, 3, line)
    velocities = line[20 + 3 * width:]
    if velocities.strip():
        _gro_fixed_floats(velocities, width, 3, line)  # optional, but must align and be finite
    # At most 3 coordinates + 3 velocities: anything past the sixth field is malformed and must not be dropped.
    if velocities[3 * width:].strip():
        raise LigandParameterizationError(f"unexpected extra .gro fields: {line!r}")
    return line[0:15], (coordinates[0], coordinates[1], coordinates[2])
def merge_gro_files(protein_gro: Path, ligand_gro: Path, out_complex_gro: Path) -> int:
    # Fixed 8.3f precision for every atom; a 3- or 9-component box is preserved verbatim.
    protein_atoms, box = _read_gro(protein_gro)
    ligand_atoms, _ = _read_gro(ligand_gro)
    rows = []
    for line in [*protein_atoms, *ligand_atoms]:
        prefix, coordinates = _gro_atom(line)
        rows.append(f"{prefix}{(len(rows) + 1) % 100000:5d}" + "".join(f"{value:8.3f}" for value in coordinates))
    out = Path(out_complex_gro)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(["complex", f"{len(rows):5d}", *rows, box]) + "\n", encoding="utf-8")
    return len(rows)
def _include_target(line: str) -> str | None:
    match = _INCLUDE_RE.match(line)
    return match.group(1).strip().replace("\\", "/") if match else None
def _preprocessor_depths(lines: list[str]) -> list[int]:
    # Nesting depth *at* each line; the #ifdef/#ifndef line itself is depth 0, everything inside is > 0.
    depths, depth = [], 0
    for line in lines:
        directive = _DIRECTIVE_RE.match(line.split(";", 1)[0].strip())
        keyword = directive.group(1).lower() if directive else ""
        if keyword == "endif":
            depth = max(0, depth - 1)
        depths.append(depth)
        if keyword in ("ifdef", "ifndef"):
            depth += 1
    return depths
def _find_include(lines: list[str], name: str, depths: list[int] | None = None) -> int | None:
    # With `depths`, only unconditioned (depth 0) includes match: one inside #ifdef WATER disappears elsewhere.
    wanted = name.casefold()
    return next((i for i, line in enumerate(lines)
                 if (depths is None or depths[i] == 0) and (_include_target(line) or "").casefold() == wanted), None)
def _section_index(lines: list[str], name: str, depths: list[int] | None = None) -> int | None:
    for index, line in enumerate(lines):
        if depths is not None and depths[index] != 0:
            continue
        match = _SECTION_RE.match(line.split(";", 1)[0].strip())
        if match and match.group(1).lower() == name:
            return index
    return None
def _ligand_insert_index(lines: list[str]) -> int:
    # Insert at preprocessor depth 0: a ligand include inside #ifdef WATER vanishes without water.
    depth = 0
    for index, line in enumerate(lines):
        code = line.split(";", 1)[0].strip()
        directive = _DIRECTIVE_RE.match(code)
        keyword = directive.group(1).lower() if directive else ""
        if keyword in ("ifdef", "ifndef"):
            depth += 1
            continue
        if keyword == "endif":
            depth = max(0, depth - 1)
            continue
        if depth != 0 or keyword in ("else", "elif", "define", "undef", "pragma", "error", "warning"):
            continue
        target = _include_target(code) or ""
        match = _SECTION_RE.match(code)
        section = match.group(1).lower() if match else ""
        if re.search(r"(tip[345]p|spc|water)", target, re.I) and target.lower().endswith(".itp"):
            return index
        if section in ("system", "molecules"):
            return index
    return len(lines)
def patch_topol_top(topol_path: Path, *, ligand_itp_name: str, moleculetype_name: str,
                    atomtypes_itp_name: str | None = None, posre_itp_name: str | None = None,
                    ligand_count: int = 1) -> str:
    # Idempotent: ignores comments, indented includes still match, never writes after [ molecules ].
    path = Path(topol_path)
    if not path.is_file():
        raise LigandParameterizationError(f"topology not found: {path}")
    lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    # Only depth-0 matches count: an include that exists only inside #ifdef WATER is no anchor, and a
    # conditional [ molecules ] would put the ligand entry where GROMACS never reads it.
    depths = _preprocessor_depths(lines)
    forcefield_index = next((i for i in range(len(lines)) if depths[i] == 0
                             and (_include_target(lines[i]) or "").lower().endswith("forcefield.itp")), None)
    if forcefield_index is None:
        raise LigandParameterizationError("topology has no top-level forcefield.itp include")
    if _section_index(lines, "system", depths) is None:
        raise LigandParameterizationError("topology has no top-level [ system ] section")
    if atomtypes_itp_name and _find_include(lines, atomtypes_itp_name, depths) is None:
        lines.insert(forcefield_index + 1, f'#include "{atomtypes_itp_name}"')
        depths = _preprocessor_depths(lines)
    posre_block = ["#ifdef POSRES_LIG", f'#include "{posre_itp_name}"', "#endif"] if posre_itp_name else []
    ligand_index = _find_include(lines, ligand_itp_name, depths)
    if ligand_index is None:
        insert_at = _ligand_insert_index(lines)
        lines[insert_at:insert_at] = [f'#include "{ligand_itp_name}"', *posre_block]
        depths = _preprocessor_depths(lines)
        ligand_index = _find_include(lines, ligand_itp_name, depths)
    elif posre_block and _find_include(lines, posre_itp_name or "") is None:
        lines[ligand_index + 1:ligand_index + 1] = posre_block
        depths = _preprocessor_depths(lines)
        ligand_index = _find_include(lines, ligand_itp_name, depths)
    # [ atomtypes ] must precede the ligand's [ atoms ]: refuse to patch an unusable include order.
    atomtypes_index = _find_include(lines, atomtypes_itp_name, depths) if atomtypes_itp_name else None
    if atomtypes_index is not None and ligand_index is not None and atomtypes_index > ligand_index:
        raise LigandParameterizationError(
            f"topology includes {ligand_itp_name} before {atomtypes_itp_name}; reorder them first")
    section = _section_index(lines, "molecules", depths)
    if section is None:
        raise LigandParameterizationError("topology has no top-level [ molecules ] section")
    entry = f"{moleculetype_name} {int(ligand_count)}"
    # Only a depth-0 header ends [ molecules ]; a conditional header must not truncate the scan.
    end = next((i for i in range(section + 1, len(lines))
                if depths[i] == 0 and _SECTION_RE.match(lines[i].split(";", 1)[0].strip())), len(lines))
    # Only a top-level entry may be rewritten; one inside #ifdef belongs to a different build.
    hit = next((i for i in range(section + 1, end)
                if depths[i] == 0 and (lines[i].split(";", 1)[0].split() or [""])[0] == moleculetype_name), None)
    if hit is not None:
        lines[hit] = entry
    else:
        insert_at = end
        while insert_at > section + 1 and (depths[insert_at - 1] != 0
                                           or not lines[insert_at - 1].split(";", 1)[0].strip()):
            insert_at -= 1
        lines.insert(insert_at, entry)
    text = "\n".join(lines).rstrip() + "\n"
    path.write_text(text, encoding="utf-8")
    return text
def _itp_atom_rows(itp_path: Path) -> list[list[str]]:
    rows, in_atoms = [], False
    for line in Path(itp_path).read_text(encoding="utf-8", errors="ignore").splitlines():
        code = line.split(";", 1)[0].strip()
        if not code or code.startswith("#"):
            continue
        match = _SECTION_RE.match(code)
        if match:
            in_atoms = match.group(1).lower() == "atoms"
        elif in_atoms:
            rows.append(code.split())
    return rows
def _validate_structure_consistency(itp_path: Path, gro_path: Path, *, expected_resname: str | None = None) -> int:
    rows = _itp_atom_rows(itp_path)
    gro_atoms, _ = _read_gro(gro_path)
    if not rows:
        raise LigandParameterizationError(f"no [ atoms ] entries in {itp_path}")
    if len(rows) != len(gro_atoms):
        raise LigandParameterizationError(
            f"atom count mismatch: {itp_path} has {len(rows)}, {gro_path} has {len(gro_atoms)}")
    itp_resnames = {row[3] for row in rows if len(row) >= 4}
    gro_resnames = {line[5:10].strip() for line in gro_atoms}
    if itp_resnames != gro_resnames:
        raise LigandParameterizationError(
            f"residue name mismatch: itp {sorted(itp_resnames)}, gro {sorted(gro_resnames)}")
    if expected_resname is not None and itp_resnames != {expected_resname}:
        raise LigandParameterizationError(f"unexpected ligand residue name(s): {sorted(itp_resnames)}")
    return len(rows)
def prepare_ligand_with_rdkit(ligand_path: Path, work_dir: Path, *, ligand_resname: str = DEFAULT_LIGAND_RESNAME,
                              net_charge: int | None = None, ligand_index: int = 0) -> dict:
    # Locate the original 0-based SDF record, require finite non-degenerate 3D, write .sdf + .pdb.
    from rdkit import Chem
    path, work = Path(ligand_path), Path(work_dir).resolve()
    work.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        raise LigandParameterizationError(f"ligand file not found: {path}")
    resname, suffix = validate_ligand_resname(ligand_resname), path.suffix.lower()
    if suffix == ".sdf":
        supplier, index = Chem.SDMolSupplier(str(path), removeHs=False), int(ligand_index)
        if index < 0 or (hasattr(supplier, "__len__") and index >= len(supplier)):
            raise LigandParameterizationError(f"ligand index {index} out of range")
        try:
            molecule = supplier[index]
        except (IndexError, RuntimeError) as exc:
            raise LigandParameterizationError(f"ligand index {index} out of range") from exc
        if molecule is None:
            raise LigandParameterizationError(f"cannot read record {index} from {path}")
    elif suffix in (".mol", ".mol2"):
        reader = Chem.MolFromMolFile if suffix == ".mol" else Chem.MolFromMol2File
        molecule = reader(str(path), removeHs=False)
    else:
        raise LigandParameterizationError(f"unsupported ligand format: {suffix}")
    if molecule is None or molecule.GetNumAtoms() == 0:
        raise LigandParameterizationError(f"cannot read a non-empty molecule from {path}")
    if molecule.GetNumConformers() == 0 or not molecule.GetConformer().Is3D():
        raise LigandParameterizationError("ligand has no 3D coordinates")
    conformer = molecule.GetConformer()
    positions = [conformer.GetAtomPosition(i) for i in range(molecule.GetNumAtoms())]
    if not all(math.isfinite(p.x) and math.isfinite(p.y) and math.isfinite(p.z) for p in positions):
        raise LigandParameterizationError("ligand has non-finite 3D coordinates")
    if len({(round(p.x, 9), round(p.y, 9), round(p.z, 9)) for p in positions}) == 1:
        raise LigandParameterizationError("ligand 3D coordinates are degenerate")
    molecule = Chem.AddHs(molecule, addCoords=True)
    inferred = sum(atom.GetFormalCharge() for atom in molecule.GetAtoms())
    if net_charge is not None and int(net_charge) != inferred:
        raise LigandParameterizationError(f"net charge mismatch: config {net_charge}, molecule {inferred}")
    molecule.SetProp("_Name", resname)
    for index, atom in enumerate(molecule.GetAtoms(), start=1):
        atom.SetMonomerInfo(Chem.AtomPDBResidueInfo(atomName=f"{atom.GetSymbol()}{index}"[:4],
                            residueName=resname, residueNumber=1, chainId="A", isHeteroAtom=True))
    sdf, pdb = work / "ligand.sdf", work / "ligand.pdb"
    writer = Chem.SDWriter(str(sdf))
    writer.write(molecule)
    writer.close()
    Chem.MolToPDBFile(molecule, str(pdb))
    return {"sdf": sdf, "pdb": pdb, "net_charge": inferred if net_charge is None else int(net_charge),
            "atom_count": molecule.GetNumAtoms()}
def build_acpype_command(ligand_mol_path: Path, *, ligand_resname: str = DEFAULT_LIGAND_RESNAME,
                         charge_method: str = "bcc", net_charge: int = 0, acpype_bin: str = "acpype") -> list[str]:
    resname, method = validate_ligand_resname(ligand_resname), str(charge_method).lower()
    if method not in ALLOWED_CHARGE_METHODS:
        raise LigandParameterizationError(f"unsupported charge method: {charge_method}")
    return [acpype_bin, "-i", str(ligand_mol_path), "-b", resname, "-a", "gaff2",
            "-c", method, "-n", str(int(net_charge)), "-o", "gmx", "-d"]
def resolve_amber_env(amber_root: str | Path, base_env: dict | None = None) -> dict:
    conda = Path(amber_root) / "anaconda3"
    amber = conda / "envs" / "AmberTools"
    env = dict(os.environ if base_env is None else base_env)
    env.update({"AMBERHOME": str(amber), "OPAL_PREFIX": str(conda),
                "PATH": f"{amber / 'bin'}{os.pathsep}{conda / 'bin'}{os.pathsep}{env.get('PATH', '')}",
                "LD_LIBRARY_PATH": (f"{conda / 'lib'}{os.pathsep}{amber / 'lib'}{os.pathsep}"
                                    f"{env.get('LD_LIBRARY_PATH', '')}"),
                "OMPI_MCA_plm": "isolated", "OMPI_MCA_rmaps_base_oversubscribe": "1"})
    return env
def _run_custom_bundle(work: Path, config: LigandPrepConfig, resname: str, ligand_sdf: Path | None,
                       custom_itp: Path | None, custom_prm: Path | None, custom_gro: Path | None,
                       custom_zip: Path | None) -> ParameterizedLigand:
    source_itp, source_prm, source_gro = (Path(p) if p else None for p in (custom_itp, custom_prm, custom_gro))
    extras: list[Path] = []
    referenced: set[Path] = set()
    if custom_zip:
        extras = safe_extract_topology_zip(Path(custom_zip), work / "custom_topology")
        bundle_root = (work / "custom_topology").resolve()
        referenced = _referenced_files(extras, root=bundle_root)
        candidates = [p for p in extras if p.suffix.lower() == ".itp" and "posre" not in p.name.lower()]
        source_itp = source_itp or _select_entry(candidates, root=bundle_root, section="moleculetype", referenced=referenced)
        source_prm = source_prm or next((p for p in extras if p.suffix.lower() in (".prm", ".rtp")), None)
        source_gro = source_gro or next((p for p in extras if p.suffix.lower() == ".gro"), None)
    for label, required_path in (("custom ITP", source_itp), ("custom ligand .gro", source_gro)):
        if required_path is None or not required_path.is_file():
            raise LigandParameterizationError(f"{label} is required for Mode 0")
    root = (work / "custom_topology").resolve() if custom_zip else source_itp.resolve().parent
    # Entries (the topology GROMACS actually reads) must expand to a section; bundle extras are validated
    # through the shared cache and may be data-row-only fragments, so they carry no section of their own.
    visited: dict[Path, bool] = {}
    for path in [source_itp, *([source_prm] if source_prm else []), *extras]:
        if path.suffix.lower() in (".itp", ".prm", ".top", ".rtp"):
            validate_itp_security(path, root=root, _visited=visited, _require_section=path in (source_itp, source_prm))
    # Validation only proved the graph inside the bundle is safe. The delivered topology lives in work/,
    # where those relative includes no longer resolve, so expand them in GROMACS preprocessing order and
    # split the (now self-contained) text. Nothing outside the validated root can be pulled in afterwards.
    included: set[Path] = set()
    sources = [(source_itp, inline_itp_includes(source_itp, root=root, seen=included))]
    if source_prm is not None and source_prm.resolve() not in included:
        sources.append((source_prm, inline_itp_includes(source_prm, root=root)))
    atomtypes, clean_itp = _split_atomtypes_texts(
        sources, out_atomtypes_itp=work / "ligand_atomtypes.itp", out_clean_itp=work / "ligand.itp")
    validate_delivered_topology(clean_itp, atomtypes)
    posre_candidates = [p for p in extras if p.suffix.lower() == ".itp" and "posre" in p.name.lower()]
    posre_candidate = _select_entry(posre_candidates, root=root, section="position_restraints", referenced=referenced)
    posre = None
    if posre_candidate is not None:
        # Compare the *whole* include closure: a posre wrapper whose children sit in ligand.itp is already
        # delivered, and a partially shared closure would apply the restraints twice via the .top.
        posre_seen: set[Path] = set()
        inline_itp_includes(posre_candidate, root=root, seen=posre_seen)
        if not (posre_seen <= included):
            if posre_seen & included:
                shared = ", ".join(sorted(path.name for path in posre_seen & included))
                raise LigandParameterizationError(
                    f"posre ITP shares inlined #include files with the ligand topology ({shared}); "
                    "delivering both would duplicate position restraints")
            posre = _prepare_delivered_posre(posre_candidate, root=root, out_path=work / "posre_ligand.itp", seen=posre_seen)
    atom_count = _validate_structure_consistency(clean_itp, source_gro)
    itp_resnames = {row[3] for row in _itp_atom_rows(clean_itp) if len(row) >= 4}
    if len(itp_resnames) != 1:
        raise LigandParameterizationError(f"Mode 0 requires one ligand residue name, got: {sorted(itp_resnames)}")
    actual_resname = validate_ligand_resname(next(iter(itp_resnames)))
    return ParameterizedLigand(
        mode="custom_itp", ligand_resname=actual_resname, atomtypes_itp=atomtypes, ligand_itp=clean_itp,
        ligand_gro=source_gro, posre_itp=posre, template_sdf=Path(ligand_sdf) if ligand_sdf else None,
        net_charge=int(config.net_charge or 0), atom_count=atom_count,
        charge_method="custom", moleculetype=detect_moleculetype_name(clean_itp))
def _run_acpype_mode(work: Path, config: LigandPrepConfig, resname: str, ligand_sdf: Path,
                     runner) -> ParameterizedLigand:
    prepared = prepare_ligand_with_rdkit(ligand_sdf, work / "prepared", ligand_resname=resname,
                                         net_charge=config.net_charge, ligand_index=config.ligand_index)
    # A fresh directory per call: stale output from an earlier run can never be picked up.
    acpype_dir = Path(tempfile.mkdtemp(prefix="acpype-", dir=str(work)))
    # acpype names its outputs after -b, so the command and the artefact lookup must share this exact basename.
    command = build_acpype_command(prepared["pdb"], ligand_resname=resname, charge_method=config.charge_method,
                                   net_charge=prepared["net_charge"], acpype_bin=config.acpype_bin)
    env = resolve_amber_env(config.amber_root)
    result = (runner(command, cwd=acpype_dir, env=env) if runner is not None else
              subprocess.run(command, cwd=str(acpype_dir), env=env, text=True, capture_output=True, check=False))
    if getattr(result, "returncode", 1) != 0:
        raise LigandParameterizationError("acpype failed: " + str(getattr(result, "stderr", ""))[-1200:])
    output_dir = acpype_dir / f"{resname}.acpype"
    gmx_itp, gmx_gro = output_dir / f"{resname}_GMX.itp", output_dir / f"{resname}_GMX.gro"
    # Exact non-OPLS artefacts only; never "first .itp found by recursive search".
    if not gmx_itp.is_file() or not gmx_gro.is_file():
        raise LigandParameterizationError(f"acpype output incomplete: expected {gmx_itp.name} and {gmx_gro.name}")
    validate_itp_security(gmx_itp)
    atomtypes, ligand_itp = split_atomtypes_from_itp(
        gmx_itp, out_atomtypes_itp=work / "ligand_atomtypes.itp", out_clean_itp=work / "ligand.itp")
    posre = next((path for path in sorted(output_dir.glob("*.itp")) if "posre" in path.name.lower()), None)
    return ParameterizedLigand(
        mode="gaff2_acpype", ligand_resname=resname, atomtypes_itp=atomtypes, ligand_itp=ligand_itp,
        ligand_gro=gmx_gro, posre_itp=posre, template_sdf=prepared["sdf"], net_charge=prepared["net_charge"],
        atom_count=_validate_structure_consistency(ligand_itp, gmx_gro, expected_resname=resname),
        charge_method=str(config.charge_method).lower(), moleculetype=detect_moleculetype_name(ligand_itp))
def parameterize_ligand(work_dir: Path, *, config: LigandPrepConfig, ligand_sdf: Path | None = None,
                        custom_itp: Path | None = None, custom_prm: Path | None = None,
                        custom_gro: Path | None = None, custom_zip: Path | None = None,
                        runner=None) -> ParameterizedLigand:
    work = Path(work_dir).resolve()
    work.mkdir(parents=True, exist_ok=True)
    resname, mode = validate_ligand_resname(config.ligand_resname), config.mode
    if mode == "auto":
        mode = "custom_itp" if (custom_itp or custom_zip) else "gaff2_acpype" if ligand_sdf else ""
    if mode == "custom_itp":
        return _run_custom_bundle(work, config, resname, ligand_sdf, custom_itp, custom_prm, custom_gro, custom_zip)
    if mode != "gaff2_acpype":
        raise LigandParameterizationError("cannot resolve ligand preparation mode from the supplied inputs")
    if not ligand_sdf:
        raise LigandParameterizationError("SDF/MOL/MOL2 ligand is required for GAFF2 parameterisation")
    return _run_acpype_mode(work, config, resname, Path(ligand_sdf), runner)
