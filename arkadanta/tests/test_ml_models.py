"""Validasi migrasi GMM/HGB pada data sintetis eksplisit dan penyimpanan sementara."""
from contextlib import ExitStack
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import joblib
import numpy as np
import pandas as pd
from pydantic import ValidationError
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.mixture import GaussianMixture
from threadpoolctl import threadpool_limits

from backend.analytics.anomaly_detector import detect_anomalies
from backend.analytics.feature_engineering import compute_dynamic_features
from backend.analytics.timeframe_aggregator import aggregate_timeframe
from backend.ml import model_predictor, model_trainer
from backend.schemas import DynamicConfig, PredictRequest
from data import storage
from data.sample_generator import generate_synthetic_5m_ohlcv
from spark_jobs.train_models import MAX_DRIVER_ROWS, collect_model_features


class ModelMigrationTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.models = self.root / 'models'
        self.models.mkdir()
        self.drop = self.root / 'drop'
        self.drop.mkdir()
        self.stack.enter_context(patch.object(storage, 'DROP_ZONE_DIR', self.drop))
        self.stack.enter_context(patch.object(storage, 'NIFI_OUTBOX_DIR', self.root / 'nifi_outbox'))
        self.stack.enter_context(patch.object(model_trainer, 'MODELS_DIR', self.models))
        self.raw = generate_synthetic_5m_ohlcv(n_candles=600)
        self.raw.to_csv(self.drop / 'BTCUSDT_5m_clean.csv', index=False)
        self.config = DynamicConfig(timeframe='5m', gb_max_iter=20, gb_max_depth=3,
                                    ma_period=7, rsi_period=9, rolling_window=11)

    def test_train_save_reload_and_predict_with_new_algorithms(self):
        legacy = self.models / 'model_BTCUSDT_5m.joblib'
        legacy.write_bytes(b'legacy artifact must not be read or replaced')
        metrics = model_trainer.train_dynamic_models(self.config)
        bundle = joblib.load(model_trainer.bundle_path('BTCUSDT', '5m'))
        self.assertIsInstance(bundle['labeler'].gmm, GaussianMixture)
        self.assertEqual(bundle['labeler'].gmm.init_params, 'random_from_data')
        self.assertIsInstance(bundle['classifier'], HistGradientBoostingClassifier)
        self.assertIsInstance(bundle['regressor'], HistGradientBoostingRegressor)
        self.assertFalse(bundle['classifier'].early_stopping)
        self.assertEqual(legacy.read_bytes(), b'legacy artifact must not be read or replaced')
        self.assertEqual(metrics['model_version'], model_trainer.MODEL_VERSION)
        self.assertTrue(metrics['gmm_metrics']['converged'])
        self.assertTrue(np.isfinite(metrics['gmm_metrics']['bic']))
        self.assertTrue(np.isfinite(metrics['gmm_metrics']['aic']))
        scores = [record['composite_risk_score'] for record in metrics['gmm_metrics']['centroids']]
        self.assertEqual(scores, sorted(scores))
        self.assertEqual(metrics['feature_importance_method'], 'permutation_f1_macro_holdout')
        self.assertEqual({item['feature'] for item in metrics['feature_importances']}, set(metrics['features']))
        split = metrics['temporal_split']
        self.assertLess(pd.Timestamp(split['train_target_end']), pd.Timestamp(split['test_start']))
        self.assertLess(pd.Timestamp(split['labeler_fit_end']), pd.Timestamp(split['test_start']))
        with patch.object(model_predictor, 'compute_dynamic_features', wraps=compute_dynamic_features) as compute:
            result = model_predictor.predict_next_period(PredictRequest(timeframe='5m'))
        self.assertEqual(compute.call_args.kwargs['ma_period'], 7)
        self.assertEqual(compute.call_args.kwargs['rsi_period'], 9)
        self.assertEqual(compute.call_args.kwargs['rolling_window'], 11)
        self.assertAlmostEqual(sum(result['probabilities_t_plus_1'].values()), 1, places=3)
        self.assertIn(result['predicted_regime_t_plus_1'], {'SAFE', 'WARNING', 'DANGER'})
        self.assertIn('current_component_id', result)
        self.assertGreaterEqual(result['predicted_volatility_pct'], 0)
        self.assertEqual(model_predictor.get_latest_metrics('BTCUSDT', '5m')['model_version'], model_trainer.MODEL_VERSION)

    def test_future_holdout_changes_do_not_change_fitted_models(self):
        config = self.config.model_copy(update={'target_horizon': 3})
        features = compute_dynamic_features(aggregate_timeframe(self.raw, '5m'), ma_period=7, rsi_period=9, rolling_window=11)
        baseline = model_trainer.train_from_features(features, config, 'test')
        old = joblib.load(model_trainer.bundle_path('BTCUSDT', '5m'))
        boundary = int((len(features) - 3) * config.train_ratio)
        changed = features.copy()
        changed.loc[boundary:, 'max_volatility'] *= 100
        changed.loc[boundary:, 'volume_zscore'] += 100
        current = model_trainer.train_from_features(changed, config, 'test')
        new = joblib.load(model_trainer.bundle_path('BTCUSDT', '5m'))
        np.testing.assert_allclose(old['labeler'].gmm.means_, new['labeler'].gmm.means_)
        np.testing.assert_allclose(old['labeler'].scaler.mean_, new['labeler'].scaler.mean_)
        probe = features[baseline['features']].iloc[:10].to_numpy()
        with threadpool_limits(limits=2):
            # Model yang dievaluasi tidak boleh melihat holdout; model deploy memang dilatih ulang pada semua data.
            np.testing.assert_allclose(old['holdout_classifier'].predict_proba(probe), new['holdout_classifier'].predict_proba(probe))
        self.assertEqual(baseline['classification_metrics'].keys(), current['classification_metrics'].keys())
        self.assertEqual(current['temporal_split']['embargo_samples'], 3)
        with self.assertRaisesRegex(storage.ResearchDataError, 'horizon'):
            model_predictor.predict_next_period(PredictRequest(timeframe='5m', target_horizon=1))

    def test_legacy_configuration_is_rejected_instead_of_silently_ignored(self):
        with self.assertRaises(ValidationError):
            DynamicConfig(rf_num_trees=100)
        with self.assertRaises(ValidationError):
            DynamicConfig(anomaly_method='kmeans')

    def test_gmm_anomalies_use_finite_density_scores(self):
        features = compute_dynamic_features(aggregate_timeframe(self.raw, '5m'))
        with threadpool_limits(limits=2):
            result, summary = detect_anomalies(features, method='gmm')
        self.assertEqual(summary['method'], 'gmm')
        self.assertTrue(np.isfinite(result['anomaly_score']).all())

    def test_spark_failure_does_not_silently_train_another_engine(self):
        with patch('spark_jobs.batch_analytics.run_batch_job', side_effect=RuntimeError('Spark unavailable')):
            with self.assertRaisesRegex(RuntimeError, 'Spark unavailable'):
                model_trainer.train_dynamic_models(self.config.model_copy(update={'use_spark': True}))
        self.assertFalse(model_trainer.bundle_path('BTCUSDT', '5m').exists())

    def test_driver_memory_guard_prevents_unbounded_training(self):
        class TooManyRows:
            def __len__(self):
                return MAX_DRIVER_ROWS + 1
        frame = Mock()
        frame.columns = []
        frame.limit.return_value.toPandas.return_value = TooManyRows()
        with self.assertRaisesRegex(ValueError, 'dibatasi'):
            collect_model_features(frame)
        frame.limit.assert_called_once_with(MAX_DRIVER_ROWS + 1)

    def test_spark_trained_model_is_served_without_starting_spark(self):
        config = self.config.model_copy(update={'use_spark': True})
        features = compute_dynamic_features(aggregate_timeframe(self.raw, '5m'), ma_period=7, rsi_period=9, rolling_window=11)
        with patch('spark_jobs.batch_analytics.prepare_spark_features', return_value=features) as prepare:
            result = model_trainer.train_dynamic_models(config)
            prediction = model_predictor.predict_next_period(PredictRequest(timeframe='5m'))
        self.assertEqual(prepare.call_count, 1)
        self.assertIn('driver', result['execution_engine'])
        self.assertIn('current_component_id', prediction)


if __name__ == '__main__':
    unittest.main()
