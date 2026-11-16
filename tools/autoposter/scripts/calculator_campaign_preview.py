"""Generate an offline, owner-reviewable platform link bundle.

Example:
python -m tools.autoposter.scripts.calculator_campaign_preview --target axis_distribution --content-id axis_loading_01 --output /tmp/calculator_links.json
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

from tools.autoposter.src.crossplatform.calculator_campaign import TARGETS, preview_package


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", choices=sorted(TARGETS), required=True)
    parser.add_argument("--content-id", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = preview_package(target=args.target, content_id=args.content_id)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
