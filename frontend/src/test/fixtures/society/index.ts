/**
 * Response bodies CAPTURED from the real EnergiQ backend serving the imported Fox community (BDG2 data, trained and
 * deployed models) by `scripts/capture_society_fixtures.py`. Not hand-written; regenerate with that script.
 */
import anomalies from './anomalies.json';
import backtest from './backtest.json';
import buildingConsumption from './building_consumption.json';
import buildings from './buildings.json';
import buildingsMonthly from './buildings_monthly.json';
import consumptionDaily from './consumption_daily.json';
import consumptionHourly from './consumption_hourly.json';
import compare from './compare.json';
import cost from './cost.json';
import detailAdmin from './detail_admin.json';
import detailUser from './detail_user.json';
import errorAnalysis from './error_analysis.json';
import explainGlobal from './explain_global.json';
import explainLocal from './explain_local.json';
import facilities from './facilities.json';
import forecast from './forecast.json';
import meters from './meters.json';
import models from './models.json';
import overview from './overview.json';
import peaks from './peaks.json';
import recommendations from './recommendations.json';
import reportCreated from './report_created.json';
import reports from './reports.json';
import societies from './societies.json';
import tariffs from './tariffs.json';

export const sfx = {
  anomalies,
  backtest,
  buildingConsumption,
  buildings,
  buildingsMonthly,
  consumptionDaily,
  consumptionHourly,
  compare,
  cost,
  detailAdmin,
  detailUser,
  errorAnalysis,
  explainGlobal,
  explainLocal,
  facilities,
  forecast,
  meters,
  models,
  overview,
  peaks,
  recommendations,
  reportCreated,
  reports,
  societies,
  tariffs,
};
