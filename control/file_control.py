"""
Cortex AI — File Control Module
Full file-system intelligence layer for Cortex AI:
  - Create / Read / Write / Append with auto-versioning
  - Copy / Move / Rename with collision-safe naming
  - Safe Delete (Recycle Bin or fallback Cortex Trash) + Permanent Delete
  - Smart search — by name, extension, size, date, or content
  - Auto-organize — by file type or by date
  - Duplicate finder — SHA-256 hash based
  - Compression — zip / unzip / inspect archives
  - Metadata — size, timestamps, folder size, file counts
  - Recent-files audit trail
  - ASCII directory tree visualizer
  - Bulk rename (regex or sequential)
  - File comparison / diff
  - Backup & restore
  - Optional password-based encryption (cryptography)
  - Natural-language command dispatcher
"""

import os
import re
import json
import shutil
import hashlib
import zipfile
import difflib
import datetime
from typing import Optional

# ---------------------------------------------------------------------------
# Paths & Config
# ---------------------------------------------------------------------------

BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
DATA_DIR          = os.path.join(BASE_DIR, "..", "data")
TRASH_DIR         = os.path.join(DATA_DIR, "trash")
BACKUP_DIR        = os.path.join(DATA_DIR, "backups")
RECENT_FILES_LOG  = os.path.join(DATA_DIR, "recent_files.json")
TRASH_LOG         = os.path.join(DATA_DIR, "trash_log.json")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(TRASH_DIR, exist_ok=True)
os.makedirs(BACKUP_DIR, exist_ok=True)

EXTENSION_CATEGORIES: dict[str, list[str]] = {
    "Images":      [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".svg", ".webp", ".ico", ".tiff"],
    "Documents":   [".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".xls", ".xlsx", ".ppt", ".pptx", ".csv"],
    "Videos":      [".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm"],
    "Music":       [".mp3", ".wav", ".flac", ".aac", ".ogg", ".m4a"],
    "Archives":    [".zip", ".rar", ".7z", ".tar", ".gz", ".bz2"],
    "Code":        [".py", ".js", ".html", ".css", ".java", ".cpp", ".c", ".json", ".xml", ".sh", ".ps1", ".ts", ".jsx", ".tsx"],
    "Executables": [".exe", ".msi", ".bat", ".apk"],
}


# ---------------------------------------------------------------------------
# Internal Helpers
# ---------------------------------------------------------------------------

def _respond(msg: str) -> str:
    """Print and return a voice-friendly response."""
    print(f"  [FILE] {msg}")
    return msg


def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_json(path: str, default):
    if not os.path.exists(path):
        _save_json(path, default)
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return default


def _save_json(path: str, data) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def _human_size(size_bytes: float) -> str:
    """Convert raw bytes into a human-readable string."""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}" if unit != "B" else f"{int(size_bytes)} B"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def _hash_file(path: str, block_size: int = 65536) -> str:
    """SHA-256 hash of a file's contents — used for duplicate/identity checks."""
    hasher = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for block in iter(lambda: f.read(block_size), b""):
                hasher.update(block)
        return hasher.hexdigest()
    except (IOError, OSError):
        return ""


def _unique_path(dest: str) -> str:
    """Return a collision-free path by appending (1), (2)... if dest exists."""
    if not os.path.exists(dest):
        return dest
    base, ext = os.path.splitext(dest)
    counter = 1
    new_dest = f"{base} ({counter}){ext}"
    while os.path.exists(new_dest):
        counter += 1
        new_dest = f"{base} ({counter}){ext}"
    return new_dest


def _log_recent(path: str, action: str) -> None:
    """Record a file operation in the recent-activity audit trail."""
    recent = _load_json(RECENT_FILES_LOG, [])
    recent.insert(0, {"path": os.path.abspath(path), "action": action, "timestamp": _now()})
    _save_json(RECENT_FILES_LOG, recent[:100])


# ---------------------------------------------------------------------------
# 1. CREATE / READ / WRITE / APPEND
# ---------------------------------------------------------------------------

def create_file(path: str, content: str = "") -> str:
    """Create a new file. Fails safely if the file already exists."""
    try:
        parent = os.path.dirname(os.path.abspath(path)) or "."
        os.makedirs(parent, exist_ok=True)
        if os.path.exists(path):
            return _respond(f"File already exists: {path}. Use write_file() to overwrite.")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        _log_recent(path, "created")
        return _respond(f"File created: {path}")
    except Exception as e:
        return _respond(f"Create failed: {e}")


