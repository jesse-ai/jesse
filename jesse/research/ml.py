"""
jesse/research/ml.py

Machine-learning utilities for the Jesse research module.

Public API
----------
gather_ml_data   – run a backtest and collect labelled feature data
train_model      – train any sklearn-compatible estimator on that data
load_ml_data_csv – reload previously saved data points from CSV
load_ml_model    – reload a previously saved model + scaler + importance
"""

from __future__ import annotations

import csv
import datetime
import os
from collections import Counter
from typing import Any, Dict, List, Optional

import joblib
import numpy as np
from scipy.stats import rankdata, spearmanr
from sklearn.base import clone
from sklearn.feature_selection import RFE, f_classif, f_regression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    matthews_corrcoef,
    mean_absolute_error,
    mean_squared_error,
    precision_recall_fscore_support,
    r2_score,
    roc_auc_score,
)
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC, SVR


# ─── Print width ──────────────────────────────────────────────────────────────

W = 64


# ═══════════════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════════════


def gather_ml_data(
    config: dict,
    routes: List[Dict],
    data_routes: List[Dict],
    candles: dict,
    warmup_candles: Optional[dict] = None,
    csv_path: Optional[str] = "auto",
    verbose: bool = True,
) -> dict:
    """Run a backtest and collect ML training data recorded by the strategy.

    The strategy must be in its ML gather mode (e.g. ``ML_MODE = "gather"``)
    and must call ``record_features({...})`` and ``record_label(name, value)``
    at the appropriate points in its lifecycle.

    Parameters
    ----------
    config:
        Jesse exchange/backtest config dict – same format as
        ``research.backtest()``.
    routes:
        Strategy routes – same format as ``research.backtest()``.
    data_routes:
        Extra data routes for additional timeframes / symbols.
    candles:
        Trading candles dict – same format as ``research.backtest()``.
    warmup_candles:
        Warm-up candles dict.
    csv_path:
        Where to write the collected data points.  Defaults to ``"auto"``,
        which saves to
        ``strategies/<StrategyName>/ml_data/<StrategyName>_data.csv``
        inside the current Jesse project.  Pass an explicit path string to
        override, or ``None`` to skip writing entirely.
    verbose:
        If True (default) prints a formatted summary to stdout.

    Returns
    -------
    dict
        ``data_points``      – ``list[dict]`` where each dict has
                               ``{time, features, label: {name, value}}``
        ``backtest_metrics`` – standard Jesse metrics dict
    """
    from .backtest import backtest as _run_backtest
    from jesse.routes import router

    backtest_result = _run_backtest(
        config,
        routes,
        data_routes,
        candles,
        warmup_candles,
        fast_mode=True,
    )

    data_points: List[dict] = []
    if router.routes:
        strategy = router.routes[0].strategy
        if hasattr(strategy, "_ml_data_points"):
            data_points = [
                p for p in strategy._ml_data_points
                if p.get("label") is not None
            ]

    metrics = backtest_result.get("metrics", {})

    if not data_points:
        if verbose:
            print("\n  ⚠  No ML data points were collected.")
            print("     Make sure your strategy is in gather mode and calls")
            print("     self.record_features({...}) and self.record_label(name, value).")
        return {"data_points": [], "backtest_metrics": metrics}

    if csv_path == "auto":
        strategy_name = routes[0]["strategy"]
        csv_path = os.path.join(
            "strategies", strategy_name, "ml_data", f"{strategy_name}_data.csv"
        )

    if csv_path:
        _write_csv(data_points, csv_path)

    if verbose:
        _print_gather_report(data_points, metrics, csv_path, routes)

    return {"data_points": data_points, "backtest_metrics": metrics}


