/**
 * Response bodies CAPTURED from the real EnergiQ backend (FastAPI, `uvicorn backend.app.main:create_app`)
 * while it served the bundled UCI household sample dataset (2009, hourly): login, jobs, tariffs,
 * recommendations, notifications and admin endpoints.
 *
 * They are NOT hand-written. The only edit is that the JWT in login*.json was replaced by a placeholder.
 * Tests use them so that the UI is exercised against exactly the shapes the server sends.
 * Error fixtures (err_*.json) are `{ status, body }` pairs for the failure responses that were captured.
 * User ids and job ids are whatever the capturing run produced; tests never depend on other values.
 */
import adminAudit from './admin_audit.json';
import adminSystem from './admin_system.json';
import adminUsers from './admin_users.json';
import err401 from './err_401.json';
import err403 from './err_403.json';
import err409Register from './err_409_register.json';
import err422Validation from './err_422_validation.json';
import errLogin from './err_login.json';
import jobsList from './jobs_list.json';
import login from './login.json';
import loginAdmin from './login_admin.json';
import me from './me.json';
import notifications from './notifications.json';
import recommendations from './recommendations.json';
import register from './register.json';
import tariffs from './tariffs.json';
import trainAccepted from './train_accepted.json';

export const fx = {
  adminAudit,
  adminSystem,
  adminUsers,
  err401,
  err403,
  err409Register,
  err422Validation,
  errLogin,
  jobsList,
  login,
  loginAdmin,
  me,
  notifications,
  recommendations,
  register,
  tariffs,
  trainAccepted,
} as const;
