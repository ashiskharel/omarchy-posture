"""Turn body landmarks into short coaching lines.

Landmarks are (x, y, visibility) in image space: x grows right, y grows down.
The rules are geometric and run without a network.
"""

from __future__ import annotations

import math

POSES = {
    "mountain": "Mountain",
    "fold": "Forward fold",
    "chair": "Chair",
    "side": "Side stretch",
}
SHORT = {"mountain": "Mtn", "fold": "Fold", "chair": "Chair", "side": "Side"}

# Spoken once as soon as the camera opens, before the pose is judged,
# so the trainee hears what to do while they are still getting into place.
READY = {
    "mountain": "Get ready for Mountain. Stand tall, feet together, arms by your sides. Step back until your whole body is in view.",
    "fold": "Get ready for Forward fold. Feet under your hips, knees soft. Hinge from the hips and let the chest drop.",
    "chair": "Get ready for Chair. Feet under your hips. Sit back and bend the knees, chest lifted.",
    "side": "Get ready for a side stretch. Plant both feet. Reach one arm up and bend to the other side.",
}


def _pt(points, name):
    x, y, vis = points[name]
    return float(x), float(y), float(vis)


def _seen(points, *names, thresh=0.2):
    return all(name in points and _pt(points, name)[2] >= thresh for name in names)


def _mid(a, b):
    return ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)


