"""Write toc_pages.json: the page of every heading, read from Word-made PDFs of the manuals.

    <python with python-docx and pymupdf> docs/manual/toc_pages.py EN.pdf FR.pdf

build_manual.py then writes these page numbers into the contents page, so the .docx is complete
without Word having to refresh it. Re-run (build -> PDF -> this -> build) after changing the text.
"""
import json
import os
import re
import sys

import fitz  # pymupdf

import build_manual as bm

HERE = os.path.dirname(os.path.abspath(__file__))


def norm(text):
    return re.sub(r"\s+", " ", text.replace(" ", " ")).strip()


def heading_pages(pdf, lang):
    bm.LANG[0] = lang
    entries = bm.toc_entries(None)
    doc = fitz.open(pdf)
    texts = [norm(page.get_text()) for page in doc]
    pages, start = [], 2                       # page 1 = cover, page 2 = contents
    for _, title in entries:
        t = norm(title)
        for k in range(start, len(texts)):
            if t in texts[k]:
                pages.append(k + 1)
                start = k                      # headings come in order
                break
        else:
            raise SystemExit("%s: heading not found: %s" % (lang, t))
    return pages


if __name__ == "__main__":
    en, fr = sys.argv[1:3]
    data = {"en": heading_pages(en, "en"), "fr": heading_pages(fr, "fr")}
    with open(os.path.join(HERE, "toc_pages.json"), "w", encoding="utf-8") as f:
        json.dump(data, f)
    print(data)
