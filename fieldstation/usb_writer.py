import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


PACKAGE_SCHEMA_VERSION = 1
DANGEROUS_TARGETS = {
    Path("/"),
    Path("/etc"),
    Path("/usr"),
    Path("/bin"),
    Path("/sbin"),
    Path("/lib"),
    Path("/lib64"),
    Path("/opt"),
    Path("/opt/meshmon-companion"),
    Path("/home"),
}


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def validate_target(target_path, repo_root=None):
    if not target_path:
        raise ValueError("target_path is required")
    target = Path(str(target_path)).expanduser()
    if not target.exists():
        raise ValueError("target_path must exist")
    if not target.is_dir():
        raise ValueError("target_path must be a directory")
    resolved = target.resolve()
    repo = Path(repo_root).resolve() if repo_root else None
    if resolved in DANGEROUS_TARGETS:
        raise ValueError(f"Refusing dangerous target path: {resolved}")
    if repo and (resolved == repo or repo in resolved.parents):
        raise ValueError("Refusing to create USB package inside the source repository")
    for bad in DANGEROUS_TARGETS:
        if resolved == bad:
            raise ValueError(f"Refusing dangerous target path: {resolved}")
    return resolved


def package_name():
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"FieldStation-USB-{stamp}"


def create_package(target_path, files, included_categories, repo_root=None):
    target = validate_target(target_path, repo_root)
    package_dir = target / package_name()
    package_dir.mkdir(parents=False, exist_ok=False)
    written = []
    for relative, content in files.items():
        destination = safe_destination(package_dir, relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
        written.append(destination)
    checksums = checksums_for(package_dir, written)
    checksums_text = "\n".join(f"{digest}  {path}" for path, digest in checksums.items()) + "\n"
    (package_dir / "checksums.txt").write_text(checksums_text, encoding="utf-8")
    manifest = {
        "package_type": "FieldStation offline installer package",
        "schema_version": PACKAGE_SCHEMA_VERSION,
        "created_at": utc_now(),
        "included_categories": included_categories,
        "files": checksums,
        "notes": [
            "Folder package only; not a bootable USB image.",
            "No raw disk writes, formatting, or device erasing were performed.",
            "Real node send/receive still requires future adapter integration.",
        ],
    }
    (package_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    checksums = checksums_for(package_dir, [*written, package_dir / "manifest.json"])
    (package_dir / "checksums.txt").write_text(
        "\n".join(f"{digest}  {path}" for path, digest in checksums.items()) + "\n",
        encoding="utf-8",
    )
    return {"package_dir": str(package_dir), "files": checksums, "manifest": manifest}


def safe_destination(package_dir, relative):
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"Unsafe package path: {relative}")
    destination = (package_dir / rel).resolve()
    if package_dir.resolve() not in destination.parents and destination != package_dir.resolve():
        raise ValueError(f"Unsafe package path: {relative}")
    return destination


def checksums_for(package_dir, paths):
    results = {}
    base = package_dir.resolve()
    for path in sorted(paths):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        results[str(path.resolve().relative_to(base))] = digest
    return results


def verify_package(package_dir):
    root = Path(str(package_dir)).resolve()
    manifest = root / "checksums.txt"
    if not manifest.exists():
        raise ValueError("checksums.txt not found")
    results = []
    ok = True
    for raw in manifest.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        expected, relative = raw.split(None, 1)
        relative = relative.strip()
        path = safe_destination(root, relative)
        exists = path.exists()
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if exists else ""
        match = exists and actual == expected
        ok = ok and match
        results.append({"path": relative, "expected": expected, "actual": actual, "ok": match})
    return {"ok": ok, "files": results}


def looks_removable(path):
    resolved = Path(path).resolve()
    return str(resolved).startswith(("/media/", "/mnt/", "/run/media/"))