def read_file(path: str, max_chars: int = 3000) -> str:
    """Read and print a file's text content (truncated for very large files)."""
    if not os.path.exists(path):
        return _respond(f"File not found: {path}")
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read(max_chars)
        print(f"  [FILE] Contents of {path}:\n{content}")
        _log_recent(path, "read")
        return content
    except Exception as e:
        return _respond(f"Read failed: {e}")


def write_file(path: str, content: str, backup: bool = True) -> str:
    """Overwrite a file's content. Auto-backs up the previous version first."""
    try:
        if backup and os.path.exists(path):
            backup_file(path)
        parent = os.path.dirname(os.path.abspath(path)) or "."
        os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        _log_recent(path, "written")
        return _respond(f"File saved: {path}")
    except Exception as e:
        return _respond(f"Write failed: {e}")


def append_to_file(path: str, content: str) -> str:
    """Append text to the end of a file (creates it if missing)."""
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(content)
        _log_recent(path, "appended")
        return _respond(f"Content appended to: {path}")
    except Exception as e:
        return _respond(f"Append failed: {e}")


def create_folder(path: str) -> str:
    try:
        os.makedirs(path, exist_ok=True)
        return _respond(f"Folder created: {path}")
    except Exception as e:
        return _respond(f"Create folder failed: {e}")


# ---------------------------------------------------------------------------
# 2. COPY / MOVE / RENAME
# ---------------------------------------------------------------------------

def copy_file(src: str, dst: str) -> str:
    if not os.path.exists(src):
        return _respond(f"Source not found: {src}")
    try:
        if os.path.isdir(dst):
            dst = os.path.join(dst, os.path.basename(src))
        dst = _unique_path(dst)
        shutil.copy2(src, dst)
        _log_recent(dst, "copied")
        return _respond(f"Copied to: {dst}")
    except Exception as e:
        return _respond(f"Copy failed: {e}")


def copy_folder(src: str, dst: str) -> str:
    if not os.path.isdir(src):
        return _respond(f"Source folder not found: {src}")
    try:
        if os.path.exists(dst):
            dst = _unique_path(dst)
        shutil.copytree(src, dst)
        return _respond(f"Folder copied to: {dst}")
    except Exception as e:
        return _respond(f"Copy folder failed: {e}")


def move_file(src: str, dst: str) -> str:
    if not os.path.exists(src):
        return _respond(f"Source not found: {src}")
    try:
        if os.path.isdir(dst):
            dst = os.path.join(dst, os.path.basename(src))
        dst = _unique_path(dst)
        shutil.move(src, dst)
        _log_recent(dst, "moved")
        return _respond(f"Moved to: {dst}")
    except Exception as e:
        return _respond(f"Move failed: {e}")


def rename_file(path: str, new_name: str) -> str:
    if not os.path.exists(path):
        return _respond(f"Not found: {path}")
    try:
        new_path = _unique_path(os.path.join(os.path.dirname(path), new_name))
        os.rename(path, new_path)
        _log_recent(new_path, "renamed")
        return _respond(f"Renamed to: {new_path}")
    except Exception as e:
        return _respond(f"Rename failed: {e}")


# ---------------------------------------------------------------------------
# 3. DELETE — SAFE (TRASH) & PERMANENT
# ---------------------------------------------------------------------------

def safe_delete(path: str) -> str:
    """
    Move a file to the OS Recycle Bin (via send2trash if installed),
    or fall back to a local Cortex Trash folder with full restore support.
    """
    if not os.path.exists(path):
        return _respond(f"Not found: {path}")
    try:
        from send2trash import send2trash
        send2trash(os.path.abspath(path))
        _log_recent(path, "trashed")
        return _respond(f"Moved to Recycle Bin: {path}")
    except ImportError:
        try:
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S%f")
            trashed_path = os.path.join(TRASH_DIR, f"{ts}_{os.path.basename(path)}")
            shutil.move(path, trashed_path)

            trash_log = _load_json(TRASH_LOG, [])
            trash_log.append({
                "id":            (trash_log[-1]["id"] + 1) if trash_log else 1,
                "original_path": os.path.abspath(path),
                "trashed_path":  trashed_path,
                "deleted_at":    _now(),
            })
            _save_json(TRASH_LOG, trash_log)
            _log_recent(path, "trashed")
            return _respond(f"Moved to Cortex Trash: {path}  (install send2trash for native Recycle Bin support)")
        except Exception as e:
            return _respond(f"Delete failed: {e}")
    except Exception as e:
        return _respond(f"Delete failed: {e}")


