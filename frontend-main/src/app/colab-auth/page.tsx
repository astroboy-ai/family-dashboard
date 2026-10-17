import Link from "next/link";

export const dynamic = "force-dynamic";

/**
 * TEMP page (2026-10): opens the Google OAuth consent URL for the Colab CLI
 * in a real browser. The CLI prints the URL on the host; R2-D2 passes it here
 * as ?url=<encoded>. Delete this page once the flow is no longer needed.
 */
function isAllowedGoogleConsentUrl(value: string): boolean {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" && parsed.hostname === "accounts.google.com";
  } catch {
    return false;
  }
}

export default async function ColabAuthPage({
  searchParams,
}: {
  searchParams: Promise<{ url?: string }>;
}) {
  const { url } = await searchParams;
  const allowed = typeof url === "string" && isAllowedGoogleConsentUrl(url);

  return (
    <div className="page-wrap planned-page">
      <p className="eyebrow">FAMILYOS · TEMP</p>
      <h1>Colab CLI authorization</h1>
      <div className="planned-rule" />

      {allowed ? (
        <>
          <p>1. Open Google&apos;s consent page and approve access for the Colab CLI.</p>
          <p>
            <a className="text-link" href={url} target="_blank" rel="noreferrer noopener">
              Open Google consent page <span aria-hidden="true">→</span>
            </a>
          </p>
          <p>2. Google shows an authorization code. Copy it.</p>
          <p>3. Send the code back to R2-D2 — the CLI is already waiting for it.</p>
        </>
      ) : (
        <p>
          No authorization URL supplied. Ask R2-D2 to start the Colab CLI flow first, then
          reopen this page with the URL it returns.
        </p>
      )}

      <Link className="text-link" href="/">
        Return home <span aria-hidden="true">→</span>
      </Link>
    </div>
  );
}
