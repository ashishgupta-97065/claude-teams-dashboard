"""
Minimal in-house Markdown → HTML renderer.

Supported:
  - ATX headings #..######
  - Fenced code blocks ```lang ... ```
  - Paragraphs (blank-line separated)
  - Bullet lists (- or *) and ordered lists (1.)
  - Bold **x**, italic *x*, inline code `x`, links [t](u)
  - Horizontal rules ---
  - HTML escaping on all user content before inline rules

NOT supported: tables, footnotes, task lists, images, nested blockquotes.

Output is wrapped in <div class="md"> for CSS scoping.
No new pip dependencies — pure stdlib.
"""
from __future__ import annotations

import html
import re


def render(md_text: str) -> str:
    """Convert Markdown text to HTML string wrapped in <div class="md">."""
    html_parts: list[str] = []
    lines = md_text.split("\n")
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]

        # ── Fenced code block ─────────────────────────────────────────────────
        if line.strip().startswith("```"):
            lang = line.strip()[3:].strip()
            i += 1
            code_lines: list[str] = []
            while i < n and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            if i < n:
                i += 1  # skip closing ```
            code_content = html.escape("\n".join(code_lines))
            if lang:
                html_parts.append(
                    f'<pre><code class="language-{html.escape(lang)}">{code_content}</code></pre>'
                )
            else:
                html_parts.append(f"<pre><code>{code_content}</code></pre>")
            continue

        # ── ATX heading ───────────────────────────────────────────────────────
        m = re.match(r"^(#{1,6})\s+(.*)", line)
        if m:
            level = len(m.group(1))
            text = _apply_inline(html.escape(m.group(2).strip()))
            html_parts.append(f"<h{level}>{text}</h{level}>")
            i += 1
            continue

        # ── Horizontal rule ───────────────────────────────────────────────────
        if re.match(r"^---+\s*$", line.strip()) and line.strip():
            html_parts.append("<hr>")
            i += 1
            continue

        # ── Unordered list ────────────────────────────────────────────────────
        if re.match(r"^[-*]\s+", line):
            items: list[str] = []
            while i < n and re.match(r"^[-*]\s+", lines[i]):
                item_text = re.sub(r"^[-*]\s+", "", lines[i])
                items.append(f"<li>{_apply_inline(html.escape(item_text))}</li>")
                i += 1
            html_parts.append("<ul>" + "".join(items) + "</ul>")
            continue

        # ── Ordered list ──────────────────────────────────────────────────────
        if re.match(r"^\d+\.\s+", line):
            items = []
            while i < n and re.match(r"^\d+\.\s+", lines[i]):
                item_text = re.sub(r"^\d+\.\s+", "", lines[i])
                items.append(f"<li>{_apply_inline(html.escape(item_text))}</li>")
                i += 1
            html_parts.append("<ol>" + "".join(items) + "</ol>")
            continue

        # ── Empty line ────────────────────────────────────────────────────────
        if not line.strip():
            i += 1
            continue

        # ── Paragraph ─────────────────────────────────────────────────────────
        para_lines: list[str] = []
        while i < n:
            current = lines[i]
            # Stop collecting paragraph on block-level elements
            if not current.strip():
                break
            if re.match(r"^#{1,6}\s", current):
                break
            if current.strip().startswith("```"):
                break
            if re.match(r"^---+\s*$", current.strip()) and current.strip():
                break
            if re.match(r"^[-*]\s+", current):
                break
            if re.match(r"^\d+\.\s+", current):
                break
            para_lines.append(current)
            i += 1

        if para_lines:
            text = " ".join(para_lines)
            html_parts.append(f"<p>{_apply_inline(html.escape(text))}</p>")

    return f'<div class="md">{"".join(html_parts)}</div>'


def _apply_inline(text: str) -> str:
    """Apply inline Markdown formatting to already-HTML-escaped text.

    Order matters: inline code first (prevents * and _ inside code from being
    processed), then bold, then italic, then links.
    """
    # Inline code: `code` — process before bold/italic
    text = re.sub(r"`([^`]+)`", lambda m: f"<code>{m.group(1)}</code>", text)

    # Bold: **text**
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)

    # Italic: *text* (must come after bold to avoid partial match on **)
    text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)

    # Links: [text](url)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2">\1</a>',
        text,
    )

    return text
