"""Camera capture and on-device pose. Nothing here opens a network socket
except the one-time download of the pose model, and an IP camera the
operator typed in themselves.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from pose.cues import POSES, SHORT, coach, label_for, ready_line, still_getting_ready

MODEL_URL = (
    "https://tfhub.dev/google/lite-model/movenet/singlepose/lightning/"
    "tflite/int8/4?lite-format=tflite"
)
WIDTH, HEIGHT = 640, 480
INPUT_SIZE = 192
PARTS = (
    "nose",
    "left_eye", "right_eye", "left_ear", "right_ear",
    "left_shoulder", "right_shoulder", "left_elbow", "right_elbow",
    "left_wrist", "right_wrist",
    "left_hip", "right_hip", "left_knee", "right_knee",
    "left_ankle", "right_ankle",
)
BONES = (
    ("left_shoulder", "right_shoulder"),
    ("left_shoulder", "left_elbow"), ("left_elbow", "left_wrist"),
    ("right_shoulder", "right_elbow"), ("right_elbow", "right_wrist"),
    ("left_shoulder", "left_hip"), ("right_shoulder", "right_hip"),
    ("left_hip", "right_hip"),
    ("left_hip", "left_knee"), ("left_knee", "left_ankle"),
    ("right_hip", "right_knee"), ("right_knee", "right_ankle"),
)


def cache_dir(path: str | None) -> Path:
    directory = Path(path) if path else Path.home() / ".cache" / "omarchy-posture"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def model_path(directory: Path) -> Path:
    destination = directory / "movenet_lightning_int8.tflite"
    if destination.exists() and destination.stat().st_size > 100_000:
        return destination
    request = urllib.request.Request(MODEL_URL, headers={"User-Agent": "omarchy-posture/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        destination.write_bytes(response.read())
    return destination


class Capture:
    def __init__(self, source: str):
        self.source = source or "camera"
        self.proc = None
        self.still = None

    def start(self):
        if self._still_file():
            self.still = np.asarray(Image.open(self.source).convert("RGB").resize((WIDTH, HEIGHT)))
            return
        device = "/dev/video0" if self.source == "camera" else self.source
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-fflags", "nobuffer"]
        if str(device).startswith("rtsp://"):
            cmd += ["-rtsp_transport", "tcp"]
        if str(device).startswith("/dev/"):
            cmd += ["-f", "v4l2", "-framerate", "8", "-video_size", f"{WIDTH}x{HEIGHT}", "-i", device]
        else:
            cmd += ["-i", device]
        cmd += ["-vf", "fps=5,scale=640:480", "-f", "rawvideo", "-pix_fmt", "rgb24", "-an", "pipe:1"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, start_new_session=True)

    def _still_file(self):
        return self.source not in ("camera",) and not str(self.source).startswith(("/dev/", "rtsp://", "http://", "https://")) and Path(self.source).is_file()

    def read(self):
        if self.still is not None:
            return self.still.copy()
        if self.proc is None or self.proc.stdout is None:
            return None
        need = WIDTH * HEIGHT * 3
        buf = bytearray()
        while len(buf) < need:
            chunk = self.proc.stdout.read(need - len(buf))
            if not chunk:
                return None
            buf += chunk
        return np.frombuffer(buf, dtype=np.uint8).reshape((HEIGHT, WIDTH, 3)).copy()

    def close(self):
        proc = self.proc
        self.proc = None
        if proc is None:
            return
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)


class Tracker:
    def __init__(self, directory: Path):
        from ai_edge_litert.interpreter import Interpreter

        self.interpreter = Interpreter(model_path=str(model_path(directory)))
        self.interpreter.allocate_tensors()
        self.input_index = self.interpreter.get_input_details()[0]["index"]
        self.output_index = self.interpreter.get_output_details()[0]["index"]

    def landmarks(self, frame):
        small = np.asarray(Image.fromarray(frame, "RGB").resize((INPUT_SIZE, INPUT_SIZE)), dtype=np.uint8)
        self.interpreter.set_tensor(self.input_index, np.expand_dims(small, 0))
        self.interpreter.invoke()
        raw = self.interpreter.get_tensor(self.output_index)[0][0]
        points = {}
        for name, row in zip(PARTS, raw):
            y, x, score = float(row[0]), float(row[1]), float(row[2])
            points[name] = (x, y, score)
        if max(score for _, _, score in points.values()) < 0.15:
            return None
        return points


def brighten(frame):
    # The laptop camera is often pointed at a dim room. Stretch a dark frame
    # so the pose model and the preview can both see a person.
    hi = float(np.percentile(frame, 98))
    if hi >= 140:
        return frame
    scale = min(5.0, 180.0 / max(hi, 1.0))
    return np.clip(frame.astype(np.float32) * scale, 0, 255).astype(np.uint8)


def draw_frame(frame, landmarks):
    image = Image.fromarray(frame, "RGB")
    if not landmarks:
        return image
    pen = ImageDraw.Draw(image)
    w, h = image.size

    def xy(name):
        x, y, vis = landmarks[name]
        if vis < 0.2:
            return None
        return x * w, y * h

    for a, b in BONES:
        pa, pb = xy(a), xy(b)
        if pa and pb:
            pen.line([pa, pb], fill=(186, 214, 180), width=3)
    for name in ("left_shoulder", "right_shoulder", "left_hip", "right_hip", "left_knee", "right_knee", "left_ankle", "right_ankle"):
        point = xy(name)
        if point:
            x, y = point
            pen.ellipse((x - 4, y - 4, x + 4, y + 4), fill=(240, 236, 220))
    return image


def read_pose(directory: Path) -> str:
    file = directory / "pose.txt"
    if not file.exists():
        return "mountain"
    name = file.read_text().strip().split()
    if not name:
        return "mountain"
    return name[0] if name[0] in POSES else "mountain"


def publish(directory: Path, frame, landmarks, pose, error=""):
    seen = landmarks is not None
    cues = coach(landmarks, pose) if seen else [{"text": "Step into the frame. One person, full body if you can.", "ok": False}]
    if error:
        cues = [{"text": error, "ok": False}]
        seen = False
    payload = {
        "pose": pose,
        "pose_name": POSES.get(pose, pose),
        "short": SHORT.get(pose, "Pose"),
        "label": label_for(pose, cues, seen and not error),
        "seen": seen,
        "cues": cues,
        "source_note": "",
    }
    image = draw_frame(frame, landmarks if seen else None)
    jpg = directory / "live.jpg"
    tmp_jpg = directory / "live.jpg.tmp"
    meta = directory / "live.json"
    tmp_meta = directory / "live.json.tmp"
    image.save(tmp_jpg, "JPEG", quality=80)
    tmp_meta.write_text(json.dumps(payload))
    os.replace(tmp_jpg, jpg)
    os.replace(tmp_meta, meta)
    return payload


class Speaker:
    """Say a coaching line. A new line replaces the one still playing."""

    def __init__(self):
        self.proc = None
        self.last = ""
        self.last_at = 0.0
        self.command = shutil.which("espeak-ng") or shutil.which("espeak")

    def say(self, text: str, replace: bool = False):
        if not self.command or not text:
            return
        now = time.monotonic()
        playing = self.proc is not None and self.proc.poll() is None
        # Let the sentence finish. The getting-ready line is long on purpose,
        # and cutting it off left the trainee in silence.
        if playing and not replace:
            return
        if text == self.last and now - self.last_at < 12:
            return
        if playing:
            self.proc.terminate()
        self.proc = subprocess.Popen(
            [self.command, "-s", "145", "-a", "140", text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.last = text
        self.last_at = now

    def close(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


def spoken_line(payload) -> str:
    cues = payload.get("cues") or []
    fixes = [item["text"] for item in cues if not item.get("ok")]
    if not fixes:
        name = payload.get("pose_name") or "This pose"
        return name + ". Hold there."
    return fixes[0]


def serve(source: str, directory: Path, speak: bool = True):
    capture = Capture(source)
    speaker = Speaker() if speak else None
    announced = ""
    try:
        # Speak before the camera and the model are ready, so the trainee
        # hears the setup while they are still getting into place.
        pose = read_pose(directory)
        announced = pose
        if speaker:
            speaker.say(ready_line(pose), replace=True)
        capture.start()
        tracker = Tracker(directory)
        while True:
            frame = capture.read()
            if frame is not None:
                frame = brighten(frame)
            if frame is None:
                payload = publish(directory, np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8), None, read_pose(directory), "The camera stopped. Check the source and try again.")
                if speaker:
                    speaker.say(spoken_line(payload))
                break
            try:
                landmarks = tracker.landmarks(frame)
            except Exception as exc:
                payload = publish(directory, frame, None, read_pose(directory), str(exc))
                if speaker:
                    speaker.say(spoken_line(payload))
                time.sleep(0.5)
                continue
            pose = read_pose(directory)
            payload = publish(directory, frame, landmarks, pose)
            if speaker and pose != announced:
                announced = pose
                speaker.say(ready_line(pose), replace=True)
            elif speaker and still_getting_ready(payload):
                speaker.say(ready_line(pose))
            elif speaker:
                speaker.say(spoken_line(payload))
            if capture.still is not None:
                time.sleep(0.4)
    finally:
        if speaker:
            speaker.close()
        capture.close()


def once(source: str, pose: str, directory: Path):
    capture = Capture(source)
    try:
        capture.start()
        frame = capture.read()
        if frame is None:
            raise RuntimeError("No frame from " + source)
        frame = brighten(frame)
        tracker = Tracker(directory)
        landmarks = tracker.landmarks(frame)
        return publish(directory, frame, landmarks, pose if pose in POSES else "mountain")
    finally:
        capture.close()