def list_trash() -> list:
    trash_log = _load_json(TRASH_LOG, [])
    if not trash_log:
        _respond("Cortex Trash is empty.")
        return []
    print("  [FILE] Cortex Trash:")
    for item in trash_log:
        print(f"    [{item['id']}] {item['original_path']}  (deleted {item['deleted_at']})")
    return trash_log


def restore_from_trash(item_id: int) -> str:
    trash_log = _load_json(TRASH_LOG, [])
    for item in trash_log:
        if item["id"] == item_id:
            if os.path.exists(item["trashed_path"]):
                dest = _unique_path(item["original_path"])
                shutil.move(item["trashed_path"], dest)
                trash_log.remove(item)
                _save_json(TRASH_LOG, trash_log)
                return _respond(f"Restored: {dest}")
            return _respond("That trashed file no longer exists on disk.")
    return _respond(f"Trash item {item_id} not found.")


def empty_trash(confirm: bool = False) -> str:
    if not confirm:
        return _respond("To permanently empty trash, call empty_trash(confirm=True). This cannot be undone.")
    shutil.rmtree(TRASH_DIR, ignore_errors=True)
    os.makedirs(TRASH_DIR, exist_ok=True)
    _save_json(TRASH_LOG, [])
    return _respond("Cortex Trash emptied permanently.")


def permanent_delete(path: str, confirm: bool = True) -> str:
    """Delete a file or folder immediately — bypasses trash entirely."""
    if not os.path.exists(path):
        return _respond(f"Not found: {path}")
    if confirm:
        answer = input(f"    Permanently delete '{path}'? This cannot be undone. (yes/no): ")
        if answer.lower() != "yes":
            return _respond("Deletion cancelled.")
    try:
        if os.path.isfile(path):
            os.remove(path)
        else:
            shutil.rmtree(path)
        _log_recent(path, "permanently deleted")
        return _respond(f"Permanently deleted: {path}")
    except Exception as e:
        return _respond(f"Delete failed: {e}")


# ---------------------------------------------------------------------------
# 4. SMART SEARCH
# ---------------------------------------------------------------------------

def find_files(query: str, path: str = ".", search_content: bool = False) -> list:
    """Search filenames (and optionally text content) for a query string."""
    matches = []
    query_lower = query.lower()
    for root, _, files in os.walk(path):
        for name in files:
            full = os.path.join(root, name)
            if query_lower in name.lower():
                matches.append(full)
            elif search_content:
                try:
                    with open(full, "r", encoding="utf-8", errors="ignore") as f:
                        if query_lower in f.read().lower():
                            matches.append(full)
                except (IOError, OSError):
                    continue
    print(f"  [FILE] Found {len(matches)} match(es) for '{query}':")
    for m in matches[:20]:
        print(f"    - {m}")
    return matches


def find_by_extension(ext: str, path: str = ".") -> list:
    ext = ext if ext.startswith(".") else "." + ext
    matches = [
        os.path.join(root, name)
        for root, _, files in os.walk(path)
        for name in files if name.lower().endswith(ext.lower())
    ]
    print(f"  [FILE] Found {len(matches)} '{ext}' file(s).")
    return matches


def find_by_size(path: str = ".", min_mb: float = None, max_mb: float = None) -> list:
    matches = []
    for root, _, files in os.walk(path):
        for name in files:
            full = os.path.join(root, name)
            try:
                size_mb = os.path.getsize(full) / (1024 * 1024)
            except OSError:
                continue
            if (min_mb is None or size_mb >= min_mb) and (max_mb is None or size_mb <= max_mb):
                matches.append((full, round(size_mb, 2)))
    print(f"  [FILE] Found {len(matches)} file(s) matching the size range.")
    return matches


