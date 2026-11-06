"""Module F: unsupervised statistical anomaly detection.

These methods describe how *unusual* a window is relative to the rest of the same
recording. They are deliberately kept apart from manipulation evidence: every finding
is category ``statistical`` with family ``statistical``, and the correlation engine
never counts them as independent corroboration.

F1  Robust z-score / MAD outliers per feature (Iglewicz & Hoaglin, 1993).
F2  Isolation Forest (Liu, Ting & Zhou, ICDM 2008) on window feature vectors.
F3  PELT change-point detection, Gaussian mean-shift cost (Killick, Fearnhead & Eckley, JASA 2012).
F4  Window-based comparison: two-sample Kolmogorov-Smirnov test on quiet-frame flatness.
F5  Delta-BIC segmentation on MFCCs (Chen & Gopalakrishnan, DARPA BNTU Workshop 1998).
"""

from __future__ import annotations

import numpy as np
from scipy.stats import ks_2samp

from ..evidence.evidence_model import Category, EvidenceRegistry, Localization, Severity, TestResult
from .context import AnalysisContext
from .stats import local_maxima, robust_z

FEATURES = ["level_median_db", "level_p10_db", "centroid_hz", "flatness", "zcr", "rolloff_hz", "mfcc1", "mfcc2", "mfcc3", "mfcc4"]


