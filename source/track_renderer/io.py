"""Write UTF-8 text or binary output by replacing its destination atomically."""

import os
import tempfile
from pathlib import Path


def write_file(path: str | Path, content: str | bytes) -> None:
    """@brief Write to a temporary file, then replace the destination in one step."""
    destination = Path(path)
    data = content.encode("utf-8") if isinstance(content, str) else content
    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            dir=destination.parent, prefix="." + destination.name, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
