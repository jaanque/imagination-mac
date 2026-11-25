#!/usr/bin/env python3
"""Parse and validate GitHub Issue Form payloads for Cloud Swift Builder."""

from __future__ import annotations

import os
import re
import sys
from urllib.parse import urlparse

ALLOWED_HOSTS = {"github.com", "objects.githubusercontent.com"}
DEFAULT_APP_NAME = "MyCloudApp"
DEFAULT_BUNDLE_ID = "com.example.mycloudapp"


def write_github_output(outputs: dict[str, str]) -> None:
    """Write key-value pairs to $GITHUB_OUTPUT safely."""
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return

    with open(output_path, "a", encoding="utf-8") as fh:
        for key, value in outputs.items():
            clean_val = value.replace("\r", " ").replace("\n", " ").strip()
            fh.write(f"{key}={clean_val}\n")


def parse_issue_sections(body: str) -> dict[str, str]:
    """Split a GitHub Issue Form markdown body into heading -> content pairs."""
    sections: dict[str, list[str]] = {}
    current_heading: str | None = None

    for line in body.splitlines():
        heading_match = re.match(r"^###\s+(.+?)\s*$", line)
        if heading_match:
            current_heading = heading_match.group(1).strip().lower()
            sections[current_heading] = []
        elif current_heading is not None:
            sections[current_heading].append(line)

    return {k: "\n".join(v).strip() for k, v in sections.items()}


def is_allowed_zip_url(url: str) -> bool:
    """Verify URL uses HTTPS and points strictly to github.com or objects.githubusercontent.com."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return False

    if parsed.scheme.lower() != "https":
        return False
    if parsed.username is not None or parsed.password is not None:
        return False
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_HOSTS:
        return False
    if not parsed.path or parsed.path == "/":
        return False
    return True


def extract_zip_url(text: str) -> str | None:
    """Extract and validate a GitHub-hosted .zip attachment URL from issue text."""
    md_links = re.findall(r"\[[^\]]*\]\((https://[^\s)]+)\)", text)
    bare_urls = re.findall(r"(https://[^\s<>()\[\]\"']+)", text)

    candidates: list[str] = []
    for url in md_links + bare_urls:
        cleaned = url.rstrip(".,;:!?")
        if cleaned not in candidates:
            candidates.append(cleaned)

    for url in candidates:
        if is_allowed_zip_url(url):
            parsed = urlparse(url)
            if parsed.path.lower().endswith(".zip") or "/files/" in parsed.path.lower():
                return url
    return None


def normalize_platform(raw_value: str) -> str:
    """Normalize the platform dropdown value to 'ios', 'macos', or 'both'."""
    val = raw_value.strip().lower()
    if val.startswith("both") or ("ios" in val and "macos" in val):
        return "both"
    if val.startswith("macos") or "mac" in val:
        return "macos"
    if val.startswith("ios") or "ipa" in val:
        return "ios"
    return ""


def sanitize_identifier(raw_value: str, default: str, allow_dots: bool = True) -> str:
    """Keep only alphanumeric characters, hyphens, and optionally dots."""
    val = raw_value.strip()
    if not val or val == "_No response_":
        return default

    pattern = r"[^A-Za-z0-9.-]" if allow_dots else r"[^A-Za-z0-9-]"
    cleaned = re.sub(pattern, "", val).strip(".-")
    return cleaned or default


def fail(message: str) -> None:
    """Emit failure outputs and exit non-zero."""
    write_github_output({"valid": "false", "error_message": message})
    print(f"Validation error: {message}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    issue_body = os.environ.get("ISSUE_BODY", "")
    if not issue_body.strip():
        fail("Issue body is empty. Please use the Build Swift App issue form.")

    sections = parse_issue_sections(issue_body)
    zip_section = sections.get("project archive (.zip)", issue_body)
    zip_url = extract_zip_url(zip_section) or extract_zip_url(issue_body)

    if not zip_url:
        fail(
            "No valid GitHub .zip attachment URL found. Please drag and drop a .zip file "
            "hosted on github.com or objects.githubusercontent.com into the Project Archive field."
        )

    platform_raw = sections.get("target platform", "")
    platform = normalize_platform(platform_raw)
    if platform not in {"ios", "macos", "both"}:
        fail(f"Unsupported or missing target platform: '{platform_raw}'.")

    app_name = sanitize_identifier(
        sections.get("app name (optional)", ""),
        DEFAULT_APP_NAME,
        allow_dots=False,
    )
    bundle_id = sanitize_identifier(
        sections.get("bundle identifier (optional)", ""),
        DEFAULT_BUNDLE_ID,
        allow_dots=True,
    )

    write_github_output(
        {
            "valid": "true",
            "zip_url": zip_url,
            "platform": platform,
            "app_name": app_name,
            "bundle_id": bundle_id,
            "error_message": "",
        }
    )
    print(f"Validated build request: platform={platform}, app_name={app_name}, bundle_id={bundle_id}")


if __name__ == "__main__":
    main()