def _dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _angle(a, b, c):
    v1 = (a[0] - b[0], a[1] - b[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    n1 = math.hypot(*v1)
    n2 = math.hypot(*v2)
    if n1 == 0 or n2 == 0:
        return None
    cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    return math.degrees(math.acos(cos))


def _cue(text, ok):
    return {"text": text, "ok": ok}


def _body(landmarks):
    needed = ("left_shoulder", "right_shoulder", "left_hip", "right_hip")
    if not _seen(landmarks, *needed):
        return None
    ls, rs = _pt(landmarks, "left_shoulder"), _pt(landmarks, "right_shoulder")
    lh, rh = _pt(landmarks, "left_hip"), _pt(landmarks, "right_hip")
    shoulders = _mid(ls, rs)
    hips = _mid(lh, rh)
    torso = _dist(shoulders, hips) or 0.2
    knees = None
    if _seen(landmarks, "left_knee", "right_knee", "left_ankle", "right_ankle"):
        knees = (
            _angle(lh, _pt(landmarks, "left_knee"), _pt(landmarks, "left_ankle")),
            _angle(rh, _pt(landmarks, "right_knee"), _pt(landmarks, "right_ankle")),
        )
    return {
        "ls": ls,
        "rs": rs,
        "lh": lh,
        "rh": rh,
        "shoulders": shoulders,
        "hips": hips,
        "torso": torso,
        "knees": knees,
    }


def coach(landmarks, pose):
    if pose not in POSES:
        pose = "mountain"
    body = _body(landmarks)
    if body is None:
        return [_cue("Step back so both shoulders and both hips are in frame.", False)]

    torso = body["torso"]
    shoulder_gap = abs(body["ls"][1] - body["rs"][1])
    hip_gap = abs(body["lh"][1] - body["rh"][1])
    shoulders_level = shoulder_gap < 0.18 * torso
    hips_level = hip_gap < 0.18 * torso
    upright = abs(body["shoulders"][0] - body["hips"][0]) < 0.35 * torso
    folded = body["shoulders"][1] > body["hips"][1] + 0.35 * torso
    knees = body["knees"]

    cues = []
    if pose == "mountain":
        cues.append(_cue("Shoulders are level." if shoulders_level else "Level the shoulders.", shoulders_level))
        cues.append(_cue("Hips are level." if hips_level else "Level the hips.", hips_level))
        cues.append(_cue("The chest is stacked over the hips." if upright else "Stand tall. Stack the chest over the hips.", upright))
        if knees is None:
            cues.append(_cue("Step back so both knees and ankles are in frame.", False))
        else:
            straight = knees[0] > 155 and knees[1] > 155
            cues.append(_cue("Legs are straight." if straight else "Straighten the legs. A tiny bend in the knees is enough.", straight))
    elif pose == "fold":
        cues.append(_cue("The chest is folding down." if folded else "Hinge from the hips and let the chest drop.", folded))
        cues.append(_cue("Hips stay level." if hips_level else "Keep the hips square.", hips_level))
        if knees is None:
            cues.append(_cue("Include the knees in the frame.", False))
        else:
            soft = 140 <= knees[0] <= 175 and 140 <= knees[1] <= 175
            locked = knees[0] > 175 and knees[1] > 175
            if soft:
                cues.append(_cue("Knees have a soft bend.", True))
            elif locked:
                cues.append(_cue("Soften the knees. Do not lock them.", False))
            else:
                cues.append(_cue("This is a fold, not a squat. Lengthen the legs.", False))
    elif pose == "chair":
        cues.append(_cue("The chest stays lifted." if upright and not folded else "Lift the chest. The back stays long.", upright and not folded))
        if knees is None:
            cues.append(_cue("Step back so the knees and ankles are visible.", False))
        else:
            bent = all(70 <= k <= 130 for k in knees)
            cues.append(_cue("Knees are bent into the sit." if bent else "Sit back. Bend the knees until the thighs work.", bent))
        cues.append(_cue("Shoulders stay level." if shoulders_level else "Keep the shoulders even as you sit.", shoulders_level))
    elif pose == "side":
        side = "left" if body["ls"][1] > body["rs"][1] else "right"
        reaching = shoulder_gap > 0.28 * torso
        cues.append(
            _cue(
                f"Bending to the {side}. The other arm reaches long." if reaching else "Bend to one side. One shoulder drops, the other reaches up.",
                reaching,
            )
        )
        cues.append(_cue("Hips stay level." if hips_level else "Keep the hips still while the ribs move.", hips_level))
    return cues


def ready_line(pose):
    return READY.get(pose, READY["mountain"])


def still_getting_ready(payload):
    if not payload.get("seen"):
        return True
    texts = " ".join(item.get("text", "") for item in payload.get("cues") or [])
    return "in frame" in texts or "in view" in texts or "Step back" in texts


def label_for(pose, cues, seen):
    short = SHORT.get(pose, "Pose")
    if not seen:
        return short
    if cues and all(item["ok"] for item in cues):
        return short + " ok"
    return short


def self_test():
    def lm(**named):
        names = {
            "ls": "left_shoulder", "rs": "right_shoulder",
            "lh": "left_hip", "rh": "right_hip",
            "lk": "left_knee", "rk": "right_knee",
            "la": "left_ankle", "ra": "right_ankle",
        }
        return {names[key]: value for key, value in named.items()}

    upright = lm(
        ls=(0.42, 0.30, 1), rs=(0.58, 0.30, 1),
        lh=(0.44, 0.55, 1), rh=(0.56, 0.55, 1),
        lk=(0.44, 0.75, 1), rk=(0.56, 0.75, 1),
        la=(0.44, 0.93, 1), ra=(0.56, 0.93, 1),
    )
    folded = lm(
        ls=(0.42, 0.72, 1), rs=(0.58, 0.72, 1),
        lh=(0.44, 0.40, 1), rh=(0.56, 0.40, 1),
        lk=(0.46, 0.62, 1), rk=(0.54, 0.62, 1),
        la=(0.46, 0.90, 1), ra=(0.54, 0.90, 1),
    )
    mountain = coach(upright, "mountain")
    fold = coach(folded, "fold")
    if not any(item["ok"] and "level" in item["text"].lower() for item in mountain):
        raise SystemExit(f"upright mountain cues were unexpected: {mountain}")
    if not any(item["ok"] and "fold" in item["text"].lower() for item in fold):
        raise SystemExit(f"folded cues were unexpected: {fold}")
    if mountain == fold:
        raise SystemExit("mountain and fold produced the same cues")
    hidden = {}
    missing = coach(hidden, "mountain")
    if missing[0]["ok"] or "frame" not in missing[0]["text"].lower():
        raise SystemExit(f"missing body was not caught: {missing}")
    if "Mountain" not in ready_line("mountain") or "Forward fold" not in ready_line("fold"):
        raise SystemExit("ready lines are missing the pose names")
    if not still_getting_ready({"seen": False, "cues": []}):
        raise SystemExit("an empty frame should count as getting ready")
    print("cues ok")
    print("mountain:", "; ".join(item["text"] for item in mountain))
    print("fold:", "; ".join(item["text"] for item in fold))
