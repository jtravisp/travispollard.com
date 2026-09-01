'use client';

/**
 * One fetch, one document, and the four states a page can be in (SPEC-phase1 6.2).
 *
 * The site is a static export (`output: 'export'`), so there is no server to
 * fetch on: every one of these documents is loaded in the browser after the page
 * paints. That is a constraint rather than a preference, and it is why `loading`
 * is a real state the pages have to draw rather than a flash nobody sees.
 *
 * **`stale` is the state §6.2 exists for.** The site and the pipeline deploy
 * independently, so a document written by a newer generator than the deployed
 * page is not a bug -- it is a few minutes on an ordinary Friday. A page that
 * threw on it would turn a routine deploy skew into an error; a page that
 * rendered it anyway would read fields that may have changed meaning. So it
 * refuses, and says which side is ahead.
 */

import { useEffect, useState } from 'react';

import { CFB_DATA_BASE, Envelope, SUPPORTED_SCHEMA_VERSIONS } from './contract';

export type CfbDocumentState<T> =
  | { status: 'loading' }
  | { status: 'ready'; document: T }
  /** The document loaded and this page cannot read its version. */
  | { status: 'stale'; found: number; supported: number[] }
  /** Nothing loaded: no network, a 404, or bytes that are not JSON. */
  | { status: 'error'; message: string };

/**
 * `supported` is per document, not per site.
 *
 * The four documents version independently (SPEC-phase1 6.2, SPEC-phase2 6.2):
 * `models.json` starts at 3 while the other three are on 2, because it is a new
 * document rather than a change to them. A single shared list would either
 * reject `models.json` outright or accept a version 3 `next-game.json` that
 * nothing has ever published -- and the second is worse, because it is the
 * rollback case this check exists to catch.
 */
export function useCfbDocument<T extends Envelope>(
  name: string,
  supported: number[] = SUPPORTED_SCHEMA_VERSIONS,
): CfbDocumentState<T> {
  const [state, setState] = useState<CfbDocumentState<T>>({ status: 'loading' });

  useEffect(() => {
    // Guards against setting state after the component unmounts, which in dev's
    // StrictMode double-effect is otherwise a console warning on every load.
    let live = true;

    fetch(`${CFB_DATA_BASE}/${name}`, { cache: 'no-store' })
      .then(async (response) => {
        if (!response.ok) {
          // The status, not a friendly sentence: a 403 here means the bucket
          // policy or the OAC, and a 404 means the publish never ran. Those are
          // different problems and the page should not blur them.
          throw new Error(`${response.status} ${response.statusText}`);
        }
        return (await response.json()) as T;
      })
      .then((document) => {
        if (!live) return;
        if (!supported.includes(document.schema_version)) {
          setState({
            status: 'stale',
            found: document.schema_version,
            supported,
          });
          return;
        }
        setState({ status: 'ready', document });
      })
      .catch((error: unknown) => {
        if (!live) return;
        setState({
          status: 'error',
          message: error instanceof Error ? error.message : String(error),
        });
      });

    return () => {
      live = false;
    };
  }, [name, supported]);

  return state;
}