def find_by_date(path: str = ".", after: str = None, before: str = None) -> list:
    """Dates in 'YYYY-MM-DD' format. Filters by last-modified time."""
    after_dt  = datetime.datetime.strptime(after, "%Y-%m-%d") if after else None
    before_dt = datetime.datetime.strptime(before, "%Y-%m-%d") if before else None
    matches = []
    for root, _, files in os.walk(path):
        for name in files:
            full = os.path.join(root, name)
            try:
                mtime = datetime.datetime.fromtimestamp(os.path.getmtime(full))
            except OSError:
                continue
            if (after_dt is None or mtime >= after_dt) and (before_dt is None or mtime <= before_dt):
                matches.append(full)
    print(f"  [FILE] Found {len(matches)} file(s) in that date range.")
    return matches


def find_large_files(path: str = ".", top: int = 10) -> list:
    all_files = []
    for root, _, files in os.walk(path):
        for name in files:
            full = os.path.join(root, name)
            try:
                all_files.append((full, os.path.getsize(full)))
            except OSError:
                continue
    all_files.sort(key=lambda x: x[1], reverse=True)
    top_files = all_files[:top]
    print(f"  [FILE] Top {len(top_files)} largest files:")
    for f, s in top_files:
        print(f"    {_human_size(s):>10}  {f}")
    return top_files


# ---------------------------------------------------------------------------
# 5. AUTO-ORGANIZE
# ---------------------------------------------------------------------------

def _category_for(ext: str) -> str:
    ext = ext.lower()
    for category, extensions in EXTENSION_CATEGORIES.items():
        if ext in extensions:
            return category
    return "Others"


def organize_folder(path: str = ".") -> str:
    """Sort top-level files in a folder into category subfolders by type."""
    if not os.path.isdir(path):
        return _respond(f"Folder not found: {path}")

    moved = 0
    for name in os.listdir(path):
        full = os.path.join(path, name)
        if os.path.isdir(full) or name.startswith("."):
            continue

        category = _category_for(os.path.splitext(name)[1])
        category_folder = os.path.join(path, category)
        os.makedirs(category_folder, exist_ok=True)

        dest = _unique_path(os.path.join(category_folder, name))
        shutil.move(full, dest)
        moved += 1

    return _respond(f"Organized {moved} file(s) into categories.")


def organize_by_date(path: str = ".") -> str:
    """Sort top-level files into YYYY-MM subfolders by last-modified date."""
    if not os.path.isdir(path):
        return _respond(f"Folder not found: {path}")

    moved = 0
    for name in os.listdir(path):
        full = os.path.join(path, name)
        if os.path.isdir(full) or name.startswith("."):
            continue

        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(full))
        dest_folder = os.path.join(path, mtime.strftime("%Y-%m"))
        os.makedirs(dest_folder, exist_ok=True)

        dest = _unique_path(os.path.join(dest_folder, name))
        shutil.move(full, dest)
        moved += 1

    return _respond(f"Organized {moved} file(s) into monthly folders.")


# ---------------------------------------------------------------------------
# 6. DUPLICATE FINDER
# ---------------------------------------------------------------------------

def find_duplicates(path: str = ".") -> dict:
    """Group files by content hash — anything with 2+ entries is a duplicate set."""
    hash_map: dict[str, list[str]] = {}
    for root, _, files in os.walk(path):
        for name in files:
            full = os.path.join(root, name)
            h = _hash_file(full)
            if h:
                hash_map.setdefault(h, []).append(full)

    duplicates = {h: paths for h, paths in hash_map.items() if len(paths) > 1}
    if duplicates:
        print(f"  [FILE] Found {len(duplicates)} set(s) of duplicates:")
        for h, paths in duplicates.items():
            print(f"    Hash {h[:10]}...:")
            for p in paths:
                print(f"      - {p}")
    else:
        print("  [FILE] No duplicate files found.")
    return duplicates


def remove_duplicates(path: str = ".", keep: str = "first") -> str:
    """Keep one copy of each duplicate set (first or last alphabetically) and trash the rest."""
    duplicates = find_duplicates(path)
    removed = []
    for _, paths in duplicates.items():
        sorted_paths = sorted(paths)
        to_keep = sorted_paths[0] if keep == "first" else sorted_paths[-1]
        for p in sorted_paths:
            if p != to_keep:
                safe_delete(p)
                removed.append(p)
    return _respond(f"Removed {len(removed)} duplicate file(s), kept the originals.")


# ---------------------------------------------------------------------------
# 7. COMPRESSION
# ---------------------------------------------------------------------------

def zip_files(paths: list, output_zip: str) -> str:
    try:
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in paths:
                if os.path.exists(p):
                    zf.write(p, os.path.basename(p))
        return _respond(f"Created archive: {output_zip}")
    except Exception as e:
        return _respond(f"Zip failed: {e}")


