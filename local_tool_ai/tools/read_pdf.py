"""Read the text content of a PDF file as Markdown."""

from __future__ import annotations

SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "read_pdf",
        "description": (
            "Read and return the text content of a PDF file as Markdown. "
            "USE THIS instead of run_bash when the goal is to read or inspect a PDF file. "
            "Do NOT use run_bash (e.g. pdftotext, cat) for this purpose. "
            "Read-only operation — no changes are made to the file."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the PDF file.",
                },
            },
            "required": ["file_path"],
        },
    },
}


def run(file_path: str) -> str:
    try:
        import pymupdf4llm

        result = pymupdf4llm.to_markdown(file_path)
        return result if result.strip() else "(no extractable text found in PDF)"
    except FileNotFoundError:
        return f"Error: '{file_path}' does not exist."
    except Exception as exc:
        return f"Error: {exc}"
