"""Tests des tests de Kolmogorov–Smirnov et statistiques de validation."""

import random

import pytest

from hospital_simulator import describe, ks_exponential, ks_one_sample, ks_two_sample


class TestDescribe:
    def test_basic(self):
        d = describe([1.0, 2.0, 3.0])
        assert d["n"] == 3
        assert d["mean"] == pytest.approx(2.0)
        assert d["median"] == pytest.approx(2.0)

    def test_empty(self):
        assert describe([]) == {"n": 0}


class TestKsTwoSample:
    def test_same_distribution_not_rejected(self):
        rng = random.Random(0)
        a = [rng.gauss(0, 1) for _ in range(500)]
        b = [rng.gauss(0, 1) for _ in range(500)]
        d, p = ks_two_sample(a, b)
        assert 0.0 <= d <= 1.0
        assert p > 0.05  # ne rejette pas l'égalité

    def test_different_distributions_rejected(self):
        rng = random.Random(0)
        a = [rng.gauss(0, 1) for _ in range(500)]
        b = [rng.gauss(3, 1) for _ in range(500)]
        d, p = ks_two_sample(a, b)
        assert d > 0.5
        assert p < 0.05

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            ks_two_sample([], [1.0])


class TestKsExponential:
    def test_exponential_sample_not_rejected(self):
        rng = random.Random(1)
        mean = 4.0
        sample = [rng.expovariate(1.0 / mean) for _ in range(600)]
        d, p = ks_exponential(sample, mean)
        assert p > 0.05  # l'hypothèse exponentielle tient

    def test_non_exponential_sample_rejected(self):
        rng = random.Random(1)
        # Échantillon uniforme : clairement pas exponentiel.
        sample = [rng.uniform(3.5, 4.5) for _ in range(400)]
        d, p = ks_exponential(sample, mean=4.0)
        assert p < 0.05

    def test_invalid_mean_raises(self):
        with pytest.raises(ValueError):
            ks_exponential([1.0, 2.0], mean=0)


class TestKsOneSample:
    def test_uniform_cdf_not_rejected(self):
        rng = random.Random(2)
        sample = [rng.random() for _ in range(500)]
        d, p = ks_one_sample(sample, lambda x: min(1.0, max(0.0, x)))
        assert p > 0.05