def zip_folder(folder_path: str, output_zip: str = None) -> str:
    if not os.path.isdir(folder_path):
        return _respond(f"Folder not found: {folder_path}")
    if not output_zip:
        output_zip = folder_path.rstrip("/\\") + ".zip"
    try:
        with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, _, files in os.walk(folder_path):
                for name in files:
                    full = os.path.join(root, name)
                    arcname = os.path.relpath(full, os.path.dirname(folder_path)).replace(os.sep, "/")
                    zf.write(full, arcname)
        return _respond(f"Folder compressed: {output_zip}")
    except Exception as e:
        return _respond(f"Zip failed: {e}")


def unzip_file(zip_path: str, extract_to: str = ".") -> str:
    if not os.path.exists(zip_path):
        return _respond(f"Zip file not found: {zip_path}")
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(extract_to)
        return _respond(f"Extracted to: {extract_to}")
    except zipfile.BadZipFile:
        return _respond("Invalid or corrupted zip file.")
    except Exception as e:
        return _respond(f"Unzip failed: {e}")


def list_zip_contents(zip_path: str) -> list:
    if not os.path.exists(zip_path):
        return []
    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
        print(f"  [FILE] Contents of {zip_path}:")
        for n in names:
            print(f"    - {n}")
        return names
    except Exception as e:
        print(f"  [FILE] Error reading zip: {e}")
        return []


# ---------------------------------------------------------------------------
# 8. METADATA & INFO
# ---------------------------------------------------------------------------

def get_file_info(path: str) -> dict:
    if not os.path.exists(path):
        _respond(f"Not found: {path}")
        return {}
    stat = os.stat(path)
    info = {
        "path":         os.path.abspath(path),
        "size":         _human_size(stat.st_size),
        "size_bytes":   stat.st_size,
        "created":      datetime.datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S"),
        "modified":     datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        "accessed":     datetime.datetime.fromtimestamp(stat.st_atime).strftime("%Y-%m-%d %H:%M:%S"),
        "is_directory": os.path.isdir(path),
        "extension":    os.path.splitext(path)[1],
    }
    print(f"  [FILE] Info for {path}:")
    for k, v in info.items():
        print(f"    {k}: {v}")
    return info


def get_folder_size(path: str) -> str:
    total = 0
    for root, _, files in os.walk(path):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(root, name))
            except OSError:
                continue
    return _respond(f"Folder size: {_human_size(total)}")


def count_files(path: str = ".", extension: str = None) -> int:
    count = 0
    for _, _, files in os.walk(path):
        for name in files:
            if extension is None or name.lower().endswith(extension.lower()):
                count += 1
    suffix = f" with extension '{extension}'" if extension else ""
    _respond(f"{count} file(s) found{suffix}.")
    return count


# ---------------------------------------------------------------------------
# 9. RECENT FILES & STORAGE SUMMARY
# ---------------------------------------------------------------------------

def get_recent_files(n: int = 10) -> list:
    recent = _load_json(RECENT_FILES_LOG, [])[:n]
    print(f"  [FILE] Last {len(recent)} file operation(s):")
    for r in recent:
        print(f"    [{r['timestamp']}] {r['action']:<20} {r['path']}")
    return recent


def clear_recent_files() -> str:
    _save_json(RECENT_FILES_LOG, [])
    return _respond("Recent files log cleared.")


def get_storage_summary() -> str:
    recent  = _load_json(RECENT_FILES_LOG, [])
    trash   = _load_json(TRASH_LOG, [])
    backups = os.listdir(BACKUP_DIR) if os.path.exists(BACKUP_DIR) else []
    print("\n  [FILE] ── Storage Summary ──")
    print(f"    Recent operations logged: {len(recent)}")
    print(f"    Items in Cortex Trash:    {len(trash)}")
    print(f"    Backups stored:           {len(backups)}")
    return _respond("Storage summary complete.")


# ---------------------------------------------------------------------------
# 10. DIRECTORY TREE VISUALIZER
# ---------------------------------------------------------------------------

