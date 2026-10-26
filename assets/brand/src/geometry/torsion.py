# ruff: noqa  -- one-off provenance script for geometry.json, kept as run
import json

import numpy as np
from scipy.spatial.transform import Rotation as Rot

g = json.load(open("geometry.json"))
d = json.load(open("detected.json"))
A = g["atoms"]
P = np.array([[a["x"], a["y"], a["z"]] for a in A])
nb = {i: [] for i in range(len(A))}
for b in g["bonds"]:
    nb[b["a"]].append(b["b"])
    nb[b["b"]].append(b["a"])
lbl = {a["label"]: a["i"] for a in A}


def T(l):
    return np.array([d[l]["x"], d[l]["y"]])


def rotate_group(axis_a, axis_b, hs):
    o = P[axis_a]
    k = P[axis_b] - o
    k /= np.linalg.norm(k)
    best = (1e18, 0)
    for ang in np.linspace(0, 2 * np.pi, 721):
        R = Rot.from_rotvec(k * ang).as_matrix()
        Q = (P[hs] - P[axis_b]) @ R.T + P[axis_b]
        # assignment free for methyl: min over permutations
        import itertools

        labs = [A[h]["label"] for h in hs]
        e = min(
            sum(((Q[i, :2] - T(pl[i])) ** 2).sum() for i in range(len(hs)))
            for pl in itertools.permutations(labs)
        )
        if e < best[0]:
            best = (e, ang)
    R = Rot.from_rotvec(k * best[1]).as_matrix()
    P[hs] = (P[hs] - P[axis_b]) @ R.T + P[axis_b]
    print(
        "rot",
        [A[h]["label"] for h in hs],
        round(np.degrees(best[1])),
        round(np.sqrt(best[0] / len(hs)), 1),
    )


# hydroxyls: rotate H about C-O axis
for O in ["O1", "O2", "O3"]:
    o = lbl[O]
    h = [n for n in nb[o] if A[n]["el"] == "H"]
    c = [n for n in nb[o] if A[n]["el"] == "C"][0]
    rotate_group(c, o, h)
# methyl about N-C1
c1 = lbl["C1"]
rotate_group(lbl["N"], c1, [n for n in nb[c1] if A[n]["el"] == "H"])
# N-H: invert / rotate about bisector of C-N-C
n = lbl["N"]
cs = [x for x in nb[n] if A[x]["el"] == "C"]
h = [x for x in nb[n] if A[x]["el"] == "H"][0]
u = sum((P[c] - P[n]) / np.linalg.norm(P[c] - P[n]) for c in cs)
u /= np.linalg.norm(u)
L = np.linalg.norm(P[h] - P[n])
best = None
v = P[h] - P[n]  # candidates: reflect through plane of C-N-C, and original
nrm = np.cross(P[cs[0]] - P[n], P[cs[1]] - P[n])
nrm /= np.linalg.norm(nrm)
for cand in [v, v - 2 * np.dot(v, nrm) * nrm]:
    e = ((P[n, :2] + cand[:2] - T("HN")) ** 2).sum()
    if best is None or e < best[0]:
        best = (e, cand)
P[h] = P[n] + best[1]
print("HN err", round(np.sqrt(best[0]), 1))
for a, p in zip(A, P):
    a["x"], a["y"], a["z"] = [round(float(v), 2) for v in p]
json.dump(g, open("geometry.json", "w"), indent=1)
