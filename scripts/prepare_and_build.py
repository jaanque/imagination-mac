#!/usr/bin/env python3
"""Download, safely extract, auto-detect, and compile unsigned Swift/SwiftUI projects."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from urllib.parse import urlparse

MAX_ZIP_BYTES = 35 * 1024 * 1024  # 35 MB download limit
MAX_UNCOMPRESSED_BYTES = 250 * 1024 * 1024  # 250 MB zip-bomb guard
ALLOWED_INITIAL_HOSTS = {"github.com", "objects.githubusercontent.com"}

WORKSPACE_DIR = Path("/tmp/user_workspace")
OUTPUT_DIR = Path("/tmp/build_outputs")
DD_IOS = Path("/tmp/dd_ios")
DD_SIM = Path("/tmp/dd_sim")
DD_MACOS = Path("/tmp/dd_macos")


class BuildError(RuntimeError):
    """Raised when downloading, extracting, or compiling fails."""


def sanitize_log(text: str) -> str:
    """Redact internal runner paths from build logs before publishing."""
    replacements = [
        (str(WORKSPACE_DIR), "<workspace>"),
        (str(OUTPUT_DIR), "<outputs>"),
        (str(DD_IOS), "<derived-data-ios>"),
        (str(DD_SIM), "<derived-data-sim>"),
        (str(DD_MACOS), "<derived-data-macos>"),
        (os.environ.get("HOME", "/Users/runner"), "<home>"),
    ]
    sanitized = text
    for src, dst in replacements:
        if src:
            sanitized = sanitized.replace(src, dst)
    sanitized = re.sub(r"/Users/[^/\s]+", "<home>", sanitized)
    return sanitized


def append_report(log_chunks: list[str], title: str, content: str) -> None:
    """Append a section to the in-memory build report."""
    log_chunks.append(f"## {title}\n\n```text\n{sanitize_log(content).strip()}\n```\n")


def write_report(log_chunks: list[str]) -> None:
    """Persist build_report.md to OUTPUT_DIR."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = OUTPUT_DIR / "build_report.md"
    report_path.write_text("\n".join(log_chunks), encoding="utf-8")


def validate_initial_url(url: str) -> None:
    """Verify the download URL uses HTTPS and an allowed GitHub host."""
    parsed = urlparse(url)
    if parsed.scheme.lower() != "https":
        raise BuildError("Refusing non-HTTPS download URL.")
    if (parsed.hostname or "").lower() not in ALLOWED_INITIAL_HOSTS:
        raise BuildError("Download URL host is not in the allowed GitHub domains.")


def download_zip(url: str, dest_path: Path) -> None:
    """Stream-download the project archive with a strict 35 MB size cap."""
    validate_initial_url(url)
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Cloud-Swift-Builder/1.0"},
    )
    total = 0
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            content_length = resp.headers.get("Content-Length")
            if content_length and int(content_length) > MAX_ZIP_BYTES:
                raise BuildError(
                    f"Archive exceeds maximum allowed size ({MAX_ZIP_BYTES // (1024 * 1024)} MB)."
                )
            with open(dest_path, "wb") as out:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_ZIP_BYTES:
                        raise BuildError(
                            f"Downloaded archive exceeded {MAX_ZIP_BYTES // (1024 * 1024)} MB limit."
                        )
                    out.write(chunk)
    except urllib.error.URLError as exc:
        raise BuildError(f"Failed to download archive: {exc}") from exc


def safe_extract_zip(zip_path: Path, dest_dir: Path) -> None:
    """Extract a ZIP archive while blocking Zip Slip, symlinks, and zip bombs."""
    dest_resolved = dest_dir.resolve()
    total_uncompressed = 0

    with zipfile.ZipFile(zip_path, "r") as zf:
        for info in zf.infolist():
            member_name = info.filename
            if not member_name:
                continue

            # Reject symlinks stored in Unix mode bits
            mode = (info.external_attr >> 16) & 0o170000
            if mode == stat.S_IFLNK:
                raise BuildError(f"Refusing symlink inside archive: {member_name}")

            # Reject absolute paths or traversal segments
            pure_parts = Path(member_name).parts
            if Path(member_name).is_absolute() or ".." in pure_parts:
                raise BuildError(f"Unsafe path detected in archive (Zip Slip): {member_name}")

            target = (dest_resolved / member_name).resolve()
            if target != dest_resolved and dest_resolved not in target.parents:
                raise BuildError(f"Archive entry escapes workspace: {member_name}")

            total_uncompressed += info.file_size
            if total_uncompressed > MAX_UNCOMPRESSED_BYTES:
                raise BuildError("Archive uncompressed size exceeds 250 MB safety limit.")

            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)


