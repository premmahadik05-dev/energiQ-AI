/**
 * Response bodies CAPTURED from the real EnergiQ backend (FastAPI, `uvicorn backend.app.main:create_app`)
 * while it served the bundled UCI household sample dataset (2009, hourly): login, upload/train/anomaly jobs,
 * forecast, explain, optimise, notifications, admin and benchmark endpoints.
 *
 * They are NOT hand-written. The only edit is that the JWT in login*.json was replaced by a placeholder.
 * Tests use them so that the UI is exercised against exactly the shapes the server sends.
 * Error fixtures (err_*.json) are `{ status, body }` pairs for the failure responses that were captured.
 * Dataset id 1, model id and user ids are whatever the capturing run produced; tests never depend on other values.
 */
import adminAudit from './admin_audit.json';
import adminSystem from './admin_system.json';
import adminUsers from './admin_users.json';
import anomaliesList from './anomalies_list.json';
import anomalyAck from './anomaly_ack.json';
import anomalyJobAccepted from './anomaly_job_accepted.json';
import anomalyJobDone from './anomaly_job_done.json';
import anomalySummary from './anomaly_summary.json';
import benchmark from './benchmark.json';
import cost from './cost.json';
import datasetDetail from './dataset_detail.json';
import datasetsList from './datasets_list.json';
import err401 from './err_401.json';
import err403 from './err_403.json';
import err404 from './err_404.json';
import err409Register from './err_409_register.json';
import err422DetailStr from './err_422_detail_str.json';
import err422Validation from './err_422_validation.json';
import errForecastOrigin from './err_forecast_origin.json';
import errLogin from './err_login.json';
import errSchedule422 from './err_schedule_422.json';
import explainGlobal from './explain_global.json';
import explainLocal from './explain_local.json';
import forecastCreated from './forecast_created.json';
import forecastCreatedOrigin from './forecast_created_origin.json';
import forecastsList from './forecasts_list.json';
import jobIngestDone from './job_ingest_done.json';
import jobTrainDone from './job_train_done.json';
import jobsList from './jobs_list.json';
import login from './login.json';
import loginAdmin from './login_admin.json';
import me from './me.json';
import modelsList from './models_list.json';
import monitoringAfterForecast from './monitoring_after_forecast.json';
import monitoringBeforeForecast from './monitoring_before_forecast.json';
import notifications from './notifications.json';
import profile from './profile.json';
import readingsDaily from './readings_daily.json';
import readingsHourlyDefault from './readings_hourly_default.json';
import recommendations from './recommendations.json';
import register from './register.json';
import sampleAccepted from './sample_accepted.json';
import schedule from './schedule.json';
import tariffs from './tariffs.json';
import trainAccepted from './train_accepted.json';

export const fx = {
  adminAudit,
  adminSystem,
  adminUsers,
  anomaliesList,
  anomalyAck,
  anomalyJobAccepted,
  anomalyJobDone,
  anomalySummary,
  benchmark,
  cost,
  datasetDetail,
  datasetsList,
  err401,
  err403,
  err404,
  err409Register,
  err422DetailStr,
  err422Validation,
  errForecastOrigin,
  errLogin,
  errSchedule422,
  explainGlobal,
  explainLocal,
  forecastCreated,
  forecastCreatedOrigin,
  forecastsList,
  jobIngestDone,
  jobTrainDone,
  jobsList,
  login,
  loginAdmin,
  me,
  modelsList,
  monitoringAfterForecast,
  monitoringBeforeForecast,
  notifications,
  profile,
  readingsDaily,
  readingsHourlyDefault,
  recommendations,
  register,
  sampleAccepted,
  schedule,
  tariffs,
  trainAccepted,
} as const;
