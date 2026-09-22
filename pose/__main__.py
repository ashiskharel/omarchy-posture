from __future__ import annotations

import argparse
import json
import sys

from pose.cues import POSES, self_test
from pose.engine import cache_dir, once, serve


def main(argv=None):
    parser = argparse.ArgumentParser(description="Coach a pose from a local camera or an IP feed.")
    parser.add_argument("command", choices=("serve", "once", "self-test"))
    parser.add_argument("--source", default="camera", help="camera, /dev/videoN, rtsp://, http://, or an image file")
    parser.add_argument("--pose", default="mountain", choices=tuple(POSES))
    parser.add_argument("--dir", default="", help="Where live.jpg and live.json are written")
    parser.add_argument("--no-speak", action="store_true", help="Do not say the coaching lines")
    args = parser.parse_args(argv)

    if args.command == "self-test":
        self_test()
        return 0

    directory = cache_dir(args.dir or None)
    if args.command == "once":
        (directory / "pose.txt").write_text(args.pose + "\n")
        payload = once(args.source, args.pose, directory)
        json.dump(payload, sys.stdout)
        sys.stdout.write("\n")
        return 0

    (directory / "pose.txt").write_text(args.pose + "\n")
    serve(args.source, directory, speak=not args.no_speak)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
