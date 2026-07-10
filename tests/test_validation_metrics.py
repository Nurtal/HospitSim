"""Tests Phase 1 : métriques de validation opérationnelle + séries observées."""

import random
from datetime import date

import pytest

from hospital_simulator import (
    Scenario,
    bias,
    census_sample,
    ci_coverage,
    daily_arrivals,
    daily_census,
    mae,
    mape,
    markov_order_check,
    poisson_dispersion_test,
    replicated_census,
    temporal_split,
    wasserstein_1d,
)


# ----- Séries observées -----


class TestObservedSeries:
    def test_daily_census_counts_presence(self):
        stays = [
            {"person_id": "1", "service": "ICU", "start": "2023-01-01", "end": "2023-01-03"},
            {"person_id": "2", "service": "ICU", "start": "2023-01-02", "end": "2023-01-02"},
        ]
        series = daily_census(stays)["ICU"]
        assert series[date(2023, 1, 1)] == 1
        assert series[date(2023, 1, 2)] == 2  # les deux présents
        assert series[date(2023, 1, 3)] == 1

    def test_census_sample_is_flat_list(self):
        stays = [{"person_id": "1", "service": "ED", "start": "2023-01-01", "end": "2023-01-04"}]
        sample = census_sample(stays)["ED"]
        assert sample == [1, 1, 1, 1]

    def test_daily_arrivals(self):
        stays = [
            {"person_id": "1", "service": "ED", "start": "2023-01-01", "end": "2023-01-02"},
            {"person_id": "2", "service": "ED", "start": "2023-01-01", "end": "2023-01-02"},
            {"person_id": "3", "service": "ED", "start": "2023-01-03", "end": "2023-01-04"},
        ]
        assert daily_arrivals(stays, "ED") == [2, 0, 1]

    def test_temporal_split(self):
        stays = [
            {"person_id": "1", "service": "ED", "start": "2019-06-01", "end": "2019-06-02"},
            {"person_id": "2", "service": "ED", "start": "2020-06-01", "end": "2020-06-02"},
        ]
        train, test = temporal_split(stays, "2020-01-01")
        assert len(train) == 1 and len(test) == 1


# ----- Métriques -----


class TestPointMetrics:
    def test_mae_bias_mape(self):
        obs = [10, 20, 30]
        pred = [12, 18, 33]
        assert mae(obs, pred) == pytest.approx((2 + 2 + 3) / 3)
        assert bias(obs, pred) == pytest.approx((2 - 2 + 3) / 3)
        assert mape(obs, pred) == pytest.approx(100 * (0.2 + 0.1 + 0.1) / 3)

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            mae([1, 2], [1])


class TestWasserstein:
    def test_identical_is_zero(self):
        assert wasserstein_1d([1, 2, 3], [1, 2, 3]) == pytest.approx(0.0)

    def test_shift_equals_offset(self):
        # décaler tout de +5 => Wasserstein-1 = 5
        assert wasserstein_1d([0, 1, 2, 3], [5, 6, 7, 8]) == pytest.approx(5.0)


class TestCiCoverage:
    def test_same_distribution_near_nominal(self):
        rng = random.Random(0)
        obs = [rng.gauss(0, 1) for _ in range(2000)]
        sim = [rng.gauss(0, 1) for _ in range(2000)]
        cov = ci_coverage(obs, sim)
        assert cov["coverage"] == pytest.approx(0.95, abs=0.03)

    def test_shifted_distribution_low_coverage(self):
        rng = random.Random(0)
        obs = [rng.gauss(10, 1) for _ in range(1000)]
        sim = [rng.gauss(0, 1) for _ in range(1000)]
        assert ci_coverage(obs, sim)["coverage"] < 0.1


class TestPoissonDispersion:
    def test_poisson_not_rejected(self):
        rng = random.Random(1)
        counts = [_poisson(rng, 5.0) for _ in range(400)]
        assert poisson_dispersion_test(counts)["is_poisson"] is True

    def test_overdispersed_rejected(self):
        rng = random.Random(1)
        # mélange -> sur-dispersion
        counts = [_poisson(rng, 1.0) if rng.random() < 0.5 else _poisson(rng, 20.0)
                  for _ in range(400)]
        assert poisson_dispersion_test(counts)["is_poisson"] is False


class TestMarkovOrder:
    def test_order1_data_low_tv(self):
        # Données réellement markoviennes d'ordre 1 : TV moyenne faible.
        rng = random.Random(2)
        trans = {"A": {"B": 0.7, "C": 0.3}, "B": {"A": 0.5, "C": 0.5}, "C": {"A": 1.0}}
        stays = []
        for pid in range(400):
            cur = "A"
            t = 0
            for _ in range(5):
                stays.append({"person_id": pid, "service": cur, "start": f"2023-01-{t+1:02d}",
                              "end": f"2023-01-{t+1:02d}"})
                t += 1
                nxt = rng.choices(list(trans[cur]), weights=list(trans[cur].values()))[0]
                cur = nxt
        result = markov_order_check(stays, min_context=15)
        assert result["mean_tv"] < 0.15


def _poisson(rng, lam):
    import math
    limit = math.exp(-lam)
    k, p = 0, 1.0
    while True:
        k += 1
        p *= rng.random()
        if p <= limit:
            return k - 1


class TestReplicatedCensus:
    def test_shape_matches_services_and_reps(self):
        sc = Scenario(name="c", days=30, warmup_days=5, arrival_rate_per_day=10.0, seed=1)
        bands = replicated_census(sc, 8)
        assert set(bands) == set(sc.service_capacities)
        # 30 - 5 jours d'analyse, 8 réplications par jour
        for svc, days in bands.items():
            assert len(days) == 25
            assert all(len(reps) == 8 for reps in days)