def clean_macos_junk(root: Path) -> None:
    """Remove __MACOSX metadata directories and .DS_Store files."""
    for macosx_dir in list(root.rglob("__MACOSX")):
        if macosx_dir.is_dir():
            shutil.rmtree(macosx_dir, ignore_errors=True)
    for ds_store in list(root.rglob(".DS_Store")):
        if ds_store.is_file():
            ds_store.unlink(missing_ok=True)


def resolve_project_root(extract_dir: Path) -> Path:
    """Descend automatically if the archive wraps everything in a single folder."""
    entries = [p for p in extract_dir.iterdir() if p.name not in {"__MACOSX", ".DS_Store"}]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return extract_dir


def run_cmd(
    cmd: list[str],
    cwd: Path,
    log_chunks: list[str],
    step_title: str,
) -> subprocess.CompletedProcess[str]:
    """Run a subprocess, capturing combined stdout/stderr into the build report."""
    proc = subprocess.run(
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    append_report(log_chunks, step_title, proc.stdout or "(no output)")
    if proc.returncode != 0:
        raise BuildError(f"{step_title} failed with exit code {proc.returncode}.")
    return proc


def detect_scheme(project_root: Path, log_chunks: list[str]) -> tuple[list[str], str]:
    """Detect .xcworkspace or .xcodeproj and select the primary application scheme."""
    workspaces = sorted(project_root.glob("*.xcworkspace"))
    projects = sorted(project_root.glob("*.xcodeproj"))

    if workspaces:
        container_args = ["-workspace", str(workspaces[0])]
    elif projects:
        container_args = ["-project", str(projects[0])]
    else:
        raise BuildError("No .xcworkspace or .xcodeproj found after project preparation.")

    proc = subprocess.run(
        ["xcodebuild", *container_args, "-list", "-json"],
        cwd=str(project_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        append_report(log_chunks, "xcodebuild -list", proc.stdout or "(no output)")
        raise BuildError("Failed to inspect Xcode project schemes.")

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        append_report(log_chunks, "xcodebuild -list", proc.stdout or "(invalid json)")
        raise BuildError("Failed to parse xcodebuild -list JSON output.") from exc

    container_info = data.get("workspace") or data.get("project") or {}
    schemes: list[str] = container_info.get("schemes") or []
    if not schemes:
        raise BuildError("No build schemes found in Xcode project.")

    # Prefer non-test, non-Pods schemes
    preferred = [
        s
        for s in schemes
        if not s.endswith("Tests")
        and not s.endswith("UITests")
        and not s.startswith("Pods-")
    ]
    selected = preferred[0] if preferred else schemes[0]
    return container_args, selected


def generate_xcodegen_yml(
    project_root: Path,
    app_name: str,
    bundle_id: str,
    platform: str,
    swift_files: list[Path],
) -> None:
    """Create a project.yml for standalone .swift files."""
    rel_sources = sorted({str(p.parent.relative_to(project_root)) for p in swift_files})
    source_entries = "\n".join(
        f"      - path: {'.' if src == '.' else src}" for src in rel_sources
    )

    targets: list[str] = []
    if platform in {"ios", "both"}:
        targets.append(
            f"""  {app_name}-iOS:
    type: application
    platform: iOS
    deploymentTarget: "17.0"
    sources:
{source_entries}
    settings:
      base:
        PRODUCT_NAME: {app_name}
        PRODUCT_BUNDLE_IDENTIFIER: {bundle_id}
        GENERATE_INFOPLIST_FILE: YES
        INFOPLIST_KEY_UIApplicationSceneManifest_Generation: YES
        INFOPLIST_KEY_UILaunchScreen_Generation: YES
        CODE_SIGN_IDENTITY: ""
        CODE_SIGNING_REQUIRED: NO
        CODE_SIGNING_ALLOWED: NO"""
        )

    if platform in {"macos", "both"}:
        targets.append(
            f"""  {app_name}-macOS:
    type: application
    platform: macOS
    deploymentTarget: "14.0"
    sources:
{source_entries}
    settings:
      base:
        PRODUCT_NAME: {app_name}
        PRODUCT_BUNDLE_IDENTIFIER: {bundle_id}
        GENERATE_INFOPLIST_FILE: YES
        CODE_SIGN_IDENTITY: ""
        CODE_SIGNING_REQUIRED: NO
        CODE_SIGNING_ALLOWED: NO"""
        )

    yml_content = f"""name: {app_name}
options:
  bundleIdPrefix: {bundle_id.rsplit('.', 1)[0] if '.' in bundle_id else bundle_id}
  deploymentTarget:
    iOS: "17.0"
    macOS: "14.0"
targets:
{chr(10).join(targets)}
"""
    (project_root / "project.yml").write_text(yml_content, encoding="utf-8")


def prepare_project(
    project_root: Path,
    app_name: str,
    bundle_id: str,
    platform: str,
    log_chunks: list[str],
) -> tuple[list[str], dict[str, str]]:
    """Detect project mode (A: project.yml, B: Xcode project, C: standalone .swift) and prepare schemes."""
    has_project_yml = (project_root / "project.yml").is_file()
    has_xcode = bool(list(project_root.glob("*.xcworkspace")) or list(project_root.glob("*.xcodeproj")))

    if has_project_yml:
        append_report(log_chunks, "Project Detection", "Mode A: Found project.yml (XcodeGen).")
        run_cmd(["xcodegen", "generate"], project_root, log_chunks, "XcodeGen Generate")
        container_args, scheme = detect_scheme(project_root, log_chunks)
        return container_args, {"ios": scheme, "macos": scheme}

    if has_xcode:
        append_report(log_chunks, "Project Detection", "Mode B: Found existing .xcworkspace/.xcodeproj.")
        container_args, scheme = detect_scheme(project_root, log_chunks)
        return container_args, {"ios": scheme, "macos": scheme}

    swift_files = sorted(project_root.rglob("*.swift"))
    if not swift_files:
        raise BuildError(
            "No project.yml, .xcodeproj, .xcworkspace, or .swift files found in the uploaded archive."
        )

    append_report(
        log_chunks,
        "Project Detection",
        f"Mode C: Found {len(swift_files)} standalone .swift file(s). Generating project.yml.",
    )
    generate_xcodegen_yml(project_root, app_name, bundle_id, platform, swift_files)
    run_cmd(["xcodegen", "generate"], project_root, log_chunks, "XcodeGen Generate")

    container_args, default_scheme = detect_scheme(project_root, log_chunks)
    schemes: dict[str, str] = {}
    if platform in {"ios", "both"}:
        schemes["ios"] = f"{app_name}-iOS"
    if platform in {"macos", "both"}:
        schemes["macos"] = f"{app_name}-macOS"
    if not schemes:
        schemes = {"ios": default_scheme, "macos": default_scheme}
    return container_args, schemes


def find_built_app(products_dir: Path) -> Path:
    """Locate the compiled .app bundle inside Xcode DerivedData Products."""
    apps = sorted(products_dir.glob("*.app"))
    if not apps:
        raise BuildError(f"No .app bundle produced in {products_dir.name}.")
    return apps[0]


def package_ipa(app_path: Path, out_ipa: Path) -> None:
    """Wrap an unsigned .app bundle in Payload/ and zip it as an .ipa."""
    staging = app_path.parent / "_ipa_staging"
    payload = staging / "Payload"
    shutil.rmtree(staging, ignore_errors=True)
    payload.mkdir(parents=True, exist_ok=True)
    shutil.copytree(app_path, payload / app_path.name, symlinks=True)

    subprocess.run(
        ["zip", "-qry", str(out_ipa), "Payload"],
        cwd=str(staging),
        check=True,
    )
    shutil.rmtree(staging, ignore_errors=True)


def package_simulator_zip(app_path: Path, out_zip: Path) -> None:
    """Zip the iOS Simulator .app bundle for browser testing (e.g., Appetize.io)."""
    subprocess.run(
        ["zip", "-qry", str(out_zip), app_path.name],
        cwd=str(app_path.parent),
        check=True,
    )


def package_dmg(app_path: Path, out_dmg: Path, volume_name: str) -> None:
    """Create a compressed macOS .dmg disk image using hdiutil."""
    staging = app_path.parent / "_dmg_staging"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True, exist_ok=True)
    shutil.copytree(app_path, staging / app_path.name, symlinks=True)

    subprocess.run(
        [
            "hdiutil",
            "create",
            "-volname",
            volume_name,
            "-srcfolder",
            str(staging),
            "-ov",
            "-format",
            "UDZO",
            str(out_dmg),
        ],
        check=True,
    )
    shutil.rmtree(staging, ignore_errors=True)


def build_ios(
    project_root: Path,
    container_args: list[str],
    scheme: str,
    app_name: str,
    log_chunks: list[str],
) -> None:
    """Compile unsigned iOS device (.ipa) and iOS Simulator (.zip) artifacts."""
    shutil.rmtree(DD_IOS, ignore_errors=True)
    shutil.rmtree(DD_SIM, ignore_errors=True)

    run_cmd(
        [
            "xcodebuild",
            *container_args,
            "-scheme",
            scheme,
            "-destination",
            "generic/platform=iOS",
            "-configuration",
            "Release",
            "-derivedDataPath",
            str(DD_IOS),
            "CODE_SIGN_IDENTITY=",
            "CODE_SIGNING_REQUIRED=NO",
            "CODE_SIGNING_ALLOWED=NO",
            "build",
        ],
        project_root,
        log_chunks,
        "xcodebuild (iOS Device)",
    )
    ios_app = find_built_app(DD_IOS / "Build" / "Products" / "Release-iphoneos")
    package_ipa(ios_app, OUTPUT_DIR / f"{app_name}-iOS-unsigned.ipa")

    run_cmd(
        [
            "xcodebuild",
            *container_args,
            "-scheme",
            scheme,
            "-destination",
            "generic/platform=iOS Simulator",
            "-configuration",
            "Release",
            "-derivedDataPath",
            str(DD_SIM),
            "CODE_SIGN_IDENTITY=",
            "CODE_SIGNING_REQUIRED=NO",
            "CODE_SIGNING_ALLOWED=NO",
            "build",
        ],
        project_root,
        log_chunks,
        "xcodebuild (iOS Simulator)",
    )
    sim_app = find_built_app(DD_SIM / "Build" / "Products" / "Release-iphonesimulator")
    package_simulator_zip(sim_app, OUTPUT_DIR / f"{app_name}-iOS-Simulator.zip")


def build_macos(
    project_root: Path,
    container_args: list[str],
    scheme: str,
    app_name: str,
    log_chunks: list[str],
) -> None:
    """Compile unsigned macOS (.dmg) artifact."""
    shutil.rmtree(DD_MACOS, ignore_errors=True)

    run_cmd(
        [
            "xcodebuild",
            *container_args,
            "-scheme",
            scheme,
            "-destination",
            "generic/platform=macOS",
            "-configuration",
            "Release",
            "-derivedDataPath",
            str(DD_MACOS),
            "CODE_SIGN_IDENTITY=",
            "CODE_SIGNING_REQUIRED=NO",
            "CODE_SIGNING_ALLOWED=NO",
            "build",
        ],
        project_root,
        log_chunks,
        "xcodebuild (macOS)",
    )
    mac_app = find_built_app(DD_MACOS / "Build" / "Products" / "Release")
    package_dmg(mac_app, OUTPUT_DIR / f"{app_name}-macOS.dmg", app_name)


def main() -> None:
    zip_url = os.environ.get("ZIP_URL", "").strip()
    platform = os.environ.get("TARGET_PLATFORM", "ios").strip().lower()
    app_name = os.environ.get("APP_NAME", "MyCloudApp").strip() or "MyCloudApp"
    bundle_id = os.environ.get("BUNDLE_ID", "com.example.mycloudapp").strip() or "com.example.mycloudapp"

    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    log_chunks: list[str] = [f"# Cloud Swift Build Report\n\n- **Target Platform:** `{platform}`\n"]

    try:
        if not zip_url:
            raise BuildError("ZIP_URL environment variable is missing.")

        archive_path = WORKSPACE_DIR / "project.zip"
        extract_dir = WORKSPACE_DIR / "extracted"
        shutil.rmtree(extract_dir, ignore_errors=True)
        extract_dir.mkdir(parents=True, exist_ok=True)

        download_zip(zip_url, archive_path)
        safe_extract_zip(archive_path, extract_dir)
        clean_macos_junk(extract_dir)
        project_root = resolve_project_root(extract_dir)

        container_args, schemes = prepare_project(
            project_root, app_name, bundle_id, platform, log_chunks
        )

        # Prefer the scheme name for output filenames when Mode A/B is used
        out_name = app_name
        if platform in {"ios", "both"}:
            ios_scheme = schemes["ios"]
            if not (project_root / "project.yml").is_file() or app_name == "MyCloudApp":
                out_name = re.sub(r"[^A-Za-z0-9-]", "", ios_scheme) or app_name
            build_ios(project_root, container_args, ios_scheme, out_name, log_chunks)

        if platform in {"macos", "both"}:
            mac_scheme = schemes["macos"]
            if platform == "macos" and app_name == "MyCloudApp":
                out_name = re.sub(r"[^A-Za-z0-9-]", "", mac_scheme) or app_name
            build_macos(project_root, container_args, mac_scheme, out_name, log_chunks)

        append_report(log_chunks, "Result", "All requested targets compiled and packaged successfully.")
    except Exception as exc:
        append_report(log_chunks, "Build Error", str(exc))
        write_report(log_chunks)
        print(f"Build failed: {exc}", file=sys.stderr)
        sys.exit(1)

    write_report(log_chunks)
    print("Build completed successfully.")


if __name__ == "__main__":
    main()