def train_model(
    data: List[dict],
    estimator: Any,
    task: str = "binary",
    test_ratio: float = 0.2,
    save_to: Optional[str] = None,
    verbose: bool = True,
    name: Optional[str] = None,
) -> dict:
    """Train an sklearn-compatible estimator on data collected by a Jesse strategy.

    Accepts **any scikit-learn–compatible estimator** and dispatches training,
    metrics, and reporting based on the ``task`` parameter.

    Parameters
    ----------
    data:
        Data points from ``gather_ml_data()`` or ``load_ml_data_csv()``.
        Each dict must have ``{time, features, label: {name, value}}``.
    estimator:
        A scikit-learn–compatible estimator.  For classifiers, it must
        implement ``predict_proba`` (set ``probability=True`` for SVC).
    task:
        One of:

        ``"binary"``      – Two-class classification.  Label is mapped to
                            ``0`` / ``1`` via the positive-class rule
                            (value ``> 0`` or boolean ``True``).
                            Reports: accuracy, ROC AUC, MCC, confusion
                            matrix, calibration, threshold sweep.

        ``"multiclass"``  – Three-or-more class classification.  Raw integer
                            label values are passed directly to the estimator
                            (e.g. ``-1``, ``0``, ``+1`` from triple-barrier).
                            Reports: accuracy, macro F1, MCC, per-class
                            precision/recall/F1, full NxN confusion matrix.

        ``"regression"``  – Continuous-output prediction.  Raw float label
                            values are passed directly to the estimator.
                            Reports: MAE, RMSE, R², Spearman ρ.
    test_ratio:
        Fraction of samples held out as the chronological test set.
    save_to:
        Directory path.  When provided, three files are written:
        ``model.pkl``, ``scaler.pkl``, ``feature_importance.pkl``.
    verbose:
        Print a full training report (default: True).
    name:
        Optional display name shown in the report header.

    Returns
    -------
    dict with keys:
        ``model``               – fitted estimator
        ``scaler``              – fitted ``StandardScaler``
        ``feature_names``       – ``list[str]``
        ``metrics``             – task-specific metrics dict
        ``feature_importance``  – RFE ranks, ANOVA/F-reg values, correlations,
                                  CV impacts, consensus ranks
        ``train_test_info``     – split sizes and date ranges
        For ``"binary"`` only:
        ``calibration``         – probability calibration bucket list
        ``feature_impact``      – per-feature accuracy delta on the test set
        ``class_weights``       – suggested ``{0: float, 1: float}``
    """
    if task not in ("binary", "multiclass", "regression"):
        raise ValueError(f"task must be 'binary', 'multiclass', or 'regression'; got {task!r}")

    if not data:
        raise ValueError("data is empty — nothing to train on.")

    sorted_data   = sorted(data, key=lambda p: p["time"])
    feature_names = sorted(sorted_data[0]["features"].keys())

    X = np.array(
        [[p["features"].get(f, 0.0) for f in feature_names] for p in sorted_data],
        dtype=float,
    )

    # ── Build y depending on task ─────────────────────────────────────────────
    if task == "binary":
        y = np.array(
            [1 if _label_is_positive(p["label"]["value"]) else 0 for p in sorted_data],
            dtype=int,
        )
    elif task == "multiclass":
        y = np.array(
            [int(p["label"]["value"]) for p in sorted_data],
            dtype=int,
        )
    else:  # regression
        y = np.array(
            [float(p["label"]["value"]) for p in sorted_data],
            dtype=float,
        )

    times = [p["time"] for p in sorted_data]

    # ── Chronological split ───────────────────────────────────────────────────
    split = int(len(X) * (1.0 - test_ratio))
    if split == 0 or split >= len(X):
        raise ValueError(
            f"test_ratio={test_ratio} produces an empty train or test set "
            f"for {len(X)} samples."
        )

    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    train_test_info = {
        "train_size":  len(X_train),
        "test_size":   len(X_test),
        "train_start": _ts_to_date(times[0]),
        "train_end":   _ts_to_date(times[split - 1]),
        "test_start":  _ts_to_date(times[split]),
        "test_end":    _ts_to_date(times[-1]),
    }

    # ── Scale features ────────────────────────────────────────────────────────
    scaler         = StandardScaler()
    X_train_scaled = scaler.fit_transform(X_train)
    X_test_scaled  = scaler.transform(X_test)

    label_name = sorted_data[0]["label"].get("name", "label")

    # ── Class weights (binary only, informational) ────────────────────────────
    class_weights: Optional[dict] = None
    if task == "binary":
        counts = np.bincount(y_train)
        if len(counts) >= 2:
            class_weights = {0: 1.0, 1: float(counts[0]) / float(counts[1])}

    # ── Header ────────────────────────────────────────────────────────────────
    if verbose:
        title = f"MODEL TRAINING  ·  {name}" if name else "MODEL TRAINING"
        _header(f"{title}  [{task.upper()}]")

    # ── Dataset overview ──────────────────────────────────────────────────────
    if verbose:
        _print_dataset_section(
            task, feature_names, y_train, y_test,
            train_test_info, class_weights, label_name,
        )

    # ── Feature importance ────────────────────────────────────────────────────
    fi = _compute_feature_importance(
        X_train_scaled, y_train, feature_names, estimator, task
    )
    if verbose:
        _section("FEATURE IMPORTANCE")
        _print_feature_importance_table(fi, task)

    # ── Fit the model ─────────────────────────────────────────────────────────
    if verbose:
        _section("FIT")
        print(f"\n  Fitting {type(estimator).__name__} on {len(X_train):,} samples …")

    fitted: Any = clone(estimator)
    fitted.fit(X_train_scaled, y_train)

    y_pred = fitted.predict(X_test_scaled)

    # ── Task-specific metrics + reporting ─────────────────────────────────────
    if task == "binary":
        y_probs = fitted.predict_proba(X_test_scaled)[:, 1]
        metrics = _compute_binary_metrics(y_test, y_pred, y_probs)
        if verbose:
            _print_binary_performance(metrics, label_name)

        calibration = _compute_calibration(y_test, y_probs)
        if verbose:
            _print_calibration(calibration)

        feature_impact = _compute_feature_impact(
            X_train_scaled, X_test_scaled, y_train, y_test,
            feature_names, estimator, baseline_metric=metrics["accuracy"],
            task=task,
        )
        if verbose:
            _print_feature_impact(feature_impact, metrics["accuracy"], task)

        base_rate = float(y_test.sum()) / len(y_test)
        if verbose:
            _print_threshold_sweep(y_test, y_probs, base_rate)

    elif task == "multiclass":
        y_probs_mc = fitted.predict_proba(X_test_scaled)
        classes    = fitted.classes_
        metrics    = _compute_multiclass_metrics(y_test, y_pred, y_probs_mc, classes)
        if verbose:
            _print_multiclass_performance(metrics, label_name, classes)

        feature_impact = _compute_feature_impact(
            X_train_scaled, X_test_scaled, y_train, y_test,
            feature_names, estimator, baseline_metric=metrics["accuracy"],
            task=task,
        )
        if verbose:
            _print_feature_impact(feature_impact, metrics["accuracy"], task)

        # no calibration / threshold sweep for multiclass
        calibration = None

    else:  # regression
        metrics = _compute_regression_metrics(y_test, y_pred)
        if verbose:
            _print_regression_performance(metrics, label_name)

        feature_impact = _compute_feature_impact(
            X_train_scaled, X_test_scaled, y_train, y_test,
            feature_names, estimator, baseline_metric=metrics["mae"],
            task=task,
        )
        if verbose:
            _print_feature_impact(feature_impact, metrics["mae"], task)

        calibration = None

    # ── Save artefacts ────────────────────────────────────────────────────────
    if save_to:
        os.makedirs(save_to, exist_ok=True)
        joblib.dump(fitted,  os.path.join(save_to, "model.pkl"))
        joblib.dump(scaler,  os.path.join(save_to, "scaler.pkl"))
        joblib.dump(fi,      os.path.join(save_to, "feature_importance.pkl"))

        if verbose:
            print()
            _footer()
            print(f"  Model    →  {os.path.join(save_to, 'model.pkl')}")
            print(f"  Scaler   →  {os.path.join(save_to, 'scaler.pkl')}")
            _footer()
    elif verbose:
        print()
        _footer()

    result = {
        "model":              fitted,
        "scaler":             scaler,
        "feature_names":      list(feature_names),
        "metrics":            metrics,
        "feature_importance": fi,
        "feature_impact":     feature_impact,
        "train_test_info":    train_test_info,
    }
    if task == "binary":
        result["calibration"]   = calibration
        result["class_weights"] = class_weights
    return result


