"""Minimal dependency-free single-page PDF (Helvetica, Latin-1).

Persian glyphs are not rendered by the base-14 fonts; the Persian-formatted
invoice PDF is deferred to the UI phase (documented decision). Numbers and
codes (invoice number, amount, dates) are ASCII-safe.
"""


def simple_pdf(lines: list[str]) -> bytes:
    ops = ["BT", "/F1 12 Tf", "16 TL", "50 780 Td"]
    for line in lines:
        safe = "".join(ch if 32 <= ord(ch) < 127 else "?" for ch in line)
        safe = safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        ops.append(f"({safe}) Tj")
        ops.append("T*")
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1")

    def obj(num: int, body: str) -> bytes:
        return f"{num} 0 obj\n{body}\nendobj\n".encode("latin-1")

    objects = [
        obj(1, "<< /Type /Catalog /Pages 2 0 R >>"),
        obj(2, "<< /Type /Pages /Kids [3 0 R] /Count 1 >>"),
        obj(
            3,
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            "/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        ),
        obj(4, "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"),
        (
            b"5 0 obj\n<< /Length " + str(len(stream)).encode("latin-1")
            + b" >>\nstream\n" + stream + b"\nendstream\nendobj\n"
        ),
    ]

    out = b"%PDF-1.4\n"
    offsets: list[int] = []
    for o in objects:
        offsets.append(len(out))
        out += o
    xref_pos = len(out)
    xref = f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    for off in offsets:
        xref += f"{off:010d} 00000 n \n"
    out += xref.encode("latin-1")
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF"
    ).encode("latin-1")
    return out
