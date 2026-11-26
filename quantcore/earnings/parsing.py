"""HTML/PDF text and conservative speaker/Q&A separation; no fabricated attribution."""

import hashlib
import io
import re
from html.parser import HTMLParser


class HTMLText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self.blocked = 0
        self.links = []
        self.link = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ("script", "style", "noscript"):
            self.blocked += 1
        if tag in ("p", "div", "br", "h1", "h2", "h3", "tr", "li"):
            self.parts.append("\n")
        if tag == "a" and attrs.get("href"):
            self.link = [attrs["href"], attrs.get("title", "") + " " + attrs.get("aria-label", "")]

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.blocked = max(0, self.blocked - 1)
        if tag == "a" and self.link:
            self.links.append(tuple(self.link))
            self.link = None

    def handle_data(self, data):
        if not self.blocked:
            self.parts.append(data)
        if self.link:
            self.link[1] += data


def extract(raw, content_type):
    if raw.startswith(b"%PDF"):
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(raw))
        if reader.is_encrypted or len(reader.pages) > 100:
            raise ValueError("encrypted/oversized earnings PDF unsupported")
        text = "\n".join(p.extract_text(extraction_mode="layout") or "" for p in reader.pages)
    else:
        parser = HTMLText()
        parser.feed(raw.decode("utf-8", errors="replace"))
        text = "".join(parser.parts)
    lines = [" ".join(line.split()) for line in text.splitlines()]
    text = "\n".join(line for line in lines if line)
    if len(text) < 200:
        raise ValueError("no usable earnings text; no OCR/generated replacement")
    return text


def segments(text, kind):
    speaker, role, section = None, "unknown", "prepared" if kind == "transcript" else "release"
    output = []
    buffer = []

    def flush():
        nonlocal buffer
        if buffer:
            content = "\n".join(buffer)
            # Stable text-sized chunks preserve attribution and never invent speech times.
            for start in range(0, len(content), 5000):
                part = content[start : start + 5000]
                output.append(
                    {
                        "id": hashlib.sha256((str(len(output)) + part).encode()).hexdigest()[:16],
                        "speaker": speaker,
                        "role": role,
                        "section": section,
                        "text": part,
                        "spoken_at": None,
                    }
                )
            buffer = []

    for line in text.splitlines():
        if kind == "earnings_release":
            attributed = re.search(
                r"”[,.]?\s+(?:said|says)\s+([A-Z][A-Za-z .’\'-]{2,60}),\s*(.{2,160})", line
            )
            if attributed:
                flush()
                speaker = attributed[1].strip()
                title = attributed[2]
                role = (
                    "ceo"
                    if re.search(r"Chief Executive|\bCEO\b", title, re.I)
                    else "cfo"
                    if re.search(r"Chief Financial|\bCFO\b", title, re.I)
                    else "management"
                )
                buffer.append(line)
                flush()
                speaker, role = None, "unknown"
                continue
        if re.search(r"QUESTION.AND.ANSWER|QUESTIONS AND ANSWERS|Q&A", line, re.I):
            flush()
            section = "qa"
        # Typical official/FactSet speaker lines: "Jensen Huang - President & CEO" or standalone "Operator".
        match = re.match(r"^([A-Z][A-Za-z .’\'-]{2,65})\s*[-–|]\s*(.{2,160})$", line)
        if kind == "transcript" and (match or line in ("Operator", "QUESTION AND ANSWER SECTION")):
            flush()
            if match:
                speaker = match[1].strip()
                title = match[2]
                role = (
                    "ceo"
                    if re.search(r"Chief Executive|\bCEO\b", title, re.I)
                    else "cfo"
                    if re.search(r"Chief Financial|\bCFO\b", title, re.I)
                    else "analyst"
                    if re.search(r"Analyst|Research", title, re.I)
                    else "management"
                    if re.search(r"President|Vice|Officer|Relations|Director", title, re.I)
                    else "unknown"
                )
            elif line == "Operator":
                speaker, role = "Operator", "operator"
        else:
            buffer.append(line)
    flush()
    return output