def load_ml_data_csv(path_or_name: str) -> List[dict]:
    """Reload data points previously saved by ``gather_ml_data``.

    Parameters
    ----------
    path_or_name:
        Either a **strategy name** (e.g. ``"MyStrategy"``) or an explicit
        path to a CSV file.  When a bare name is given (no path separators,
        no ``.csv`` suffix), the file is resolved automatically to
        ``strategies/<name>/ml_data/<name>_data.csv`` inside the current
        Jesse project directory.

    Returns
    -------
    list[dict]
        Same format as the ``data_points`` key returned by
        ``gather_ml_data`` – suitable for passing directly to
        ``train_model``.
    """
    if (
        os.sep not in path_or_name
        and "/" not in path_or_name
        and not path_or_name.endswith(".csv")
    ):
        path = os.path.join(
            "strategies", path_or_name, "ml_data", f"{path_or_name}_data.csv"
        )
    else:
        path = path_or_name

    if not os.path.exists(path):
        raise FileNotFoundError(f"ML data CSV not found: {path}")

    data_points: List[dict] = []
    with open(path, newline="") as f:  # type: ignore[arg-type]
        reader = csv.DictReader(f)
        for row in reader:
            feature_names = [
                k for k in row.keys()
                if k not in ("time", "label_name", "label_value")
            ]
            data_points.append({
                "time":     int(row["time"]),
                "features": {fn: float(row[fn]) for fn in feature_names},
                "label":    {
                    "name":  row["label_name"],
                    "value": _parse_label_value(row["label_value"].strip()),
                },
            })

    return data_points


def load_ml_model(directory: str) -> dict:
    """Load a previously saved model, scaler, and feature importance data.

    Parameters
    ----------
    directory:
        The directory passed as ``save_to`` when ``train_model`` was called.

    Returns
    -------
    dict with keys:
        ``model``               – fitted estimator
        ``scaler``              – fitted ``StandardScaler``
        ``feature_importance``  – feature importance dict (if present)
    """
    model_path  = os.path.join(directory, "model.pkl")
    scaler_path = os.path.join(directory, "scaler.pkl")
    fi_path     = os.path.join(directory, "feature_importance.pkl")

    for p in (model_path, scaler_path):
        if not os.path.exists(p):
            raise FileNotFoundError(f"Expected file not found: {p}")

    result = {
        "model":  joblib.load(model_path),
        "scaler": joblib.load(scaler_path),
    }
    if os.path.exists(fi_path):
        result["feature_importance"] = joblib.load(fi_path)

    return result


# ═══════════════════════════════════════════════════════════════════════════════
# Private: gathering helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _write_csv(data_points: List[dict], path: str) -> None:
    all_features: set = set()
    for p in data_points:
        all_features.update(p["features"].keys())
    sorted_features = sorted(all_features)

    ordered = sorted(data_points, key=lambda p: p["time"])

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["time", "label_name", "label_value"] + sorted_features)
        for p in ordered:
            writer.writerow(
                [p["time"], p["label"]["name"], str(p["label"]["value"])]
                + [str(p["features"].get(fn, "")) for fn in sorted_features]
            )


