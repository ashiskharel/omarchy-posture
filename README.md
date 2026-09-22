# Posture

Coaching for a few yoga and home-gym poses. The picture stays on the machine that captured it.

It runs two ways, from this same repository:

- An Omarchy bar plugin. Click **Pose** on the bar.
- A program on any Linux machine, including a small shop PC or a box that only watches an IP camera.

```sh
./bin/pose serve --source camera
./bin/pose serve --source /dev/video0
./bin/pose serve --source rtsp://192.168.1.20/stream
./bin/pose once --source snapshot.jpg --pose fold
```

`camera` is the laptop webcam. A path under `/dev/video` is a USB camera on that machine. `rtsp://` and `http://` are network cameras. The first run downloads a small pose model into `~/.cache/omarchy-posture/` and builds a local Python environment with [uv](https://docs.astral.sh/uv/). Reinstalling is cloning the repo again and running `./bin/pose`.

The poses are Mountain, Forward fold, Chair, and Side stretch. Cues are sentences about shoulders, hips, and knees. Pick another pose in the panel, or write its id (`mountain`, `fold`, `chair`, `side`) into `~/.cache/omarchy-posture/pose.txt` while `serve` is running.

## Omarchy

```sh
omarchy plugin add https://github.com/ashiskharel/omarchy-posture.git --enable --yes
omarchy bar put ashis.posture --after ashis.satellite
```

Click the bar label. The camera turns on while the panel is open and turns off when you close it. As soon as the panel opens, the pose is spoken so you can get into place before the coaching starts. Later lines are the adjustments, also with `espeak-ng`. `--no-speak` turns that off.

## What this is not

A hosted model is not called. `ml/` is reserved for a later button that would send one still, or the keypoints, only when you ask. Continuous video is not uploaded.

Shop security, recordings, and who is allowed to watch a camera are a different project. This one only answers "how is this person standing" for a camera you already have.
