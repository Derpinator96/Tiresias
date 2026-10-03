"""Create .env with the HMAC key and the Postgres password, without printing either.

Keys already present in .env are kept: rotating the HMAC key would split every stored code
in two (doc, Detailed component specs), so this script never overwrites it.
GEMINI_API_KEY is added as an empty line for the human to fill in.
"""
import secrets
from pathlib import Path

from common.config import cfg

ENV = Path(__file__).resolve().parent.parent / ".env"


def main() -> None:
    lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    present = {ln.split("=", 1)[0] for ln in lines if "=" in ln}
    added = []
    if "BT_HMAC_KEY" not in present:
        lines.append(f"BT_HMAC_KEY={secrets.token_hex(cfg('gateway.hmac_key_bytes'))}")
        added.append("BT_HMAC_KEY")
    if "POSTGRES_PASSWORD" not in present:
        lines.append(f"POSTGRES_PASSWORD={secrets.token_urlsafe(24)}")
        added.append("POSTGRES_PASSWORD")
    if "GEMINI_API_KEY" not in present:
        lines.append("GEMINI_API_KEY=")
        added.append("GEMINI_API_KEY (empty, fill it in)")
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("added: " + (", ".join(added) if added else "nothing, all keys already present"))


if __name__ == "__main__":
    main()
