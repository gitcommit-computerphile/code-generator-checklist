from datetime import datetime
from pathlib import Path

LANGUAGE_EXTENSIONS = {
    "python": "py",
    "javascript": "js",
    "typescript": "ts",
    "java": "java",
    "c": "c",
    "cpp": "cpp",
    "c++": "cpp",
    "csharp": "cs",
    "c#": "cs",
    "go": "go",
    "rust": "rs",
    "ruby": "rb",
    "php": "php",
    "bash": "sh",
    "shell": "sh",
    "sql": "sql",
    "html": "html",
    "css": "css",
    "json": "json",
    "yaml": "yaml",
}


def save_code_to_disk(directory: str, language: str, code: str) -> Path:
    """Write code to a timestamped file inside `directory`, creating it if needed.

    `directory` is expected to be a path the user chose explicitly (e.g. typed into
    the UI), so creating it is expected rather than surprising.
    """
    ext = LANGUAGE_EXTENSIONS.get(language.lower(), "txt")
    target_dir = Path(directory).expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = f"snippet_{datetime.now():%Y%m%d_%H%M%S}.{ext}"
    file_path = target_dir / filename
    file_path.write_text(code, encoding="utf-8")
    return file_path