def get_directory_tree(path: str = ".", max_depth: int = 3, _prefix: str = "", _depth: int = 0) -> str:
    """Print and return an ASCII tree of a folder's structure."""
    if _depth == 0:
        print(f"  [FILE] Directory tree for: {os.path.abspath(path)}")
        print(f"  {os.path.basename(os.path.abspath(path)) or path}/")

    if _depth >= max_depth:
        return ""

    try:
        entries = sorted(e for e in os.listdir(path) if not e.startswith("."))
    except (PermissionError, FileNotFoundError):
        return ""

    lines = []
    for i, entry in enumerate(entries):
        full = os.path.join(path, entry)
        connector = "└── " if i == len(entries) - 1 else "├── "
        is_dir = os.path.isdir(full)
        line = f"  {_prefix}{connector}{entry}{'/' if is_dir else ''}"
        print(line)
        lines.append(line)
        if is_dir:
            extension = "    " if i == len(entries) - 1 else "│   "
            lines.append(get_directory_tree(full, max_depth, _prefix + extension, _depth + 1))

    return "\n".join(filter(None, lines))


# ---------------------------------------------------------------------------
# 11. BULK OPERATIONS
# ---------------------------------------------------------------------------

def bulk_rename(folder: str, pattern: str, replacement: str) -> str:
    """Regex-based bulk rename — e.g. pattern=r'IMG_(\\d+)', replacement=r'Photo_\\1'."""
    if not os.path.isdir(folder):
        return _respond(f"Folder not found: {folder}")
    count = 0
    for name in os.listdir(folder):
        full = os.path.join(folder, name)
        if os.path.isfile(full) and re.search(pattern, name):
            new_name = re.sub(pattern, replacement, name)
            new_path = _unique_path(os.path.join(folder, new_name))
            os.rename(full, new_path)
            count += 1
    return _respond(f"Renamed {count} file(s).")


def bulk_rename_sequential(folder: str, prefix: str, extension_filter: str = None) -> str:
    """Rename all matching files to prefix_1.ext, prefix_2.ext, ..."""
    if not os.path.isdir(folder):
        return _respond(f"Folder not found: {folder}")
    files = sorted(f for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f)))
    if extension_filter:
        files = [f for f in files if f.lower().endswith(extension_filter.lower())]

    count = 0
    for i, name in enumerate(files, 1):
        full = os.path.join(folder, name)
        ext = os.path.splitext(name)[1]
        new_path = _unique_path(os.path.join(folder, f"{prefix}_{i}{ext}"))
        os.rename(full, new_path)
        count += 1
    return _respond(f"Renamed {count} file(s) sequentially with prefix '{prefix}'.")


def bulk_move(file_list: list, destination: str) -> str:
    os.makedirs(destination, exist_ok=True)
    moved = 0
    for f in file_list:
        if os.path.exists(f):
            dest = _unique_path(os.path.join(destination, os.path.basename(f)))
            shutil.move(f, dest)
            moved += 1
    return _respond(f"Moved {moved} file(s) to {destination}.")


# ---------------------------------------------------------------------------
# 12. FILE COMPARISON
# ---------------------------------------------------------------------------

def compare_files(path1: str, path2: str) -> str:
    """Print a unified diff between two text files."""
    if not (os.path.exists(path1) and os.path.exists(path2)):
        return _respond("One or both files were not found.")
    try:
        with open(path1, "r", encoding="utf-8", errors="ignore") as f1, \
             open(path2, "r", encoding="utf-8", errors="ignore") as f2:
            diff = list(difflib.unified_diff(
                f1.readlines(), f2.readlines(),
                fromfile=path1, tofile=path2, lineterm=""
            ))
        if diff:
            print("  [FILE] Differences found:")
            for line in diff[:50]:
                print(f"    {line}")
            return f"Found {len(diff)} differing line(s)."
        return _respond("Files are identical in content.")
    except Exception as e:
        return _respond(f"Comparison failed: {e}")


def files_are_identical(path1: str, path2: str) -> bool:
    """Fast byte-identity check via hash comparison."""
    if not (os.path.exists(path1) and os.path.exists(path2)):
        _respond("One or both files were not found.")
        return False
    identical = _hash_file(path1) == _hash_file(path2)
    _respond(f"Files are {'identical' if identical else 'different'}.")
    return identical


# ---------------------------------------------------------------------------
# 13. BACKUP & RESTORE
# ---------------------------------------------------------------------------

def backup_file(path: str) -> str:
    if not os.path.exists(path):
        return _respond(f"File not found: {path}")
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join(BACKUP_DIR, f"{ts}_{os.path.basename(path)}")
    shutil.copy2(path, backup_path)
    return _respond(f"Backed up to: {backup_path}")