def window_features(ctx: AnalysisContext) -> tuple[np.ndarray, np.ndarray]:
    ff, sp = ctx.frames, ctx.spectral
    n = min(len(ff.rms_db), sp.mfcc.shape[1])
    per = max(2, int(round(ctx.config.anomaly_window_s * ctx.sr / ctx.hop)))
    rows, times = [], []
    for s in range(0, n - per + 1, max(1, per // 2)):
        sl = slice(s, s + per)
        rows.append([
            np.median(ff.rms_db[sl]), np.percentile(ff.rms_db[sl], 10), np.median(sp.centroid[sl]),
            np.median(sp.flatness[sl]), np.median(ff.zcr[sl]), np.median(sp.rolloff[sl]),
            *np.mean(sp.mfcc[1:5, sl], axis=1),
        ])
        times.append((float(ff.times[s]), float(ff.times[min(s + per, n) - 1])))
    return np.array(rows), np.array(times)


def _standardise(X: np.ndarray) -> np.ndarray:
    return np.column_stack([robust_z(X[:, j]) for j in range(X.shape[1])]) if X.size else X


def run_robust_outliers(ctx: AnalysisContext, reg: EvidenceRegistry, X: np.ndarray, T: np.ndarray) -> TestResult:
    cfg = ctx.config
    test = TestResult("F1", "Robust z-score / MAD outlier windows", "F: statistics", "statistical",
                      score_name="max |modified z|", threshold=cfg.robust_z_threshold)
    if len(X) < 8:
        test.status = "not_applicable"
        test.summary = "Fewer than 8 analysis windows."
        return test
    Z = _standardise(X)
    zmax = np.max(np.abs(Z), axis=1)
    test.score = float(zmax.max())
    out = np.flatnonzero(zmax > cfg.robust_z_threshold)
    test.measurements = {"windows": len(X), "outlier_windows": int(out.size),
                         "outlier_fraction": float(out.size / len(X)), "features": FEATURES}
    strong = [i for i in local_maxima(zmax, radius=1) if zmax[i] > 2 * cfg.robust_z_threshold][:5]
    for i in strong:
        feat = FEATURES[int(np.argmax(np.abs(Z[i])))]
        f = reg.add_finding(
            "ANO", test_id=test.test_id, module=test.module, method="modified z-score (median/MAD)", family="statistical",
            category=Category.STATISTICAL, severity=Severity.INFO,
            title=f"Statistically unusual window {T[i][0]:.2f}-{T[i][1]:.2f} s ({feat})",
            description=f"Feature '{feat}' deviates by {Z[i].max() if Z[i].max() > -Z[i].min() else Z[i].min():.1f} robust standard deviations from the recording's median.",
            localization=Localization.REGION, time_start=T[i][0], time_end=T[i][1],
            measurements={"max_abs_z": zmax[i], "feature": feat}, baseline={"z_threshold": cfg.robust_z_threshold},
            alternative_explanations=["Natural variation of content (loud passage, silence, different sound)"],
            limitations=["Unusual is not the same as manipulated."],
        )
        test.finding_ids.append(f.finding_id)
    test.detected = bool(strong)
    test.summary = f"{out.size} of {len(X)} windows exceed |z| > {cfg.robust_z_threshold} on at least one feature."
    return test


def run_isolation_forest(ctx: AnalysisContext, reg: EvidenceRegistry, X: np.ndarray, T: np.ndarray) -> TestResult:
    from sklearn.ensemble import IsolationForest

    cfg = ctx.config
    test = TestResult("F2", "Isolation Forest window anomalies", "F: statistics", "statistical",
                      score_name="min decision function")
    if len(X) < 16:
        test.status = "not_applicable"
        test.summary = "Fewer than 16 analysis windows; Isolation Forest would be meaningless."
        return test
    model = IsolationForest(n_estimators=cfg.isolation_forest_estimators, contamination="auto", random_state=cfg.seed)
    Z = _standardise(X)
    model.fit(Z)
    dec = model.decision_function(Z)
    test.score = float(dec.min())
    out = np.flatnonzero(dec < 0)
    test.measurements = {"windows": len(X), "anomalous_windows": int(out.size), "random_state": cfg.seed}
    for i in out[np.argsort(dec[out])][:3]:
        f = reg.add_finding(
            "ANO", test_id=test.test_id, module=test.module, method="IsolationForest (scikit-learn)", family="statistical",
            category=Category.STATISTICAL, severity=Severity.INFO,
            title=f"Isolation Forest anomaly {T[i][0]:.2f}-{T[i][1]:.2f} s",
            description=f"Decision function {dec[i]:.3f} (< 0 means easier to isolate than typical windows).",
            localization=Localization.REGION, time_start=T[i][0], time_end=T[i][1],
            measurements={"decision_function": dec[i]}, alternative_explanations=["Natural content variation"],
            limitations=["Unsupervised; trained on the file itself; not a manipulation classifier."],
        )
        test.finding_ids.append(f.finding_id)
    test.detected = bool(out.size)
    test.summary = f"{out.size} of {len(X)} windows flagged as anomalous by Isolation Forest."
    return test


def pelt(X: np.ndarray, penalty: float, min_size: int = 2) -> list[int]:
    """PELT with the Gaussian mean-shift (L2) cost; returns change-point indices."""
    n = len(X)
    cs = np.vstack([np.zeros(X.shape[1]), np.cumsum(X, axis=0)])
    cs2 = np.concatenate([[0.0], np.cumsum(np.sum(X * X, axis=1))])

    def cost(a: int, b: int) -> float:
        s = cs[b] - cs[a]
        return float(cs2[b] - cs2[a] - np.dot(s, s) / (b - a))

    F = np.full(n + 1, np.inf)
    F[0] = -penalty
    last = np.zeros(n + 1, dtype=int)
    cands = [0]
    for t in range(min_size, n + 1):
        vals = [F[s] + cost(s, t) + penalty if t - s >= min_size else np.inf for s in cands]
        k = int(np.argmin(vals))
        F[t] = vals[k]
        last[t] = cands[k]
        cands = [s for s, v in zip(cands, vals) if v - penalty <= F[t]] + [t - min_size + 1]
    cps, t = [], n
    while t > 0:
        t = last[t]
        if t > 0:
            cps.append(t)
    return sorted(cps)


def run_change_points(ctx: AnalysisContext, reg: EvidenceRegistry, X: np.ndarray, T: np.ndarray) -> TestResult:
    cfg = ctx.config
    test = TestResult("F3", "PELT change-point detection", "F: statistics", "statistical", score_name="change points")
    if len(X) < 8:
        test.status = "not_applicable"
        test.summary = "Fewer than 8 analysis windows."
        return test
    Z = np.clip(_standardise(X), -10, 10)
    penalty = cfg.pelt_penalty_beta * Z.shape[1] * np.log(len(Z))
    cps = pelt(Z, penalty)
    test.score = float(len(cps))
    test.measurements = {"penalty": penalty, "change_points": [float(T[c][0]) for c in cps]}
    for c in cps[:10]:
        t = float(T[c][0])
        f = reg.add_finding(
            "ANO", test_id=test.test_id, module=test.module, method="PELT, Gaussian mean-shift cost", family="statistical",
            category=Category.STATISTICAL, severity=Severity.INFO, title=f"Feature-distribution change point near {t:.2f} s",
            description="The multivariate feature mean changes here enough to pay the BIC-style penalty.",
            localization=Localization.POINT, time_start=max(0.0, t - cfg.anomaly_window_s / 2), time_end=t + cfg.anomaly_window_s / 2,
            measurements={"penalty": penalty}, alternative_explanations=["Change of content (speaker, phrase, instrument)"],
            limitations=["Window resolution only; content changes are expected in natural recordings."],
        )
        test.finding_ids.append(f.finding_id)
    test.detected = bool(cps)
    test.summary = f"{len(cps)} change point(s) in window features."
    return test


def run_ks_windows(ctx: AnalysisContext, reg: EvidenceRegistry) -> TestResult:
    cfg = ctx.config
    test = TestResult("F4", "Adjacent-window KS test on quiet-frame flatness", "F: statistics", "statistical",
                      score_name="max KS statistic D", threshold=cfg.ks_min_d)
    ff, sp = ctx.frames, ctx.spectral
    per = max(8, int(round(1.0 * ctx.sr / ctx.hop)))
    n = min(len(ff.rms_db), len(sp.flatness))
    if n < 3 * per:
        test.status = "not_applicable"
        test.summary = "Recording shorter than 3 s."
        return test
    best, hits = 0.0, []
    for b in range(per, n - per, per // 2):
        L, R = slice(b - per, b), slice(b, b + per)
        lq = sp.flatness[L][ff.rms_db[L] <= np.percentile(ff.rms_db[L], 50)]
        rq = sp.flatness[R][ff.rms_db[R] <= np.percentile(ff.rms_db[R], 50)]
        if len(lq) < 8 or len(rq) < 8:
            continue
        res = ks_2samp(lq, rq)
        best = max(best, float(res.statistic))
        if res.pvalue < cfg.ks_alpha and res.statistic >= cfg.ks_min_d:
            hits.append((float(res.statistic), float(res.pvalue), float(ff.times[b])))
    test.score = best
    test.measurements = {"tests_run": int((n - 2 * per) / (per // 2)), "significant": len(hits), "alpha": cfg.ks_alpha}
    for d, p, t in sorted(hits, reverse=True)[:5]:
        f = reg.add_finding(
            "ANO", test_id=test.test_id, module=test.module, method="two-sample Kolmogorov-Smirnov", family="statistical",
            category=Category.STATISTICAL, severity=Severity.INFO, title=f"Background texture differs across {t:.2f} s",
            description=f"Spectral flatness of the quieter frames differs between the 1 s before and after (D = {d:.2f}, p = {p:.1e}).",
            localization=Localization.POINT, time_start=max(0.0, t - 0.25), time_end=t + 0.25,
            measurements={"ks_d": d, "p_value": p}, baseline={"alpha": cfg.ks_alpha, "min_d": cfg.ks_min_d},
            alternative_explanations=["Change of content density", "Environmental change", "Splice"],
            limitations=["Many overlapping tests are run; p-values are not corrected for multiplicity."],
        )
        test.finding_ids.append(f.finding_id)
    test.detected = bool(hits)
    test.summary = f"{len(hits)} significant window pair(s) (max D = {best:.2f})."
    return test


def run_delta_bic(ctx: AnalysisContext, reg: EvidenceRegistry) -> TestResult:
    cfg = ctx.config
    test = TestResult("F5", "Delta-BIC segmentation on MFCCs", "F: statistics", "statistical", score_name="max delta-BIC")
    M = ctx.spectral.mfcc[1:13].T
    per = max(20, int(round(1.0 * ctx.sr / ctx.hop)))
    if len(M) < 3 * per:
        test.status = "not_applicable"
        test.summary = "Recording shorter than 3 s."
        return test
    d = M.shape[1]
    lam = cfg.bic_lambda
    pen = 0.5 * lam * (d + 0.5 * d * (d + 1)) * np.log(2 * per)

    def logdet(A: np.ndarray) -> float:
        s, v = np.linalg.slogdet(np.cov(A, rowvar=False) + 1e-6 * np.eye(d))
        return float(v)

    scores, times = [], []
    for b in range(per, len(M) - per, max(1, per // 5)):
        both = M[b - per : b + per]
        val = per * logdet(both) - 0.5 * per * logdet(M[b - per : b]) - 0.5 * per * logdet(M[b : b + per]) - pen
        scores.append(val)
        times.append(float(ctx.frames.times[min(b, len(ctx.frames.times) - 1)]))
    sc = np.array(scores)
    test.score = float(sc.max())
    peaks = [p for p in local_maxima(sc, radius=5) if sc[p] > 0]
    test.measurements = {"positive_delta_bic_points": len(peaks), "lambda": lam}
    for p in peaks[:5]:
        f = reg.add_finding(
            "ANO", test_id=test.test_id, module=test.module, method="delta-BIC, full-covariance Gaussians", family="statistical",
            category=Category.STATISTICAL, severity=Severity.INFO, title=f"MFCC model change near {times[p]:.2f} s",
            description=f"Two Gaussians fit the MFCCs around this point better than one (delta-BIC = {sc[p]:.1f}).",
            localization=Localization.POINT, time_start=max(0.0, times[p] - 0.25), time_end=times[p] + 0.25,
            measurements={"delta_bic": sc[p]}, alternative_explanations=["Speaker/phoneme/content change", "Channel or environment change"],
            limitations=["Designed for speaker-change detection; content changes in one take also trigger it."],
        )
        test.finding_ids.append(f.finding_id)
    test.detected = bool(peaks)
    test.summary = f"{len(peaks)} positive delta-BIC point(s)."
    return test


def run_anomaly_suite(ctx: AnalysisContext, reg: EvidenceRegistry) -> list[TestResult]:
    X, T = window_features(ctx)
    return [
        run_robust_outliers(ctx, reg, X, T),
        run_isolation_forest(ctx, reg, X, T),
        run_change_points(ctx, reg, X, T),
        run_ks_windows(ctx, reg),
        run_delta_bic(ctx, reg),
    ]