def _print_gather_report(
    data_points: List[dict],
    metrics: dict,
    csv_path: Optional[str],
    routes: List[Dict],
) -> None:
    strategy_name = routes[0].get("strategy", "") if routes else ""
    title = f"ML DATA COLLECTION  ·  {strategy_name}" if strategy_name else "ML DATA COLLECTION"
    _header(title)

    _section("BACKTEST RESULTS")
    if metrics and metrics.get("total", 0) > 0:
        pnl      = metrics.get("net_profit_percentage", 0)
        annual   = metrics.get("annual_return", 0)
        drawdown = metrics.get("max_drawdown", 0)
        win_rate = metrics.get("win_rate", 0) * 100
        trades   = int(metrics.get("total", 0))
        sharpe   = metrics.get("sharpe_ratio", 0)
        col_w    = 28
        rows = [
            ("PNL",           f"{pnl:+.2f}%",     "Win Rate",     f"{win_rate:.2f}%"),
            ("Annual Return", f"{annual:+.2f}%",   "Total Trades", f"{trades:,}"),
            ("Max Drawdown",  f"{drawdown:+.2f}%", "Sharpe Ratio", f"{sharpe:.2f}"),
        ]
        print()
        for ll, lv, rl, rv in rows:
            left  = f"  {ll:<16} {lv:>8}"
            right = f"  {rl:<16} {rv:>8}"
            print(f"{left:<{col_w}}   {right}")
    else:
        print("\n  No trades were opened during the backtest.")
        print("  The ML gather mode runs on entry signals, not closed trades.")

    _section("DATASET COLLECTED")

    total      = len(data_points)
    features   = len(sorted(set(k for p in data_points for k in p["features"])))
    label_name = data_points[0]["label"].get("name", "label") if data_points else "label"
    timestamps = [p["time"] for p in data_points]
    date_from  = _ts_to_date(min(timestamps))
    date_to    = _ts_to_date(max(timestamps))

    label_counts = Counter(p["label"]["value"] for p in data_points)

    print()
    print(f"  {'Data points':<28} {total:>6,}")
    for lv, cnt in sorted(label_counts.items(), key=lambda x: -x[1]):
        print(f"  {f'{label_name} = {lv}':<28} {cnt:>6,}  ({cnt / total * 100:.1f}%)")
    print(f"  {'Features per sample':<28} {features:>6,}")
    print(f"  {'Date range':<28} {date_from} → {date_to}")

    if csv_path:
        try:
            display = os.path.relpath(csv_path)
        except ValueError:
            display = csv_path
        print(f"  {'Saved to':<28} {display}")

    print()
    _footer()


# ═══════════════════════════════════════════════════════════════════════════════
# Private: label helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_label_value(raw: str):
    """Return the most natural Python type for a label value read from CSV.

    - ``"True"`` / ``"False"`` (case-insensitive) → ``bool``
    - Integer strings (``"1"``, ``"-1"``, ``"0"``) → ``int``
    - Anything else that looks numeric → ``float``
    - Fallback → the original string
    """
    lower = raw.lower()
    if lower == "true":
        return True
    if lower == "false":
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def _label_is_positive(value) -> bool:
    """Map any label value to the binary positive class (1).

    - ``True`` (bool) → positive
    - Positive numbers (``> 0``) → positive
    - Everything else → negative
    """
    if isinstance(value, bool):
        return value
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return str(value).lower() == "true"


# ═══════════════════════════════════════════════════════════════════════════════
# Private: metrics
# ═══════════════════════════════════════════════════════════════════════════════


def _compute_binary_metrics(
    y_test: np.ndarray,
    y_pred: np.ndarray,
    y_probs: np.ndarray,
) -> dict:
    acc                = accuracy_score(y_test, y_pred)
    auc                = roc_auc_score(y_test, y_probs)
    mcc                = matthews_corrcoef(y_test, y_pred)
    cm                 = confusion_matrix(y_test, y_pred)
    tn, fp, fn, tp     = cm.ravel()
    prec, rec, f1, sup = precision_recall_fscore_support(y_test, y_pred, zero_division=0)  # type: ignore[call-overload]
    return {
        "accuracy":         float(acc),
        "roc_auc":          float(auc),
        "mcc":              float(mcc),
        "confusion_matrix": cm.tolist(),
        "precision":        prec.tolist(),
        "recall":           rec.tolist(),
        "f1":               f1.tolist(),
        "support":          sup.tolist(),
        "tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp),
    }