def list_backups() -> list:
    backups = sorted(os.listdir(BACKUP_DIR), reverse=True) if os.path.exists(BACKUP_DIR) else []
    print(f"  [FILE] {len(backups)} backup(s) found:")
    for b in backups[:20]:
        print(f"    - {b}")
    return backups


def restore_backup(filename: str, restore_to: str = None) -> str:
    backup_path = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(backup_path):
        return _respond(f"Backup not found: {filename}")
    if not restore_to:
        parts = filename.split("_", 2)
        restore_to = parts[2] if len(parts) == 3 else filename
    shutil.copy2(backup_path, restore_to)
    return _respond(f"Restored to: {restore_to}")


# ---------------------------------------------------------------------------
# 14. ENCRYPTION (Optional — requires `cryptography`)
# ---------------------------------------------------------------------------

def encrypt_file(path: str, password: str) -> str:
    """Password-encrypt a file using PBKDF2 + Fernet. Produces path + '.enc'."""
    if not os.path.exists(path):
        return _respond(f"File not found: {path}")
    try:
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        import base64

        salt = os.urandom(16)
        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=390000)
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        fernet = Fernet(key)

        with open(path, "rb") as f:
            data = f.read()
        encrypted = fernet.encrypt(data)

        enc_path = path + ".enc"
        with open(enc_path, "wb") as f:
            f.write(salt + encrypted)

        return _respond(f"Encrypted: {enc_path}")
    except ImportError:
        return _respond("Install cryptography: pip install cryptography")
    except Exception as e:
        return _respond(f"Encryption failed: {e}")


def decrypt_file(path: str, password: str, output_path: str = None) -> str:
    """Decrypt a file created by encrypt_file(). Wrong password fails safely."""
    if not os.path.exists(path):
        return _respond(f"File not found: {path}")
    try:
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
        import base64

        with open(path, "rb") as f:
            raw = f.read()
        salt, encrypted = raw[:16], raw[16:]

        kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=390000)
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        decrypted = Fernet(key).decrypt(encrypted)

        if not output_path:
            output_path = path[:-4] if path.endswith(".enc") else path + ".dec"
        with open(output_path, "wb") as f:
            f.write(decrypted)

        return _respond(f"Decrypted: {output_path}")
    except ImportError:
        return _respond("Install cryptography: pip install cryptography")
    except Exception as e:
        return _respond(f"Decryption failed — wrong password or corrupted file: {e}")


# ---------------------------------------------------------------------------
# 15. COMMAND DISPATCHER — Natural Language Interface
# ---------------------------------------------------------------------------

def handle_file_command(user_input: str) -> str:
    """
    Main entry point — called from main.py for file-related commands.
    Matches natural language to the correct file operation.
    """
    text = user_input.lower().strip()

    if any(p in text for p in ["show recent files", "recent files", "recent activity"]):
        get_recent_files()
        return "Here are your recent file operations."

    if any(p in text for p in ["find duplicates", "duplicate files", "show duplicates"]):
        find_duplicates(".")
        return "Duplicate scan complete."

    if any(p in text for p in ["directory tree", "show tree", "folder structure"]):
        get_directory_tree(".")
        return "Here is the directory tree."

    if any(p in text for p in ["show trash", "list trash", "what's in trash"]):
        list_trash()
        return "Here is your trash."

    if "empty trash" in text:
        return empty_trash(confirm=True)

    if any(p in text for p in ["storage summary", "storage report"]):
        return get_storage_summary()

    if any(p in text for p in ["largest files", "biggest files"]):
        find_large_files(".")
        return "Here are your largest files."

    if any(p in text for p in ["organize downloads", "clean downloads"]):
        return organize_folder(os.path.join(os.path.expanduser("~"), "Downloads"))

    if text.startswith("organize "):
        return organize_folder(user_input[len("organize "):].strip())

    match = re.search(r"(?:create|make)\s+file\s+(.+)", text)
    if match:
        return create_file(match.group(1).strip())

    match = re.search(r"(?:create|make|new)\s+folder\s+(.+)", text)
    if match:
        return create_folder(match.group(1).strip())

    match = re.search(r"(?:delete|remove|trash)\s+(?:file\s+)?(.+)", text)
    if match:
        return safe_delete(match.group(1).strip())

    match = re.search(r"(?:read|open)\s+file\s+(.+)", text)
    if match:
        return read_file(match.group(1).strip())

    match = re.search(r"(?:search for|find)\s+(.+)", text)
    if match:
        find_files(match.group(1).strip())
        return "Search complete."

    return _respond(f"No file command matched: '{user_input}'")


