import argparse
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.animation import FFMpegWriter, FuncAnimation, writers
from matplotlib.patches import Circle, Ellipse, FancyBboxPatch, Polygon


POSE_START, POSE_END = 0, 33
FACE_START, FACE_END = 33, 501
LH_START, LH_END = 501, 522
RH_START, RH_END = 522, 543

L_SHOULDER = 11
R_SHOULDER = 12
L_ELBOW = 13
R_ELBOW = 14
L_WRIST = 15
R_WRIST = 16

AVATAR_CENTER_X = 0.50
HEAD_CENTER_Y = 0.315
SHOULDER_Y = 0.468
BODY_TOP_Y = 0.470
BODY_BOTTOM_Y = 0.750

HEAD_W = 0.116
HEAD_H = 0.143
NECK_W = 0.028
NECK_H = 0.072

BODY_HALF_SHOULDER = 0.140
BODY_HALF_CHEST = 0.118
BODY_HALF_WAIST = 0.096
BODY_HALF_BOTTOM = 0.108

ARM_WIDTH = 13
FOREARM_WIDTH = 12
MOTION_GAIN = 1.03

HAND_SCALE = 1.08
HAND_MAX_RADIUS = 0.135
HAND_ATTACH_STRENGTH = 1.00
WRIST_RADIUS = 0.010
PALM_WIDTH = 0.044
PALM_HEIGHT = 0.034
FINGER_POINT_SIZE = 11
MAX_FINGER_SEGMENT = 0.052
MAX_THUMB_SEGMENT = 0.050

MOUTH_BASE_OPEN = 0.0045
MOUTH_THRESHOLD = 0.11
MOUTH_MAX_OPEN = 0.013

BG_DARK = "#051A2A"
CARD_EDGE = "#12B8A6"
TEAL = "#16C8BE"
TEAL_BODY = "#07506B"
TEAL_BODY_LIGHT = "#0B6D88"
TEAL_SLEEVE = "#0EAABD"
TEAL_DARK = "#063D55"
GREEN = "#6FD18A"
SKIN = "#F2C69B"
SKIN_EDGE = "#F8DFC7"
HAIR = "#101F2D"
HAIR_DARK = "#07111C"
HAIR_LIGHT = "#26384A"
WHITE = "#F2FAFF"
EYE_DARK = "#07131A"
FINGER_LINE = "#F0BF91"
FINGER_POINT = "#FFE0B9"


def _valid_point(point):
    return np.isfinite(point).all()


def _safe_pt(points, idx):
    if idx < 0 or idx >= len(points):
        return np.array([np.nan, np.nan])
    return points[idx]


def _clamp(value, low, high):
    return max(low, min(high, value))


def _clamp_point(point, xmin, xmax, ymin, ymax):
    if not _valid_point(point):
        return point
    out = point.copy()
    out[0] = _clamp(out[0], xmin, xmax)
    out[1] = _clamp(out[1], ymin, ymax)
    return out


