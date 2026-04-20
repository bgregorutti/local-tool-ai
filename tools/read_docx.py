"""Read the text content of a Word (.docx) document."""

from __future__ import annotations

SCHEMA: dict = {
    "type": "function",
    "function": {
        "name": "read_docx",
        "description": (
            "Read and return the text content of a Word document (.docx) as plain text. "
            "USE THIS instead of run_bash when the goal is to read or inspect a .docx file. "
            "Do NOT use run_bash for this purpose. "
            "Read-only operation — no changes are made to the file."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Absolute path to the .docx file.",
                },
            },
            "required": ["file_path"],
        },
    },
}


def run(file_path: str) -> str:
    try:
        import docx

        doc = docx.Document(file_path)
        text = "\n".join(para.text for para in doc.paragraphs)
        return text if text.strip() else "(empty document)"
    except FileNotFoundError:
        return f"Error: '{file_path}' does not exist."
    except Exception as exc:
        return f"Error: {exc}"