# ---------------------------------------------------------------------------
# Quick Test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("\n" + "="*55)
    print("   Cortex AI — File Control Test")
    print("="*55 + "\n")

    test_root = os.path.join(os.getcwd(), "cortex_file_test_playground")
    if os.path.exists(test_root):
        shutil.rmtree(test_root)
    os.makedirs(test_root)

    # ---- CRUD ----
    print("--- CRUD ---")
    f1 = os.path.join(test_root, "notes.txt")
    print(create_file(f1, "Hello Cortex AI\n"))
    print(append_to_file(f1, "Second line.\n"))
    read_file(f1)
    find_files("Cortex", test_root, search_content=True)

    # ---- Copy / Move / Rename ----
    print("\n--- Copy / Move / Rename ---")
    f2 = os.path.join(test_root, "notes_copy.txt")
    print(copy_file(f1, f2))
    print(rename_file(f2, "renamed_notes.txt"))

    # ---- Metadata ----
    print("\n--- Metadata ---")
    get_file_info(f1)
    get_folder_size(test_root)
    count_files(test_root)

    # ---- Backup & Compare ----
    print("\n--- Backup & Compare ---")
    print(backup_file(f1))
    list_backups()
    files_are_identical(f1, f1)

    # ---- Encryption ----
    print("\n--- Encryption ---")
    secret = os.path.join(test_root, "secret.txt")
    create_file(secret, "Top secret Cortex data")
    enc = encrypt_file(secret, "mypassword123")
    if os.path.exists(secret + ".enc"):
        decrypted_out = os.path.join(test_root, "secret_decrypted.txt")
        decrypt_file(secret + ".enc", "mypassword123", output_path=decrypted_out)
        read_file(decrypted_out)

    # ---- Organize & Duplicates (isolated folder) ----
    print("\n--- Organize & Duplicates ---")
    organize_dir = os.path.join(test_root, "messy_folder")
    os.makedirs(organize_dir, exist_ok=True)
    open(os.path.join(organize_dir, "photo.jpg"), "w").write("fake image data")
    open(os.path.join(organize_dir, "photo_copy.jpg"), "w").write("fake image data")
    open(os.path.join(organize_dir, "song.mp3"), "w").write("fake audio data")
    open(os.path.join(organize_dir, "script.py"), "w").write("print('hi')")

    find_files("photo", organize_dir)
    find_by_extension(".py", organize_dir)
    find_large_files(organize_dir, top=3)
    find_duplicates(organize_dir)

    get_directory_tree(organize_dir)
    print(organize_folder(organize_dir))
    get_directory_tree(organize_dir)

    # ---- Compression ----
    print("\n--- Compression ---")
    zip_path = os.path.join(test_root, "archive.zip")
    print(zip_folder(os.path.join(organize_dir, "Images"), zip_path))
    list_zip_contents(zip_path)
    print(unzip_file(zip_path, os.path.join(test_root, "extracted")))

    # ---- Bulk Rename ----
    print("\n--- Bulk Rename ---")
    bulk_dir = os.path.join(test_root, "bulk_test")
    os.makedirs(bulk_dir, exist_ok=True)
    for i in range(3):
        open(os.path.join(bulk_dir, f"IMG_000{i}.txt"), "w").write("x")
    print(bulk_rename_sequential(bulk_dir, prefix="Vacation"))
    get_directory_tree(bulk_dir)

    # ---- Recent Files & Summary ----
    print("\n--- Recent Files & Summary ---")
    get_recent_files(5)
    get_storage_summary()

    # ---- Trash ----
    print("\n--- Trash ---")
    print(safe_delete(f1))
    list_trash()

    # ---- Dispatcher ----
    print("\n--- Dispatcher Tests ---\n")
    for cmd in ["show recent files", "find duplicates", "storage summary", "unknown gibberish command"]:
        print(f"  > {cmd}")
        handle_file_command(cmd)
        print()

    # Cleanup
    shutil.rmtree(test_root, ignore_errors=True)
    print("\n File Control Test Complete!")