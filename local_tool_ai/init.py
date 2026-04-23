"""One-time setup: create ~/.config/local-tool-ai/.env with a generated auth token."""

import secrets
import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

CONFIG_DIR = Path.home() / ".config" / "local-tool-ai"
CONFIG_FILE = CONFIG_DIR / ".env"

_TEMPLATE = """\
# LM Studio connection
LM_STUDIO_BASE_URL={url}
LM_STUDIO_MODEL={model}
LM_STUDIO_API_KEY=lm-studio

# Agent tuning
MAX_ITERATIONS={max_iterations}

# Web server
WEB_PORT={web_port}
WEB_AUTH_TOKEN={token}
"""


def run() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_FILE.exists():
        print(f"{CONFIG_FILE} already exists — leaving it alone.")
        return
    token = secrets.token_hex(32)
    CONFIG_FILE.write_text(_TEMPLATE.format(
        token=token, 
        url=os.environ["LM_STUDIO_BASE_URL"],
        model=os.environ["LM_STUDIO_MODEL"],
        max_iterations=os.environ["MAX_ITERATIONS"],
        web_port=os.environ["WEB_PORT"]
    ))
    CONFIG_FILE.chmod(0o600)
    print(f"Created {CONFIG_FILE} with a generated WEB_AUTH_TOKEN.")
    print("Edit LM_STUDIO_MODEL to match the model loaded in LM Studio.")
