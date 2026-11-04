import { Link } from 'react-router-dom';

export function NotFoundPage() {
  return (
    <div className="mx-auto max-w-lg py-16 text-center">
      <p className="num text-5xl font-semibold text-muted">404</p>
      <h1 className="mt-3 text-2xl">Page not found</h1>
      <p className="mt-2 text-ink-2">There is nothing at this address. It may have moved, or the link may be mistyped.</p>
      <Link to="/" className="btn-primary mt-6">
        Go to the dashboard
      </Link>
    </div>
  );
}
