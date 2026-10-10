"""Malware scanning (B39 / BPMN process 06).

Mock scanner until a real AV decision (future ADR): deterministic and
dependency-free. The interface (filename/content/size -> clean|quarantined)
is what a real engine will implement.
"""

QUARANTINE_MARKERS = ("virus", "eicar", "malware")


def scan_file(*, filename: str, content_type: str, size_bytes: int) -> str:
    name = (filename or "").lower()
    if any(marker in name for marker in QUARANTINE_MARKERS):
        return "quarantined"
    if size_bytes <= 0:
        return "quarantined"
    return "clean"
