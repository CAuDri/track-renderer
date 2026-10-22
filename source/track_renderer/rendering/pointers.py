"""Build source JSON Pointers consistently for object IDs and diagnostics.

Object names may contain slashes or tildes. Escaping them here keeps ownership
lookups and source links aligned with the pointers produced by Track Description.
"""


def pointer(path: str, key: str) -> str:
    """@return The child pointer with the object's key escaped as one path segment."""
    return path + "/" + key.replace("~", "~0").replace("/", "~1")
