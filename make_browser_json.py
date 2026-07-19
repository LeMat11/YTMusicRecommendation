import argparse
import json
from typing import Dict, Optional


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert copied YouTube Music request headers to browser auth JSON."
    )
    parser.add_argument("input_file", help="Text file containing copied request headers")
    parser.add_argument("output_file", help="Destination browser_*.json file")
    return parser.parse_args()


def parse_headers(raw: str) -> Dict[str, str]:
    """
    Parse raw HTTP request headers (as copied from DevTools).

    Supports two styles:
      1) Single-line:  "Name: Value"
      2) Two-line:     "Name" on one line, "Value" on the next

    It extracts the canonical keys needed for browser.json:
      - user-agent       -> "User-Agent"
      - accept           -> "Accept"
      - accept-language  -> "Accept-Language"
      - content-type     -> "Content-Type"
      - x-goog-authuser  -> "x-goog-authuser"
      - x-origin         -> "x-origin"
      - authorization    -> "Authorization"
      - cookie           -> "Cookie"
    """
    key_map = {
        "user-agent": "User-Agent",
        "accept": "Accept",
        "accept-language": "Accept-Language",
        "content-type": "Content-Type",
        "x-goog-authuser": "x-goog-authuser",
        "x-origin": "x-origin",
        "authorization": "Authorization",
        "cookie": "Cookie",
    }

    result: Dict[str, str] = {}

    lines = [ln.rstrip("\n") for ln in raw.splitlines()]
    pending_name: Optional[str] = None

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1

        if not line:
            continue

        # Case 1: "Name: value" on a single line.
        # Only treat this as a header line if we are NOT already waiting
        # for a value and the line does not start with ":" (like ":authority").
        if pending_name is None and ":" in line and not line.startswith(":"):
            name, value = line.split(":", 1)
            name_lc = name.strip().lower()
            value = value.strip()
            if name_lc in key_map and value:
                result[key_map[name_lc]] = value
            continue

        # Case 2: Two-line "Name" + "Value" format.
        if pending_name is None:
            # This line is the header name; the next non-empty line will be its value.
            pending_name = line.strip().lower()
        else:
            # This line is the value for pending_name.
            name_lc = pending_name
            value = line.strip()
            if name_lc in key_map and value:
                result[key_map[name_lc]] = value
            pending_name = None

    print("Detected header names in file:", list(result.keys()))
    return result


def main():
    args = parse_args()

    # Read raw headers from the input file
    try:
        with open(args.input_file, "r", encoding="utf-8") as f:
            raw = f.read()
    except FileNotFoundError:
        print(
            f"Input file '{args.input_file}' not found. "
            f"Put your copied Request Headers into this file first."
        )
        return

    if not raw.strip():
        print(f"Input file '{args.input_file}' is empty.")
        return

    headers = parse_headers(raw)

    # Required keys for ytmusicapi browser auth
    required = ["Cookie", "x-goog-authuser", "Authorization", "x-origin"]
    missing = [k for k in required if k not in headers]
    if missing:
        print("Warning: the following required keys are missing:", ", ".join(missing))

    # If x-origin is missing, set a sensible default for YouTube Music
    if "x-origin" not in headers:
        headers["x-origin"] = "https://music.youtube.com"

    # Write to output JSON file
    with open(args.output_file, "w", encoding="utf-8") as f:
        json.dump(headers, f, indent=2, ensure_ascii=False)

    print(f"browser.json-style file written to: {args.output_file}")


if __name__ == "__main__":
    main()