def _compute_multiclass_metrics(
    y_test: np.ndarray,
    y_pred: np.ndarray,
    y_probs: np.ndarray,
    classes: np.ndarray,
) -> dict:
    acc  = accuracy_score(y_test, y_pred)
    mcc  = matthews_corrcoef(y_test, y_pred)
    cm   = confusion_matrix(y_test, y_pred, labels=classes)
    prec, rec, f1, sup = precision_recall_fscore_support(
        y_test, y_pred, labels=classes, zero_division=0  # type: ignore[call-overload]
    )
    try:
        auc = roc_auc_score(
            y_test, y_probs, multi_class="ovr", average="macro", labels=classes
        )
    except Exception:
        auc = float("nan")

    return {
        "accuracy":         float(acc),
        "roc_auc_macro":    float(auc),
        "mcc":              float(mcc),
        "confusion_matrix": cm.tolist(),
        "classes":          classes.tolist(),
        "precision":        prec.tolist(),
        "recall":           rec.tolist(),
        "f1":               f1.tolist(),
        "support":          sup.tolist(),
    }


def _compute_regression_metrics(
    y_test: np.ndarray,
    y_pred: np.ndarray,
) -> dict:
    mae      = mean_absolute_error(y_test, y_pred)
    rmse     = float(np.sqrt(mean_squared_error(y_test, y_pred)))
    r2       = r2_score(y_test, y_pred)
    _sr      = spearmanr(y_test, y_pred)
    _sr_any: Any = _sr
    spearman = float(_sr_any.statistic if hasattr(_sr_any, "statistic") else _sr_any.correlation)
    return {
        "mae":      float(mae),
        "rmse":     float(rmse),
        "r2":       float(r2),
        "spearman": spearman,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Private: feature importance
# ═══════════════════════════════════════════════════════════════════════════════


def _compute_feature_importance(
    X_train: np.ndarray,
    y_train: np.ndarray,
    feature_names: List[str],
    estimator: Any,
    task: str,
    n_splits: int = 5,
) -> dict:
    """Four-method consensus feature importance.

    For classification tasks (binary / multiclass): RFE with a linear SVC
    proxy, ANOVA F-values, absolute Pearson correlation, and CV-impact.

    For regression: RFE with an SVR proxy, F-regression values, absolute
    Pearson correlation, and CV-impact.
    """
    n_features = len(feature_names)
    tscv       = TimeSeriesSplit(n_splits=n_splits)

    if task == "regression":
        proxy_rfe = SVR(kernel="linear")
        proxy_cv  = SVR(kernel="rbf", C=1.0, gamma="scale")
        scoring   = "r2"

        rfe = RFE(proxy_rfe, n_features_to_select=1, step=1)
        rfe.fit(X_train, y_train)
        rfe_ranking = rfe.ranking_.astype(float)

        f_values, _ = f_regression(X_train, y_train)
    else:
        proxy_rfe = SVC(kernel="linear")
        proxy_cv  = SVC(kernel="rbf", C=1.0, gamma="scale")
        scoring   = "accuracy"

        rfe = RFE(proxy_rfe, n_features_to_select=1, step=1)
        rfe.fit(X_train, y_train)
        rfe_ranking = rfe.ranking_.astype(float)

        f_values, _ = f_classif(X_train, y_train)

    correlations = np.array(
        [abs(np.corrcoef(X_train[:, i], y_train)[0, 1]) for i in range(n_features)]
    )

    baseline_cv = cross_val_score(proxy_cv, X_train, y_train, cv=tscv, scoring=scoring).mean()
    cv_without  = np.empty(n_features)
    for i in range(n_features):
        X_r = np.delete(X_train, i, axis=1)
        cv_without[i] = cross_val_score(
            clone(proxy_cv), X_r, y_train, cv=tscv, scoring=scoring
        ).mean()
    cv_impacts = baseline_cv - cv_without

    rfe_ranks   = rfe_ranking
    anova_ranks = rankdata(-f_values)
    corr_ranks  = rankdata(-correlations)
    cv_ranks    = rankdata(-cv_impacts)
    consensus   = (rfe_ranks + anova_ranks + corr_ranks + cv_ranks) / 4.0

    return {
        "feature_names":             list(feature_names),
        "rfe_ranking":               rfe_ranking.tolist(),
        "anova_f_values":            f_values.tolist(),
        "correlations":              correlations.tolist(),
        "cv_baseline":               float(baseline_cv),
        "cv_impacts":                {feature_names[i]: float(cv_impacts[i]) for i in range(n_features)},
        "cv_scores_without_feature": {feature_names[i]: float(cv_without[i])  for i in range(n_features)},
        "consensus_ranks":           {feature_names[i]: float(consensus[i])   for i in range(n_features)},
        "_order":                    np.argsort(consensus).tolist(),
    }


def _compute_calibration(
    y_test: np.ndarray,
    y_probs: np.ndarray,
) -> List[dict]:
    """Bucket predicted probabilities and measure actual positive rate per bin."""
    bins    = [(0.3, 0.4), (0.4, 0.5), (0.5, 0.6), (0.6, 0.7), (0.7, 0.8), (0.8, 1.01)]
    buckets = []
    for lo, hi in bins:
        mask = (y_probs >= lo) & (y_probs < hi)
        n    = int(mask.sum())
        if n == 0:
            continue
        actual = float(y_test[mask].mean())
        mid    = (lo + min(hi, 1.0)) / 2.0
        buckets.append({
            "range":       f"[{lo:.1f}–{min(hi, 1.0):.1f})",
            "n":           n,
            "actual_rate": actual,
            "expected":    mid,
            "diff":        actual - mid,
        })
    return buckets


def _compute_feature_impact(
    X_train: np.ndarray,
    X_test: np.ndarray,  # type: ignore[type-arg]
    y_train: np.ndarray,
    y_test: np.ndarray,
    feature_names: List[str],
    estimator: Any,
    baseline_metric: float,
    task: str,
) -> List[dict]:
    """Retrain the model with each feature removed; measure metric delta.

    For classification tasks: accuracy delta (positive = feature helps).
    For regression: MAE delta (negative = feature helps, since lower MAE is better).
    """
    impacts = []
    for i, fname in enumerate(feature_names):
        X_tr_r = np.delete(X_train, i, axis=1)
        X_te_r = np.delete(X_test,  i, axis=1)
        m: Any = clone(estimator)
        m.fit(X_tr_r, y_train)
        y_p = m.predict(X_te_r)
        if task == "regression":
            metric_i = mean_absolute_error(y_test, y_p)
        else:
            metric_i = accuracy_score(y_test, y_p)
        impacts.append({
            "feature": fname,
            "metric":  float(metric_i),
            "delta":   float(metric_i - baseline_metric),
        })
    impacts.sort(key=lambda x: x["delta"])
    return impacts


# ═══════════════════════════════════════════════════════════════════════════════
# Private: verbose print helpers — shared
# ═══════════════════════════════════════════════════════════════════════════════


def _print_dataset_section(
    task: str,
    feature_names,
    y_train: np.ndarray,
    y_test: np.ndarray,
    train_test_info: dict,
    class_weights: Optional[dict],
    label_name: str,
) -> None:
    _section("DATASET")

    y_all      = np.concatenate([y_train, y_test])
    total      = len(y_all)
    n_features = len(feature_names)

    print(f"\n  {'Samples':<28} {total:>6,}  ({n_features} features)")
    print(f"  {'Train set':<28} {train_test_info['train_size']:>6,}  "
          f"{train_test_info['train_start']} → {train_test_info['train_end']}")
    print(f"  {'Test set':<28} {train_test_info['test_size']:>6,}  "
          f"{train_test_info['test_start']} → {train_test_info['test_end']}")

    if task == "binary":
        n_pos = int((y_all == 1).sum())
        n_neg = total - n_pos
        print(f"  {f'{label_name} = positive':<28} {n_pos:>6,}  ({n_pos / total * 100:.1f}%)")
        print(f"  {f'{label_name} = negative':<28} {n_neg:>6,}  ({n_neg / total * 100:.1f}%)")
        if class_weights is not None:
            print(f"  {'Suggested class weights':<28} "
                  f"0: {class_weights[0]:.2f}  /  1: {class_weights[1]:.2f}")
            print()
            print("  ℹ  Class weights are not applied automatically. Configure them")
            print("     directly on your estimator (e.g. class_weight={0:1.0, 1:2.3}).")
        else:
            print(f"  {'Suggested class weights':<28} N/A  (only one class present)")

    elif task == "multiclass":
        counts = Counter(int(v) for v in y_all)
        for cls, cnt in sorted(counts.items(), key=lambda x: -x[1]):
            print(f"  {f'{label_name} = {cls}':<28} {cnt:>6,}  ({cnt / total * 100:.1f}%)")

    else:  # regression
        print(f"  {'Label mean':<28} {float(y_all.mean()):>10.4f}")
        print(f"  {'Label std':<28} {float(y_all.std()):>10.4f}")
        print(f"  {'Label min':<28} {float(y_all.min()):>10.4f}")
        print(f"  {'Label max':<28} {float(y_all.max()):>10.4f}")


def _print_feature_importance_table(fi: dict, task: str) -> None:
    feature_names = fi["feature_names"]
    rfe_ranking   = fi["rfe_ranking"]
    f_values      = fi["anova_f_values"]
    correlations  = fi["correlations"]
    cv_impacts    = fi["cv_impacts"]
    order         = fi["_order"]
    consensus     = fi["consensus_ranks"]

    f_label = "F-val" if task != "regression" else "F-reg"

    print(
        f"\n  {'Rank':<5} {'Feature':<24} {'RFE':>4}  "
        f"{f_label:>6}  {'|Corr|':>6}  {'CV-Impact':>9}  {'Score':>6}"
    )
    print(
        f"  {'─'*4} {'─'*24} {'─'*4}  "
        f"{'─'*6}  {'─'*6}  {'─'*9}  {'─'*6}"
    )
    for rank_pos, i in enumerate(order, start=1):
        name = feature_names[i]
        print(
            f"  {rank_pos:<5} {name:<24} {int(rfe_ranking[i]):>4}  "
            f"{f_values[i]:>6.2f}  {correlations[i]:>6.3f}  "
            f"{cv_impacts[name]:>+9.4f}  {consensus[name]:>6.2f}"
        )

    print(f"""
  Column guide:
  ┌─────────────┬──────────────────────────────────────────────────────────┐
  │ RFE         │ Recursive Feature Elimination rank (proxy estimator).    │
  │             │ 1 = most important. Lower is better.                     │
  │ {f_label:<11} │ {"ANOVA F-statistic (classification)." if task != "regression" else "F-regression statistic.":<56} │
  │             │ Higher = more discriminative.                            │
  │ |Corr|      │ Absolute Pearson correlation with the label.             │
  │             │ Higher = stronger linear relationship.                   │
  │ CV-Impact   │ Baseline CV metric minus CV metric without this feature. │
  │             │ Positive = feature helps {"(regression: lower MAE = better)." if task == "regression" else "(classification: higher acc)." :<33} │
  │ Score       │ Consensus rank (lower = more consistently important).    │
  └─────────────┴──────────────────────────────────────────────────────────┘""")


# ═══════════════════════════════════════════════════════════════════════════════
# Private: verbose print helpers — binary
# ═══════════════════════════════════════════════════════════════════════════════


def _print_binary_performance(metrics: dict, label_name: str) -> None:
    _section("MODEL PERFORMANCE")

    acc  = metrics["accuracy"]
    auc  = metrics["roc_auc"]
    mcc  = metrics["mcc"]
    tn   = metrics["tn"]
    fp   = metrics["fp"]
    fn   = metrics["fn"]
    tp   = metrics["tp"]
    prec = metrics["precision"]
    rec  = metrics["recall"]
    f1   = metrics["f1"]
    sup  = metrics["support"]

    print(f"\n  Accuracy  {acc * 100:>5.1f}%     ROC AUC  {auc:.3f}     MCC  {mcc:+.3f}")
    print()
    print(f"  {'Confusion Matrix':<28}  Predicted 0   Predicted 1")
    print(f"  {f'Actual 0  ({label_name}=neg)':<28}  {tn:>11,}   {fp:>11,}")
    print(f"  {f'Actual 1  ({label_name}=pos)':<28}  {fn:>11,}   {tp:>11,}")
    print()
    print(f"  {'Class':<14}  {'Precision':>9}  {'Recall':>6}  {'F1':>6}  {'Support':>7}")
    print(f"  {'─'*14}  {'─'*9}  {'─'*6}  {'─'*6}  {'─'*7}")
    print(f"  {'Negative (0)':<14}  {prec[0]:>9.3f}  {rec[0]:>6.3f}  {f1[0]:>6.3f}  {sup[0]:>7,}")
    print(f"  {'Positive (1)':<14}  {prec[1]:>9.3f}  {rec[1]:>6.3f}  {f1[1]:>6.3f}  {sup[1]:>7,}")


def _print_calibration(calibration: List[dict]) -> None:
    _section("PROBABILITY CALIBRATION")

    print(f"\n  {'Confidence':<14}  {'Count':>7}  {'Actual Rate':>11}  {'vs Expected':>12}")
    print(f"  {'─'*14}  {'─'*7}  {'─'*11}  {'─'*12}")

    if not calibration:
        print("  Not enough predictions to populate any bucket.")
    else:
        for b in calibration:
            print(
                f"  {b['range']:<14}  {b['n']:>7,}  "
                f"{b['actual_rate']:>10.1%}  {b['diff']:>+11.1%}"
            )

    print()
    print("  A well-calibrated model shows Actual Rate ≈ midpoint of each bin.")
    print("  Systematic over-confidence → apply Platt scaling or isotonic regression.")
    print("  Use these numbers to choose a confidence threshold for live trading.")


def _print_threshold_sweep(
    y_test: np.ndarray,
    y_probs: np.ndarray,
    base_rate: float,
) -> None:
    _section("PRECISION vs CONFIDENCE THRESHOLD  (class 1 only)")

    print(f"\n  {'Threshold':>10}  {'Allowed':>8}  {'Precision':>9}  {'Coverage':>9}")
    print(f"  {'─'*10}  {'─'*8}  {'─'*9}  {'─'*9}")

    total = len(y_test)
    for thresh in [0.45, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80]:
        mask = y_probs >= thresh
        n    = int(mask.sum())
        if n == 0:
            print(f"  {thresh:>10.2f}  {'—':>8}  {'—':>9}  {'0.0%':>9}")
            continue
        precision = float(y_test[mask].mean())
        coverage  = n / total * 100
        print(f"  {thresh:>10.2f}  {n:>8,}  {precision:>9.1%}  {coverage:>8.1f}%")

    print()
    print(f"  Base rate (no filter): {base_rate:.1%}")
    print("  Threshold = minimum predicted probability to allow a trade through.")
    print("  Precision = fraction of allowed signals that are truly class 1.")
    print("  Coverage  = % of all test signals the model lets through.")
    print()
    print("  A useful operating point is where Precision exceeds the base rate")
    print("  by a meaningful margin while Coverage remains tradeable.")


# ═══════════════════════════════════════════════════════════════════════════════
# Private: verbose print helpers — multiclass
# ═══════════════════════════════════════════════════════════════════════════════


def _print_multiclass_performance(
    metrics: dict,
    label_name: str,
    classes: np.ndarray,
) -> None:
    _section("MODEL PERFORMANCE")

    acc  = metrics["accuracy"]
    mcc  = metrics["mcc"]
    auc  = metrics["roc_auc_macro"]
    cm   = np.array(metrics["confusion_matrix"])
    prec = metrics["precision"]
    rec  = metrics["recall"]
    f1   = metrics["f1"]
    sup  = metrics["support"]

    auc_str = f"{auc:.3f}" if not np.isnan(auc) else "n/a"
    print(f"\n  Accuracy  {acc * 100:>5.1f}%     ROC AUC (macro OVR)  {auc_str}     MCC  {mcc:+.3f}")

    # Confusion matrix
    print()
    header_cells = "  " + " " * 20 + "".join(f"  Pred {c:>3}" for c in classes)
    print(header_cells)
    for i, cls in enumerate(classes):
        row_cells = "  " + f"Actual {cls:>3}  ({label_name})" .ljust(18) + "".join(
            f"  {cm[i, j]:>8,}" for j in range(len(classes))
        )
        print(row_cells)

    # Per-class report
    print()
    print(f"  {'Class':<14}  {'Precision':>9}  {'Recall':>6}  {'F1':>6}  {'Support':>7}")
    print(f"  {'─'*14}  {'─'*9}  {'─'*6}  {'─'*6}  {'─'*7}")
    for i, cls in enumerate(classes):
        print(f"  {str(cls):<14}  {prec[i]:>9.3f}  {rec[i]:>6.3f}  {f1[i]:>6.3f}  {sup[i]:>7,}")


# ═══════════════════════════════════════════════════════════════════════════════
# Private: verbose print helpers — regression
# ═══════════════════════════════════════════════════════════════════════════════


def _print_regression_performance(metrics: dict, label_name: str) -> None:
    _section("MODEL PERFORMANCE")

    mae      = metrics["mae"]
    rmse     = metrics["rmse"]
    r2       = metrics["r2"]
    spearman = metrics["spearman"]

    print(f"\n  MAE       {mae:>10.6f}")
    print(f"  RMSE      {rmse:>10.6f}")
    print(f"  R²        {r2:>10.4f}")
    print(f"  Spearman ρ {spearman:>9.4f}")
    print()
    print("  MAE / RMSE: lower is better. R² and Spearman ρ: higher is better.")
    print("  Spearman ρ measures rank correlation (robust to non-linearity).")
    print("  R² < 0 means the model is worse than simply predicting the mean.")


# ═══════════════════════════════════════════════════════════════════════════════
# Private: verbose print helpers — feature impact (shared)
# ═══════════════════════════════════════════════════════════════════════════════


def _print_feature_impact(
    feature_impact: List[dict],
    baseline_metric: float,
    task: str,
) -> None:
    if task == "regression":
        _section("FEATURE IMPACT  (retrain without each feature, test set MAE)")
        baseline_label = f"Baseline MAE: {baseline_metric:.6f}"
        verdict_help   = "↓ important — keep"
        verdict_noise  = "↑ noisy — consider dropping"
        # For regression, lower MAE = better, so delta < 0 means feature helped
        # (removing it raised MAE).  We invert the sort so most impactful first.
        sorted_impact = sorted(feature_impact, key=lambda x: x["delta"])
    else:
        _section("FEATURE IMPACT  (retrain without each feature, test set accuracy)")
        baseline_label = f"Baseline accuracy: {baseline_metric * 100:.2f}%"
        verdict_help   = "↓ important — keep"
        verdict_noise  = "↑ noisy — consider dropping"
        sorted_impact  = feature_impact  # already sorted ascending (drops come first)

    print(f"\n  {baseline_label}\n")
    metric_label = "MAE" if task == "regression" else "Accuracy"
    print(f"  {'Feature':<24}  {metric_label:>10}  {'Change':>8}  Verdict")
    print(f"  {'─'*24}  {'─'*10}  {'─'*8}  {'─'*22}")

    for item in sorted_impact:
        delta = item["delta"]
        m_val = item["metric"]
        if task == "regression":
            # delta > 0: removing the feature raised MAE → feature was helpful
            # delta < 0: removing it lowered MAE → feature was noisy
            if delta > 0.0:
                verdict = verdict_help
            elif delta < 0.0:
                verdict = verdict_noise
            else:
                verdict = "  neutral"
            print(
                f"  {item['feature']:<24}  {m_val:>10.6f}  {delta:>+8.6f}  {verdict}"
            )
        else:
            if delta < -0.015:
                verdict = verdict_help
            elif delta > 0.015:
                verdict = verdict_noise
            else:
                verdict = "  neutral"
            print(
                f"  {item['feature']:<24}  {m_val * 100:>9.1f}%  {delta:>+7.1%}  {verdict}"
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Private: formatting
# ═══════════════════════════════════════════════════════════════════════════════


def _header(title: str) -> None:
    print("\n" + "═" * W)
    pad = (W - len(title)) // 2
    print(" " * max(0, pad) + title)
    print("═" * W)


def _section(title: str) -> None:
    filler = W - len(title) - 5
    print(f"\n─── {title} {'─' * max(0, filler)}")


def _footer() -> None:
    print("─" * W)


def _ts_to_date(ts: int) -> str:
    return datetime.datetime.fromtimestamp(int(ts), datetime.UTC).strftime("%Y-%m-%d")