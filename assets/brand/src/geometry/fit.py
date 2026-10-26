# ruff: noqa  -- one-off provenance script for geometry.json, kept as run
import itertools
import json

import numpy as np
from rdkit import Chem
from rdkit.Chem import AllChem
from scipy.optimize import minimize
from scipy.spatial.transform import Rotation as Rot

det = json.load(open("detected.json"))
heavy = {
    0: "C1",
    1: "N",
    2: "C2",
    3: "C3",
    4: "O1",
    5: "Ca",
    6: "Cb",
    7: "Cc",
    8: "Cd",
    9: "O2",
    10: "Ce",
    11: "O3",
    12: "Cf",
}


def build(smi):
    m = Chem.AddHs(Chem.MolFromSmiles(smi))
    cids = AllChem.EmbedMultipleConfs(m, numConfs=150, randomSeed=7)
    AllChem.MMFFOptimizeMoleculeConfs(m, maxIters=2000)
    return m, list(cids)


def hmap(m):
    # H groups by parent heavy atom
    g = {}
    for a in m.GetAtoms():
        if a.GetSymbol() == "H":
            g.setdefault(a.GetNeighbors()[0].GetIdx(), []).append(a.GetIdx())
    return g


labelsH = {
    0: ["H1a", "H1b", "H1c"],
    1: ["HN"],
    2: ["H2a", "H2b"],
    3: ["H3"],
    4: ["HO1"],
    6: ["Hb"],
    7: ["Hc"],
    9: ["HO2"],
    11: ["HO3"],
    12: ["Hf"],
}


def target(lbl):
    d = det[lbl]
    return np.array([d["x"], -d["y"]])


def proj(params, X):
    R = Rot.from_rotvec(params[:3]).as_matrix()
    s = params[3]
    t = params[4:6]
    d = params[6] if len(params) > 6 else 1e6
    Q = X @ R.T
    f = d / (d - Q[:, 2:3])
    return s * Q[:, :2] * f + t


def fit(X, Y, starts=24, rng=np.random.default_rng(0)):
    best = None
    for i in range(starts):
        p0 = np.r_[Rot.random(random_state=i).as_rotvec(), 180, Y.mean(0)]
        r = minimize(lambda p: ((proj(p, X) - Y) ** 2).sum(), p0, method="BFGS")
        if best is None or r.fun < best.fun:
            best = r
    return best


results = []
for name, smi in [("R", "CNC[C@@H](O)c1ccc(O)c(O)c1"), ("S", "CNC[C@H](O)c1ccc(O)c(O)c1")]:
    m, cids = build(smi)
    from rdkit.Chem import rdCIPLabeler

    rdCIPLabeler.AssignCIPLabels(m)
    print(name, "CIP", m.GetAtomWithIdx(3).GetProp("_CIPCode"))
    g = hmap(m)
    for cid in cids:
        P = m.GetConformer(cid).GetPositions()
        idx = list(heavy)
        Y = np.array([target(heavy[i]) for i in idx])
        r = fit(P[idx], Y, starts=6)
        # H assignment: best perms
        Hidx = []
        Hlab = []
        for parent, labs in labelsH.items():
            hs = g[parent]
            pr = proj(r.x, P[hs])
            bestperm = min(
                itertools.permutations(labs),
                key=lambda pl: sum(((pr[k] - target(pl[k])) ** 2).sum() for k in range(len(pl))),
            )
            Hidx += hs
            Hlab += list(bestperm)
        allidx = idx + Hidx
        Yall = np.array([target(heavy[i]) for i in idx] + [target(l) for l in Hlab])
        r2 = min(
            (
                minimize(
                    lambda p: ((proj(p, P[allidx]) - Yall) ** 2).sum() + 0 * p[6],
                    np.r_[r.x, d0],
                    method="Nelder-Mead",
                    options=dict(maxiter=6000, xatol=1e-4, fatol=1e-3),
                )
                for d0 in (8, 15, 30)
            ),
            key=lambda q: q.fun,
        )
        rms = np.sqrt(r2.fun / len(allidx))
        results.append(
            (rms, name, cid, r2.x, dict(zip(allidx, [heavy.get(i) for i in idx] + Hlab)), P, m)
        )
    results.sort(key=lambda t: t[0])
    print(name, [round(t[0], 1) for t in results if t[1] == name][:5])
results.sort(key=lambda t: t[0])
rms, name, cid, x, lab, P, m = [t for t in results if t[1] == "S"][
    0
]  # key 'S' smiles == CIP R (natural L-epinephrine)
print("chosen", name, cid, rms)
R = Rot.from_rotvec(x[:3]).as_matrix()
Q0 = P @ R.T
f = x[6] / (x[6] - Q0[:, 2:3])
Q = np.c_[Q0[:, :2] * f, Q0[:, 2:3]] * x[3]
print("persp d", x[6])
atoms = []
for i in range(m.GetNumAtoms()):
    atoms.append(
        dict(
            i=i,
            el=m.GetAtomWithIdx(i).GetSymbol(),
            label=lab[i],
            x=round(Q[i, 0] + x[4], 2),
            y=round(-(Q[i, 1] + x[5]), 2),
            z=round(Q[i, 2], 2),
        )
    )
bonds = [
    dict(a=b.GetBeginAtomIdx(), b=b.GetEndAtomIdx(), arom=b.GetIsAromatic()) for b in m.GetBonds()
]
json.dump(
    dict(stereo=name, rms=rms, atoms=atoms, bonds=bonds), open("geometry.json", "w"), indent=1
)
