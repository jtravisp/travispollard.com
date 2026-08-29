export const metadata = {
  title: 'Texas Football Forecast - Travis Pollard',
  description:
    'An Elo model for college football, with every prediction written before kickoff and scored against the result. Predictions, the full slate, and the accuracy record.',
};

/**
 * The section pins its own daisyUI theme (`longhorns`, defined in globals.css).
 *
 * `data-theme` on this wrapper rather than on `<html>`: the site-wide selector in
 * `HeaderWithTheme` writes the document element, and two writers would fight
 * over it. Scoping here means the football pages are always burnt orange and the
 * rest of the site keeps whatever the visitor chose.
 */
export default function CfbLayout({ children }: { children: React.ReactNode }) {
  return (
    <div data-theme="longhorns" className="min-h-screen bg-base-100 text-base-content">
      {children}
    </div>
  );
}
