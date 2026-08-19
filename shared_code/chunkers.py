import hashlib
import re
from typing import List, Dict, Any


MAX_CHARS_PER_CHUNK = 2200
MIN_CHARS_PER_CHUNK = 300


def build_chunk_id(doc_id: str, chunk_index: int) -> str:
    raw = f"{doc_id}::{chunk_index}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return f"{doc_id}-chunk-{digest}"


def normalize_chunk_text(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def split_readme_by_headings(content: str) -> List[str]:
    text = normalize_chunk_text(content)
    if not text:
        return []

    lines = text.split("\n")
    sections = []
    current = []

    for line in lines:
        if re.match(r"^#{1,6}\s+", line) and current:
            sections.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)

    if current:
        sections.append("\n".join(current).strip())

    return [s for s in sections if s]


def split_plain_text(content: str, max_chars: int = MAX_CHARS_PER_CHUNK) -> List[str]:
    text = normalize_chunk_text(content)
    if not text:
        return []

    if len(text) <= max_chars:
        return [text]

    paragraphs = re.split(r"\n\s*\n", text)
    chunks = []
    current = ""

    for para in paragraphs:
        para = para.strip()
        if not para:
            continue

        candidate = f"{current}\n\n{para}".strip() if current else para
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            if len(para) <= max_chars:
                current = para
            else:
                for i in range(0, len(para), max_chars):
                    chunks.append(para[i:i + max_chars].strip())
                current = ""

    if current:
        chunks.append(current)

    return [c for c in chunks if c]


def split_terraform_blocks(content: str) -> List[str]:
    text = normalize_chunk_text(content)
    if not text:
        return []

    lines = text.split("\n")
    chunks = []
    current = []
    brace_balance = 0
    inside_block = False

    top_level_block_start = re.compile(
        r'^\s*(terraform|provider|module|resource|data|variable|output|locals)\b'
    )

    for line in lines:
        if top_level_block_start.match(line) and not inside_block and current:
            chunks.append("\n".join(current).strip())
            current = []

        current.append(line)

        open_count = line.count("{")
        close_count = line.count("}")

        if top_level_block_start.match(line) and "{" in line:
            inside_block = True

        brace_balance += open_count
        brace_balance -= close_count

        if inside_block and brace_balance <= 0:
            inside_block = False
            brace_balance = 0

    if current:
        chunks.append("\n".join(current).strip())

    return [c for c in chunks if c]


def merge_small_chunks(chunks: List[str], max_chars: int = MAX_CHARS_PER_CHUNK) -> List[str]:
    if not chunks:
        return []

    merged = []
    current = ""

    for chunk in chunks:
        chunk = chunk.strip()
        if not chunk:
            continue

        if not current:
            current = chunk
            continue

        if len(current) < MIN_CHARS_PER_CHUNK and len(current) + 2 + len(chunk) <= max_chars:
            current = f"{current}\n\n{chunk}".strip()
        else:
            merged.append(current)
            current = chunk

    if current:
        merged.append(current)

    return merged


def split_large_terraform_chunk(chunk: str, max_chars: int = MAX_CHARS_PER_CHUNK) -> List[str]:
    if len(chunk) <= max_chars:
        return [chunk]

    lines = chunk.split("\n")
    out = []
    current = ""

    for line in lines:
        candidate = f"{current}\n{line}".strip() if current else line
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                out.append(current)
            if len(line) <= max_chars:
                current = line
            else:
                for i in range(0, len(line), max_chars):
                    out.append(line[i:i + max_chars].strip())
                current = ""

    if current:
        out.append(current)

    return [c for c in out if c]


def chunk_terraform_content(content: str) -> List[str]:
    text = normalize_chunk_text(content)
    if not text:
        return []

    if len(text) <= MAX_CHARS_PER_CHUNK:
        return [text]

    blocks = split_terraform_blocks(text)
    blocks = merge_small_chunks(blocks)

    final_chunks = []
    for block in blocks:
        final_chunks.extend(split_large_terraform_chunk(block))

    return [c for c in final_chunks if c]


def chunk_document(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    content = normalize_chunk_text(doc.get("content", ""))
    if not content:
        return []

    doc_type = doc.get("doc_type", "other")
    path = (doc.get("path") or "").lower()

    if doc_type == "readme":
        raw_chunks = split_readme_by_headings(content)
        if not raw_chunks:
            raw_chunks = split_plain_text(content)
    elif doc_type in {"tfvars", "pipeline"}:
        raw_chunks = split_plain_text(content)
    elif path.endswith(".tf"):
        raw_chunks = chunk_terraform_content(content)
    else:
        raw_chunks = split_plain_text(content)

    chunked_docs = []

    for idx, chunk_text in enumerate(raw_chunks):
        chunk_text = normalize_chunk_text(chunk_text)
        if not chunk_text:
            continue

        chunk_doc = dict(doc)
        chunk_doc["chunk_id"] = build_chunk_id(doc["id"], idx)
        chunk_doc["chunk_index"] = idx
        chunk_doc["content"] = chunk_text
        chunk_doc["parent_id"] = doc["id"]
        chunked_docs.append(chunk_doc)

    return chunked_docs


def chunk_documents(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    all_chunks: List[Dict[str, Any]] = []

    for doc in documents:
        all_chunks.extend(chunk_document(doc))

    return all_chunks