'use client';

/**
 * The three non-ready states, drawn once so both routes agree on them.
 *
 * §6.2 requires the `stale` one by name: "a document from a newer generator than
 * the deployed page renders a plain 'data is newer than this page' state rather
 * than throwing". The other two are here because a page with one fetch and no
 * fallback has nothing else to show when the fetch does not land.
 */

import { CfbDocumentState } from './useCfbDocument';

export function DocumentPlaceholder({
  state,
  what,
}: {
  state: Exclude<CfbDocumentState<never>, { status: 'ready' }>;
  what: string;
}) {
  if (state.status === 'loading') {
    return (
      <div className="flex items-center gap-3 text-base-content/60">
        <span className="loading loading-spinner loading-sm" aria-hidden />
        <span>Loading {what}…</span>
      </div>
    );
  }

  if (state.status === 'stale') {
    return (
      <div role="status" className="alert alert-warning max-w-2xl">
        <div>
          <h2 className="font-semibold">This data is newer than this page</h2>
          <p className="text-sm opacity-90">
            The pipeline published version {state.found} and this page understands version{' '}
            {state.supported}. The site and the data deploy separately, so this usually clears
            itself within a few minutes. Nothing is wrong with the numbers — this page just
            cannot promise it would read them correctly.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div role="alert" className="alert alert-error max-w-2xl">
      <div>
        <h2 className="font-semibold">Could not load {what}</h2>
        <p className="text-sm opacity-90 font-mono">{state.message}</p>
      </div>
    </div>
  );
}