def _median_valid(values):
    values = np.array(values, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return np.nan
    return float(np.median(values))


def _mean_valid_dist(a_seq, b_seq):
    values = []
    for a, b in zip(a_seq, b_seq):
        if _valid_point(a) and _valid_point(b):
            values.append(np.linalg.norm(a - b))
    if not values:
        return np.inf
    return float(np.mean(values))


def _normalize_by_pose(frame):
    pose = frame[POSE_START:POSE_END, :2]
    key_points = pose[[11, 12, 13, 14, 15, 16, 23, 24]]
    valid = np.isfinite(key_points).all(axis=1)
    key_points = key_points[valid]

    if len(key_points) == 0:
        return frame[:, :2]

    min_xy = key_points.min(axis=0)
    max_xy = key_points.max(axis=0)
    center = (min_xy + max_xy) / 2
    scale = max(max_xy[0] - min_xy[0], max_xy[1] - min_xy[1], 1e-6)

    points = frame[:, :2].copy()
    points = (points - center) / scale
    points[:, 0] = points[:, 0] * 0.48 + 0.5
    points[:, 1] = points[:, 1] * 0.48 + 0.52
    return points


def _smooth_sequence(points_seq, alpha=0.84):
    out = points_seq.copy()
    for i in range(1, len(out)):
        curr = out[i]
        prev = out[i - 1]
        both = np.isfinite(curr).all(axis=1) & np.isfinite(prev).all(axis=1)
        out[i, both] = alpha * curr[both] + (1 - alpha) * prev[both]
    return out


def _smooth_scalar(values, alpha=0.18):
    out = np.array(values, dtype=float)
    for i in range(1, len(out)):
        out[i] = alpha * out[i] + (1 - alpha) * out[i - 1]
    return out


def _detect_visual_pose_labels(norm_frames):
    left_x = []
    right_x = []
    for points in norm_frames:
        pose = points[POSE_START:POSE_END]
        if _valid_point(pose[L_WRIST]):
            left_x.append(pose[L_WRIST][0])
        if _valid_point(pose[R_WRIST]):
            right_x.append(pose[R_WRIST][0])

    med_l = _median_valid(left_x)
    med_r = _median_valid(right_x)
    if np.isnan(med_l) or np.isnan(med_r):
        visual_left = "L"
    else:
        visual_left = "L" if med_l < med_r else "R"
    visual_right = "R" if visual_left == "L" else "L"
    return visual_left, visual_right


def _detect_hand_to_pose_mapping(norm_frames):
    lh0_seq, rh0_seq, lwr_seq, rwr_seq = [], [], [], []
    for points in norm_frames:
        pose = points[POSE_START:POSE_END]
        lh = points[LH_START:LH_END]
        rh = points[RH_START:RH_END]
        lh0_seq.append(lh[0])
        rh0_seq.append(rh[0])
        lwr_seq.append(pose[L_WRIST])
        rwr_seq.append(pose[R_WRIST])

    normal_cost = _mean_valid_dist(lh0_seq, lwr_seq) + _mean_valid_dist(rh0_seq, rwr_seq)
    swapped_cost = _mean_valid_dist(lh0_seq, rwr_seq) + _mean_valid_dist(rh0_seq, lwr_seq)
    if swapped_cost < normal_cost:
        return "RH", "LH"
    return "LH", "RH"


def _mouth_levels(norm_frames):
    raw_levels = []
    for points in norm_frames:
        face = points[FACE_START:FACE_END]
        mouth_left = _safe_pt(face, 61)
        mouth_right = _safe_pt(face, 291)
        mouth_upper = _safe_pt(face, 13)
        mouth_lower = _safe_pt(face, 14)
        level = MOUTH_BASE_OPEN

        if (
            _valid_point(mouth_left)
            and _valid_point(mouth_right)
            and _valid_point(mouth_upper)
            and _valid_point(mouth_lower)
        ):
            mouth_width = np.linalg.norm(mouth_left - mouth_right)
            mouth_open = np.linalg.norm(mouth_upper - mouth_lower)
            if mouth_width > 1e-6:
                ratio = mouth_open / mouth_width
                if ratio > MOUTH_THRESHOLD:
                    level = _clamp(
                        MOUTH_BASE_OPEN + (ratio - MOUTH_THRESHOLD) * 0.045,
                        MOUTH_BASE_OPEN,
                        MOUTH_MAX_OPEN,
                    )
        raw_levels.append(level)
    return _smooth_scalar(raw_levels, alpha=0.18)


def _avatar_points():
    cx = AVATAR_CENTER_X
    head_center = np.array([cx, HEAD_CENTER_Y])
    neck_top = np.array([cx, HEAD_CENTER_Y + 0.062])
    neck_bottom = np.array([cx, BODY_TOP_Y + 0.002])
    left_shoulder_center = np.array([cx - BODY_HALF_SHOULDER + 0.030, BODY_TOP_Y + 0.036])
    right_shoulder_center = np.array([cx + BODY_HALF_SHOULDER - 0.030, BODY_TOP_Y + 0.036])
    left_anchor = left_shoulder_center + np.array([-0.010, 0.012])
    right_anchor = right_shoulder_center + np.array([0.010, 0.012])
    return head_center, neck_top, neck_bottom, left_shoulder_center, right_shoulder_center, left_anchor, right_anchor


def _get_pose_joint(pose, label, joint_name):
    if label == "L":
        return {"shoulder": pose[L_SHOULDER], "elbow": pose[L_ELBOW], "wrist": pose[L_WRIST]}[joint_name]
    return {"shoulder": pose[R_SHOULDER], "elbow": pose[R_ELBOW], "wrist": pose[R_WRIST]}[joint_name]


def _map_motion_point(raw_point, raw_shoulder_center, avatar_shoulder_center):
    if not _valid_point(raw_point):
        return np.array([np.nan, np.nan])
    return avatar_shoulder_center + (raw_point - raw_shoulder_center) * MOTION_GAIN


def _get_visual_side_motion(pose, visual_side, visual_left_label, visual_right_label):
    _, _, _, _, _, left_anchor, right_anchor = _avatar_points()
    if visual_side == "left":
        pose_label = visual_left_label
        anchor = left_anchor
        elbow_clamp = (0.220, 0.545, 0.350, 0.735)
        wrist_clamp = (0.215, 0.590, 0.325, 0.755)
    else:
        pose_label = visual_right_label
        anchor = right_anchor
        elbow_clamp = (0.455, 0.780, 0.350, 0.735)
        wrist_clamp = (0.410, 0.785, 0.325, 0.755)

    other_label = "R" if pose_label == "L" else "L"
    raw_shoulder = _get_pose_joint(pose, pose_label, "shoulder")
    raw_other_shoulder = _get_pose_joint(pose, other_label, "shoulder")
    if _valid_point(raw_shoulder) and _valid_point(raw_other_shoulder):
        raw_shoulder_mid = (raw_shoulder + raw_other_shoulder) / 2
    else:
        raw_shoulder_mid = np.array([0.50, 0.455])

    avatar_shoulder_mid = np.array([AVATAR_CENTER_X, SHOULDER_Y])
    elbow = _map_motion_point(_get_pose_joint(pose, pose_label, "elbow"), raw_shoulder_mid, avatar_shoulder_mid)
    wrist = _map_motion_point(_get_pose_joint(pose, pose_label, "wrist"), raw_shoulder_mid, avatar_shoulder_mid)
    return pose_label, anchor, _clamp_point(elbow, *elbow_clamp), _clamp_point(wrist, *wrist_clamp)


def _get_hand_group(points, pose_label, hand_for_pose_l, hand_for_pose_r):
    lh = points[LH_START:LH_END].copy()
    rh = points[RH_START:RH_END].copy()
    if pose_label == "L":
        return lh if hand_for_pose_l == "LH" else rh
    return lh if hand_for_pose_r == "LH" else rh


def _prepare_hand(hand_pts, wrist_pt):
    valid = np.isfinite(hand_pts).all(axis=1)
    if not valid.any() or not _valid_point(wrist_pt):
        return hand_pts

    out = hand_pts.copy()
    if _valid_point(out[0]):
        shift = wrist_pt - out[0]
    else:
        shift = wrist_pt - out[valid].mean(axis=0)
    out[valid] = out[valid] + shift * HAND_ATTACH_STRENGTH
    out[valid] = wrist_pt + (out[valid] - wrist_pt) * HAND_SCALE

    for i in range(len(out)):
        if _valid_point(out[i]):
            vector = out[i] - wrist_pt
            distance = np.linalg.norm(vector)
            if distance > HAND_MAX_RADIUS:
                out[i] = wrist_pt + (vector / distance) * HAND_MAX_RADIUS

    if _valid_point(out[0]):
        out[valid] = out[valid] + (wrist_pt - out[0])
    return out


def _clamp_segment(a, b, max_len):
    vector = b - a
    distance = np.linalg.norm(vector)
    if distance < 1e-8:
        return b
    if distance > max_len:
        return a + (vector / distance) * max_len
    return b


def _draw_capsule(ax, p1, p2, width, color, edge=TEAL, z=5, alpha=1.0):
    if not (_valid_point(p1) and _valid_point(p2)):
        return
    ax.plot([p1[0] + 0.005, p2[0] + 0.005], [p1[1] + 0.008, p2[1] + 0.008],
            linewidth=width + 4, solid_capstyle="round", color="black", alpha=0.12, zorder=z - 2)
    ax.plot([p1[0], p2[0]], [p1[1], p2[1]], linewidth=width + 1.4,
            solid_capstyle="round", color=edge, alpha=0.72, zorder=z - 1)
    ax.plot([p1[0], p2[0]], [p1[1], p2[1]], linewidth=width,
            solid_capstyle="round", color=color, alpha=alpha, zorder=z)


def _draw_background(ax, frame_idx, num_frames):
    n = 500
    y, x = np.ogrid[0:1:n * 1j, 0:1:n * 1j]
    radius = np.sqrt((x - 0.50) ** 2 + (y - 0.38) ** 2)
    grad = 1 - np.clip(radius / 0.75, 0, 1)
    base = np.zeros((n, n, 3))
    base[..., 0] = 0.02 + grad * 0.02
    base[..., 1] = 0.10 + grad * 0.13
    base[..., 2] = 0.16 + grad * 0.16
    ax.imshow(base, extent=[0, 1, 1, 0], zorder=-20)

    ax.add_patch(FancyBboxPatch((0.145, 0.075), 0.710, 0.850, boxstyle="round,pad=0.018,rounding_size=0.045",
                                facecolor="#082436", edgecolor=CARD_EDGE, linewidth=2.6, alpha=0.58, zorder=-10))
    ax.add_patch(FancyBboxPatch((0.185, 0.145), 0.630, 0.715, boxstyle="round,pad=0.025,rounding_size=0.055",
                                facecolor="#0E4A63", edgecolor="none", alpha=0.18, zorder=-9))
    ax.add_patch(FancyBboxPatch((0.225, 0.190), 0.550, 0.640, boxstyle="round,pad=0.018,rounding_size=0.040",
                                facecolor="#0A3850", edgecolor="none", alpha=0.32, zorder=-8))
    ax.add_patch(Circle((0.250, 0.225), 0.012, facecolor=GREEN, edgecolor="none", alpha=0.14, zorder=-7))
    ax.add_patch(Circle((0.748, 0.245), 0.010, facecolor=TEAL, edgecolor="none", alpha=0.16, zorder=-7))
    ax.text(0.5, 0.112, "Arabic Sign Instruction Preview", color="#DDFDF8",
            fontsize=12, ha="center", va="center", alpha=0.96, zorder=40)
    ax.text(0.5, 0.145, "PharmaSign", color=TEAL, fontsize=26,
            fontweight="bold", ha="center", va="center", zorder=40)
    ax.text(0.5, 0.895, f"Frame {frame_idx + 1}/{num_frames}", color="#CFFDF5",
            fontsize=10, ha="center", va="center", alpha=0.80, zorder=40)


def _draw_body(ax):
    cx = AVATAR_CENTER_X
    top_y = BODY_TOP_Y
    chest_y = top_y + 0.065
    waist_y = top_y + 0.205
    bottom_y = BODY_BOTTOM_Y
    body_pts = np.array([
        [cx - BODY_HALF_SHOULDER, top_y + 0.020],
        [cx - BODY_HALF_CHEST, chest_y],
        [cx - BODY_HALF_WAIST, waist_y],
        [cx - BODY_HALF_BOTTOM, bottom_y],
        [cx, bottom_y + 0.012],
        [cx + BODY_HALF_BOTTOM, bottom_y],
        [cx + BODY_HALF_WAIST, waist_y],
        [cx + BODY_HALF_CHEST, chest_y],
        [cx + BODY_HALF_SHOULDER, top_y + 0.020],
        [cx + 0.036, top_y - 0.004],
        [cx + 0.013, top_y + 0.034],
        [cx, top_y + 0.040],
        [cx - 0.013, top_y + 0.034],
        [cx - 0.036, top_y - 0.004],
    ])
    ax.add_patch(Ellipse((cx, 0.785), width=0.32, height=0.040,
                         facecolor="black", edgecolor="none", alpha=0.22, zorder=0))
    ax.add_patch(Polygon(body_pts + np.array([0.008, 0.011]), closed=True,
                         facecolor="black", edgecolor="none", alpha=0.16, zorder=1))
    ax.add_patch(Polygon(body_pts, closed=True, facecolor=TEAL_BODY,
                         edgecolor=TEAL, linewidth=2.0, joinstyle="round", zorder=2))
    ax.add_patch(Ellipse((cx, top_y + 0.135), width=0.175, height=0.210,
                         facecolor=TEAL_BODY_LIGHT, edgecolor="none", alpha=0.15, zorder=3))
    ax.add_patch(FancyBboxPatch((cx - 0.021, top_y - 0.002), 0.042, 0.017,
                                boxstyle="round,pad=0.001,rounding_size=0.010",
                                facecolor=TEAL_DARK, edgecolor=TEAL, linewidth=1.1, zorder=6))
    ax.add_patch(Circle((cx, top_y + 0.075), radius=0.008, facecolor=TEAL,
                        edgecolor="none", alpha=0.95, zorder=6))


def _draw_neck(ax, neck_top, neck_bottom):
    ax.add_patch(FancyBboxPatch((neck_bottom[0] - NECK_W / 2 + 0.005, neck_top[1] + 0.006),
                                NECK_W, NECK_H, boxstyle="round,pad=0.002,rounding_size=0.014",
                                facecolor="black", edgecolor="none", alpha=0.14, zorder=3))
    ax.add_patch(FancyBboxPatch((neck_bottom[0] - NECK_W / 2, neck_top[1]), NECK_W, NECK_H,
                                boxstyle="round,pad=0.002,rounding_size=0.014",
                                facecolor=SKIN, edgecolor="#F4D6B5", linewidth=1.0, zorder=4))


def _draw_shoulder_caps(ax, left_center, right_center):
    for center in (left_center, right_center):
        ax.add_patch(Ellipse(center + np.array([0.004, 0.006]), width=0.080, height=0.064,
                             facecolor="black", edgecolor="none", alpha=0.10, zorder=8))
        ax.add_patch(Ellipse(center, width=0.078, height=0.062,
                             facecolor=TEAL_BODY, edgecolor=TEAL, linewidth=1.5, zorder=9))
        ax.add_patch(Ellipse(center + np.array([-0.010, -0.006]), width=0.035, height=0.020,
                             facecolor=TEAL_BODY_LIGHT, edgecolor="none", alpha=0.22, zorder=10))


def _draw_face(ax, head_center, mouth_open_level):
    for side in (-1, 1):
        ax.add_patch(Ellipse(head_center + np.array([side * 0.050, 0.010]), width=0.020, height=0.042,
                             facecolor=SKIN, edgecolor="#D8A57F", linewidth=0.65, zorder=20))
    ax.add_patch(Ellipse(head_center + np.array([0.008, 0.012]), width=HEAD_W * 1.05, height=HEAD_H * 1.05,
                         facecolor="black", edgecolor="none", alpha=0.16, zorder=19))
    ax.add_patch(Ellipse(head_center, width=HEAD_W, height=HEAD_H, facecolor=SKIN,
                         edgecolor=SKIN_EDGE, linewidth=1.7, zorder=21))
    ax.add_patch(Ellipse(head_center + np.array([0.000, -0.052]), width=HEAD_W * 0.94, height=HEAD_H * 0.31,
                         facecolor=HAIR, edgecolor="none", zorder=25))
    ax.add_patch(Polygon([
        (head_center[0] - 0.039, head_center[1] - 0.035),
        (head_center[0] - 0.026, head_center[1] - 0.052),
        (head_center[0] - 0.006, head_center[1] - 0.057),
        (head_center[0] + 0.014, head_center[1] - 0.053),
        (head_center[0] + 0.033, head_center[1] - 0.040),
        (head_center[0] + 0.038, head_center[1] - 0.027),
        (head_center[0] + 0.019, head_center[1] - 0.019),
        (head_center[0] - 0.019, head_center[1] - 0.019),
    ], closed=True, facecolor=HAIR_DARK, edgecolor="none", zorder=26))
    ax.add_patch(Ellipse(head_center + np.array([-0.012, -0.052]), width=0.032, height=0.010,
                         angle=-12, facecolor=HAIR_LIGHT, edgecolor="none", alpha=0.65, zorder=27))

    for eye in (head_center + np.array([-0.023, -0.004]), head_center + np.array([0.023, -0.004])):
        ax.add_patch(Ellipse(eye, width=0.017, height=0.010, facecolor=WHITE,
                             edgecolor="#7A8996", linewidth=0.30, zorder=28))
        ax.add_patch(Circle(eye, radius=0.0030, facecolor=EYE_DARK, edgecolor="none", zorder=29))

    for side in (-1, 1):
        brow_x = head_center[0] + side * 0.023
        brow_y = head_center[1] - 0.020
        ax.plot([brow_x - 0.010, brow_x + 0.010], [brow_y, brow_y - 0.0015],
                color="#201A16", linewidth=1.15, solid_capstyle="round", zorder=31)

    ax.plot([head_center[0] + 0.0015, head_center[0] - 0.0015],
            [head_center[1] + 0.003, head_center[1] + 0.022],
            color="#B57D58", linewidth=0.85, zorder=29)
    ax.add_patch(Ellipse(head_center + np.array([0.000, 0.043]), width=0.026, height=mouth_open_level,
                         facecolor="#6D2424", edgecolor="#321010", linewidth=0.55, zorder=30))


def _draw_raw_working_hand(ax, hand_pts):
    valid = np.isfinite(hand_pts).all(axis=1)
    if not valid.any():
        return

    points = hand_pts.copy()
    palm_ids = [0, 5, 9, 13, 17]
    palm_valid = [points[i] for i in palm_ids if i < len(points) and _valid_point(points[i])]
    center = np.array(palm_valid).mean(axis=0) if len(palm_valid) >= 3 else points[valid].mean(axis=0)

    ax.add_patch(Ellipse(center + np.array([0.0025, 0.0035]), width=PALM_WIDTH, height=PALM_HEIGHT,
                         facecolor="black", edgecolor="none", alpha=0.12, zorder=15))
    ax.add_patch(Ellipse(center, width=PALM_WIDTH, height=PALM_HEIGHT,
                         facecolor=SKIN, edgecolor="white", linewidth=0.9, alpha=0.97, zorder=16))

    for chain in ([1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12], [13, 14, 15, 16], [17, 18, 19, 20]):
        draw_points = [
            points[idx].copy() if idx < len(points) and _valid_point(points[idx]) else np.array([np.nan, np.nan])
            for idx in chain
        ]
        clean_points = []
        for i, point in enumerate(draw_points):
            if i == 0:
                clean_points.append(point)
            else:
                previous = clean_points[-1]
                max_len = MAX_THUMB_SEGMENT if chain[0] == 1 else MAX_FINGER_SEGMENT
                clean_points.append(_clamp_segment(previous, point, max_len) if _valid_point(previous) and _valid_point(point) else point)

        for i in range(len(clean_points) - 1):
            a = clean_points[i]
            b = clean_points[i + 1]
            if _valid_point(a) and _valid_point(b):
                lw = max(1.65, 3.15 - i * 0.45)
                ax.plot([a[0] + 0.002, b[0] + 0.002], [a[1] + 0.002, b[1] + 0.002],
                        linewidth=lw + 0.8, color="black", alpha=0.10, solid_capstyle="round", zorder=16)
                ax.plot([a[0], b[0]], [a[1], b[1]], linewidth=lw,
                        color=FINGER_LINE, alpha=0.98, solid_capstyle="round", zorder=18)

    for idx in (5, 9, 13, 17, 4, 8, 12, 16, 20):
        if idx < len(points) and _valid_point(points[idx]) and np.linalg.norm(points[idx] - center) < HAND_MAX_RADIUS * 1.20:
            ax.scatter(points[idx, 0], points[idx, 1], s=FINGER_POINT_SIZE, color=FINGER_POINT,
                       edgecolors="white", linewidths=0.25, alpha=0.88, zorder=19)


def _prepare_render_state(arr):
    num_frames = arr.shape[0]
    data = arr.reshape(num_frames, 543, 3).astype(float)
    norm_frames = np.zeros((num_frames, 543, 2), dtype=float)
    for i in range(num_frames):
        norm_frames[i] = _normalize_by_pose(data[i])
    norm_frames = _smooth_sequence(norm_frames, alpha=0.84)

    visual_left_label, visual_right_label = _detect_visual_pose_labels(norm_frames)
    hand_for_pose_l, hand_for_pose_r = _detect_hand_to_pose_mapping(norm_frames)
    mouth_levels = _mouth_levels(norm_frames)
    return norm_frames, visual_left_label, visual_right_label, hand_for_pose_l, hand_for_pose_r, mouth_levels


def render_avatar_from_npy(npy_path: str, output_path: str, fps: int = 24, bitrate: int = 5000) -> dict:
    input_path = Path(npy_path)
    output_file = Path(output_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Pose file does not exist: {input_path}")

    arr = np.load(input_path, allow_pickle=True)
    if arr.ndim != 2:
        raise ValueError(f"Expected 2D array like (frames, 1629), got {arr.shape}")
    if arr.shape[1] != 1629:
        raise ValueError(f"Expected 1629 values per frame, got {arr.shape[1]}")
    if arr.shape[0] <= 0:
        raise ValueError("Pose file has no frames.")
    if not writers.is_available("ffmpeg"):
        raise RuntimeError("FFmpeg is not installed or is not available on PATH; avatar MP4 rendering requires ffmpeg.")

    output_file.parent.mkdir(parents=True, exist_ok=True)
    norm_frames, visual_left_label, visual_right_label, hand_for_pose_l, hand_for_pose_r, mouth_levels = _prepare_render_state(arr)
    num_frames = arr.shape[0]

    fig, ax = plt.subplots(figsize=(8, 8), facecolor=BG_DARK)
    fig.patch.set_facecolor(BG_DARK)

    def update(frame_idx):
        ax.clear()
        ax.set_xlim(0, 1)
        ax.set_ylim(1, 0)
        ax.axis("off")

        _draw_background(ax, frame_idx, num_frames)
        points = norm_frames[frame_idx]
        pose = points[POSE_START:POSE_END]
        head_center, neck_top, neck_bottom, left_shoulder_cap, right_shoulder_cap, _, _ = _avatar_points()

        _draw_body(ax)
        _draw_neck(ax, neck_top, neck_bottom)

        left_pose_label, left_anchor, left_elbow, left_wrist = _get_visual_side_motion(
            pose, "left", visual_left_label, visual_right_label
        )
        right_pose_label, right_anchor, right_elbow, right_wrist = _get_visual_side_motion(
            pose, "right", visual_left_label, visual_right_label
        )

        _draw_capsule(ax, left_anchor, left_elbow, ARM_WIDTH, TEAL_SLEEVE, TEAL, z=6)
        _draw_capsule(ax, left_elbow, left_wrist, FOREARM_WIDTH, TEAL_SLEEVE, TEAL, z=7)
        _draw_capsule(ax, right_anchor, right_elbow, ARM_WIDTH, TEAL_SLEEVE, TEAL, z=6)
        _draw_capsule(ax, right_elbow, right_wrist, FOREARM_WIDTH, TEAL_SLEEVE, TEAL, z=7)

        _draw_shoulder_caps(ax, left_shoulder_cap, right_shoulder_cap)
        _draw_face(ax, head_center, mouth_levels[frame_idx])

        left_hand = _prepare_hand(
            _get_hand_group(points, left_pose_label, hand_for_pose_l, hand_for_pose_r),
            left_wrist,
        )
        right_hand = _prepare_hand(
            _get_hand_group(points, right_pose_label, hand_for_pose_l, hand_for_pose_r),
            right_wrist,
        )
        _draw_raw_working_hand(ax, left_hand)
        _draw_raw_working_hand(ax, right_hand)

        for wrist in (left_wrist, right_wrist):
            if _valid_point(wrist):
                ax.add_patch(Circle(wrist, radius=WRIST_RADIUS, facecolor=SKIN,
                                    edgecolor="white", linewidth=0.8, zorder=20))
        return []

    try:
        animation = FuncAnimation(fig, update, frames=num_frames, interval=1000 / fps, blit=False)
        writer = FFMpegWriter(fps=fps, bitrate=bitrate)
        animation.save(str(output_file), writer=writer)
    finally:
        plt.close(fig)

    return {
        "success": True,
        "input_path": str(input_path),
        "output_path": str(output_file),
        "frames": int(num_frames),
        "input_shape": [int(arr.shape[0]), int(arr.shape[1])],
        "fps": int(fps),
        "bitrate": int(bitrate),
    }


def _main():
    parser = argparse.ArgumentParser(description="Render a PharmaSign 2.5D avatar MP4 from a full 1629-dim pose .npy file.")
    parser.add_argument("--input", required=True, help="Input .npy pose path.")
    parser.add_argument("--output", required=True, help="Output .mp4 path.")
    parser.add_argument("--fps", type=int, default=24, help="Output frames per second.")
    parser.add_argument("--bitrate", type=int, default=5000, help="FFmpeg video bitrate.")
    args = parser.parse_args()

    result = render_avatar_from_npy(args.input, args.output, fps=args.fps, bitrate=args.bitrate)
    print(result)


if __name__ == "__main__":
    _main()
