import type { StreamingLinks } from './posts';

/** "Sep 25, 2026". The dates are calendar days, so formatted as UTC. */
export function formatDate(iso: string): string {
  return new Date(`${iso}T00:00:00Z`).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

/** RFC 822, as RSS wants it. Noon UTC, so no time zone moves it a day. */
export function rfc822(iso: string): string {
  return new Date(`${iso}T12:00:00Z`).toUTCString();
}

export const LINK_LABELS: Record<keyof StreamingLinks, string> = {
  spotify: 'Spotify',
  apple_music: 'Apple Music',
  bandcamp: 'Bandcamp',
  youtube_music: 'YouTube Music',
};

/** In a fixed order, whatever order the front matter used. */
export function streamingLinks(links: StreamingLinks): { label: string; url: string }[] {
  return (Object.keys(LINK_LABELS) as (keyof StreamingLinks)[])
    .filter((k) => links[k])
    .map((k) => ({ label: LINK_LABELS[k], url: links[k]! }));
}
