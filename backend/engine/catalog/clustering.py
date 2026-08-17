"""Clustering models: K-Means, DBSCAN, Agglomerative."""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN, AgglomerativeClustering, KMeans
from sklearn.decomposition import PCA
from sklearn.metrics import davies_bouldin_score, silhouette_score

from .base import ModelPlugin, ParamSpec, register
from .preprocess import RANDOM_SEED, build_preprocessor, processed_feature_names, structural_frame

MAX_SCATTER_POINTS = 2000


def _scaled_matrix(df, target, features):
    """Fold-safe prep for distance-based models: impute/encode/scale are all
    FIT on the frame passed in - so subsample stability draws refit them per
    draw instead of inheriting full-frame statistics."""
    from sklearn.pipeline import Pipeline as SkPipeline
    from sklearn.preprocessing import StandardScaler

    X = structural_frame(df, target=target, features=features)
    if X.empty:
        raise ValueError("No usable features for clustering.")
    prep = SkPipeline([("prep", build_preprocessor()), ("scale", StandardScaler())])
    Xs = prep.fit_transform(X)
    names = processed_feature_names(prep) or [str(c) for c in X.columns]
    return Xs, names


def _cluster_artifacts(X_scaled: np.ndarray, labels: np.ndarray, feature_names: list[str]) -> dict[str, Any]:
    """Metrics + 2-D PCA scatter for any clustering result."""
    unique = sorted(set(int(l) for l in labels))
    real_clusters = [u for u in unique if u != -1]

    metrics: dict[str, Any] = {
        "n_clusters_found": len(real_clusters),
        "n_noise_points": int(np.sum(labels == -1)),
    }
    if len(real_clusters) >= 2:
        mask = labels != -1
        try:
            metrics["silhouette"] = round(float(silhouette_score(X_scaled[mask], labels[mask])), 4)
            metrics["davies_bouldin"] = round(float(davies_bouldin_score(X_scaled[mask], labels[mask])), 4)
        except ValueError:
            pass

    # 2-D projection for the scatter chart.
    if X_scaled.shape[1] >= 2:
        coords = PCA(n_components=2, random_state=RANDOM_SEED).fit_transform(X_scaled)
        axis_labels = ["PC1", "PC2"]
    else:
        coords = np.column_stack([X_scaled[:, 0], np.zeros(len(X_scaled))])
        axis_labels = [feature_names[0] if feature_names else "x", ""]

    n = len(coords)
    idx = np.random.default_rng(RANDOM_SEED).choice(n, size=min(n, MAX_SCATTER_POINTS), replace=False)
    scatter = [
        {"x": round(float(coords[i, 0]), 4), "y": round(float(coords[i, 1]), 4), "cluster": int(labels[i])}
        for i in idx
    ]

    sizes = [{"cluster": u, "count": int(np.sum(labels == u))} for u in unique]

    return {
        "metrics": metrics,
        "artifacts": {
            "scatter": {"points": scatter, "axes": axis_labels},
            "cluster_sizes": sizes,
            # Full per-row labels for the insight engine; stripped from the API
            # payload by the orchestrator after insights are computed.
            "labels": [int(l) for l in labels],
        },
    }


@register
class KMeansModel(ModelPlugin):
    key = "kmeans"
    name = "K-Means"
    use_case = "clustering"
    description = "Partitions data into k spherical clusters by minimizing within-cluster variance."
    strengths = "Fast and scalable; the default choice when you have a rough idea of the number of groups and clusters are roughly globular."

    def param_schema(self) -> list[ParamSpec]:
        return [
            ParamSpec("n_clusters", "Number of clusters (k)", "int", 3, "How many groups to find.", min=2, max=20, step=1),
            ParamSpec("n_init", "Initializations", "int", 10, "Restarts; best result kept.", min=1, max=50, step=1),
        ]

    def run(self, df, hyperparams, target=None, features=None, time_column=None):
        Xs, names = _scaled_matrix(df, target, features)
        model = KMeans(n_clusters=hyperparams["n_clusters"], n_init=hyperparams["n_init"], random_state=RANDOM_SEED)
        labels = model.fit_predict(Xs)
        result = _cluster_artifacts(Xs, labels, names)
        result["metrics"]["inertia"] = round(float(model.inertia_), 2)
        return result


@register
class DBSCANModel(ModelPlugin):
    key = "dbscan"
    name = "DBSCAN"
    use_case = "clustering"
    description = "Density-based clustering; finds arbitrarily-shaped clusters and flags outliers as noise."
    strengths = "No need to choose k; discovers irregular cluster shapes; naturally identifies outliers/anomalies as noise points."

    def param_schema(self) -> list[ParamSpec]:
        return [
            ParamSpec("eps", "Neighborhood radius (eps)", "float", 0.5, "Max distance between neighbors (on scaled data).", min=0.05, max=10, step=0.05),
            ParamSpec("min_samples", "Min samples per core point", "int", 5, "Density threshold for a cluster.", min=2, max=100, step=1),
        ]

    def run(self, df, hyperparams, target=None, features=None, time_column=None):
        Xs, names = _scaled_matrix(df, target, features)
        labels = DBSCAN(eps=hyperparams["eps"], min_samples=hyperparams["min_samples"]).fit_predict(Xs)
        return _cluster_artifacts(Xs, labels, names)


@register
class AgglomerativeModel(ModelPlugin):
    key = "agglomerative"
    name = "Agglomerative Clustering"
    use_case = "clustering"
    description = "Hierarchical bottom-up clustering merging the closest groups step by step."
    strengths = "Good when clusters are nested or vary in size; linkage choice adapts to different cluster geometries."

    def param_schema(self) -> list[ParamSpec]:
        return [
            ParamSpec("n_clusters", "Number of clusters", "int", 3, "How many groups to keep.", min=2, max=20, step=1),
            ParamSpec("linkage", "Linkage", "select", "ward", "How cluster distance is computed.",
                      options=["ward", "complete", "average", "single"]),
        ]

    def run(self, df, hyperparams, target=None, features=None, time_column=None):
        Xs, names = _scaled_matrix(df, target, features)
        labels = AgglomerativeClustering(
            n_clusters=hyperparams["n_clusters"], linkage=hyperparams["linkage"]
        ).fit_predict(Xs)
        return _cluster_artifacts(Xs, labels, names)
