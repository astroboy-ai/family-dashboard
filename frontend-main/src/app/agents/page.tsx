"use client";

import {
  Check,
  Copy,
  KeyRound,
  LoaderCircle,
  Plus,
  ShieldAlert,
  Trash2,
  TriangleAlert,
} from "lucide-react";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import {
  createAgentToken,
  getActor,
  getAgentTokenScopes,
  listAgentTokens,
  revokeAgentToken,
  type Actor,
  type AgentToken,
  type AgentTokenCreated,
} from "@/lib/api";

/** Expiry choices, in days. `null` means the token never expires. */
const EXPIRY_OPTIONS: { label: string; days: number | null }[] = [
  { label: "30 days", days: 30 },
  { label: "90 days", days: 90 },
  { label: "1 year", days: 365 },
  { label: "Never expires", days: null },
];

function formatMoment(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function statusOf(token: AgentToken): { label: string; tone: string } {
  if (token.revoked_at) return { label: "Revoked", tone: "danger" };
  if (token.is_expired) return { label: "Expired", tone: "warn" };
  return { label: "Active", tone: "ok" };
}

/**
 * Endpoint guidance.
 *
 * The rule is not a preference — it follows from where the caller runs. An agent
 * in another container on the same Docker network resolves the service name; an
 * agent anywhere else cannot, because that name only exists inside the network.
 */
function EndpointGuide() {
  return (
    <section className="settings-section">
      <h2>Endpoint</h2>
      <p className="section-hint">
        Which URL an agent uses depends on where it runs, not on what it is.
      </p>
      <div className="endpoint-grid">
        <div className="endpoint-card">
          <p className="endpoint-label">Same VM, same Docker network</p>
          <code className="endpoint-url">http://familyos-backend:8000/mcp</code>
          <p className="muted">
            For agents running in a container on this host alongside the backend
            — R2-D2, Rita. Traffic never leaves the machine.
          </p>
        </div>
        <div className="endpoint-card">
          <p className="endpoint-label">Anywhere else</p>
          <code className="endpoint-url">https://familyos-mcp.logeebox.com/mcp</code>
          <p className="muted">
            For agents on another server — Kururu. Goes out through Cloudflare.
          </p>
        </div>
      </div>
      <p className="section-hint">
        Both accept the same tokens. The service name does not resolve outside the
        Docker network, so an external agent must use the public URL.
      </p>
    </section>
  );
}

export default function AgentsPage() {
  const [actor, setActor] = useState<Actor | null>(null);
  const [tokens, setTokens] = useState<AgentToken[]>([]);
  const [scopes, setScopes] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // Create form
  const [label, setLabel] = useState("");
  const [selectedScopes, setSelectedScopes] = useState<string[]>(["notes.read"]);
  const [expiresInDays, setExpiresInDays] = useState<number | null>(365);
  const [creating, setCreating] = useState(false);

  // The minted token, held only until the operator dismisses it.
  const [minted, setMinted] = useState<AgentTokenCreated | null>(null);
  const [copied, setCopied] = useState(false);

  const [revokingId, setRevokingId] = useState<string | null>(null);

  const load = useCallback(async () => {
    const [tokenList, scopeMap] = await Promise.all([
      listAgentTokens(),
      getAgentTokenScopes(),
    ]);
    setTokens(tokenList);
    setScopes(scopeMap);
  }, []);

  useEffect(() => {
    let active = true;
    void (async () => {
      try {
        const current = await getActor();
        if (!active) return;
        setActor(current);
        if (current.role !== "parent") {
          setLoading(false);
          return;
        }
        await load();
      } catch (reason) {
        if (active) {
          setError(reason instanceof Error ? reason.message : "Unable to load agents.");
        }
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [load]);

  function toggleScope(scope: string) {
    setSelectedScopes((current) =>
      current.includes(scope) ? current.filter((s) => s !== scope) : [...current, scope],
    );
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    setCopied(false);

    if (!label.trim()) {
      setError("Give the token a label so you can tell it apart later.");
      return;
    }
    if (selectedScopes.length === 0) {
      setError("Pick at least one scope.");
      return;
    }

    setCreating(true);
    try {
      const created = await createAgentToken({
        label: label.trim(),
        scopes: selectedScopes,
        expires_in_days: expiresInDays,
      });
      setMinted(created);
      setLabel("");
      setSelectedScopes(["notes.read"]);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to create the token.");
    } finally {
      setCreating(false);
    }
  }

  async function copyToken() {
    if (!minted) return;
    try {
      await navigator.clipboard.writeText(minted.token);
      setCopied(true);
    } catch {
      setError("Clipboard blocked by the browser — select the token and copy manually.");
    }
  }

  async function revoke(token: AgentToken) {
    setError("");
    setNotice("");
    setRevokingId(token.id);
    try {
      await revokeAgentToken(token.id);
      setNotice(`Revoked “${token.label}”. It stops working immediately.`);
      if (minted?.id === token.id) setMinted(null);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to revoke the token.");
    } finally {
      setRevokingId(null);
    }
  }

  if (loading) {
    return (
      <main className="page-wrap">
        <div className="settings-block">
          <p className="eyebrow">AGENTS</p>
          <p className="muted">
            <LoaderCircle size={14} className="spin" /> Loading…
          </p>
        </div>
      </main>
    );
  }

  if (actor && actor.role !== "parent") {
    return (
      <main className="page-wrap">
        <div className="settings-block">
          <p className="eyebrow">ACCESS RESTRICTED</p>
          <h1>Parent role required</h1>
          <p className="muted">Only parent accounts can manage agent tokens.</p>
        </div>
      </main>
    );
  }

  return (
    <main className="page-wrap">
      <div className="settings-block">
        <p className="eyebrow">AGENTS</p>
        <h1>Agent Tokens</h1>
        <p className="muted">
          Tokens let an AI agent reach FamilyOS. Each one carries its own scopes
          and can be revoked on its own.
        </p>
      </div>

      {error && <div className="form-error">{error}</div>}
      {notice && <div className="form-success">{notice}</div>}

      {minted && (
        <section className="settings-section token-minted">
          <h2>
            <KeyRound size={16} /> Token created
          </h2>
          <p className="section-warning">
            <ShieldAlert size={14} /> {minted.warning}
          </p>
          <div className="token-value-row">
            <code className="token-value">{minted.token}</code>
            <button type="button" className="secondary-button" onClick={() => void copyToken()}>
              {copied ? <Check size={14} /> : <Copy size={14} />}
              {copied ? "Copied" : "Copy"}
            </button>
          </div>
          <p className="section-hint">
            Label <strong>{minted.label}</strong> · scopes{" "}
            {minted.scopes.join(", ")} ·{" "}
            {minted.expires_at ? `expires ${formatMoment(minted.expires_at)}` : "never expires"}
          </p>
          <div className="settings-actions">
            <button type="button" className="secondary-button" onClick={() => setMinted(null)}>
              Done
            </button>
          </div>
        </section>
      )}

      <form onSubmit={submit} className="settings-form" noValidate>
        <section className="settings-section">
          <h2>New token</h2>

          <label className="field">
            <span>Label</span>
            <input
              type="text"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Kururu (Yorozuya)"
              maxLength={120}
            />
          </label>
          <p className="section-hint">
            Use a name that says who holds it. It appears in the audit log.
          </p>

          <fieldset className="field scope-fieldset">
            <legend>Scopes</legend>
            {Object.entries(scopes).map(([scope, description]) => (
              <label key={scope} className="scope-option">
                <input
                  type="checkbox"
                  checked={selectedScopes.includes(scope)}
                  onChange={() => toggleScope(scope)}
                />
                <span>
                  <code>{scope}</code>
                  <em>{description}</em>
                </span>
              </label>
            ))}
          </fieldset>
          <p className="section-hint">
            <TriangleAlert size={12} /> A token with <code>notes.write</code> can
            create notes and upload files without asking again. The scope is the
            consent.
          </p>

          <label className="field">
            <span>Expires</span>
            <select
              value={expiresInDays === null ? "never" : String(expiresInDays)}
              onChange={(e) =>
                setExpiresInDays(e.target.value === "never" ? null : Number(e.target.value))
              }
            >
              {EXPIRY_OPTIONS.map((option) => (
                <option
                  key={option.label}
                  value={option.days === null ? "never" : String(option.days)}
                >
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <div className="settings-actions">
            <button type="submit" className="primary-button" disabled={creating}>
              {creating ? <LoaderCircle size={14} className="spin" /> : <Plus size={14} />}
              {creating ? "Creating…" : "Create token"}
            </button>
          </div>
        </section>
      </form>

      <EndpointGuide />

      <section className="settings-section">
        <h2>Issued tokens</h2>
        {tokens.length === 0 ? (
          <p className="muted">No tokens yet.</p>
        ) : (
          <div className="token-table-wrap">
            <table className="token-table">
              <thead>
                <tr>
                  <th>Label</th>
                  <th>Scopes</th>
                  <th>Created</th>
                  <th>Last used</th>
                  <th>Expires</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {tokens.map((token) => {
                  const status = statusOf(token);
                  return (
                    <tr key={token.id} className={token.is_active ? "" : "token-inactive"}>
                      <td>{token.label}</td>
                      <td className="token-scopes">
                        {token.scopes.map((scope) => (
                          <span key={scope} className="scope-chip">
                            {scope}
                          </span>
                        ))}
                      </td>
                      <td>{formatMoment(token.created_at)}</td>
                      <td>{formatMoment(token.last_seen_at)}</td>
                      <td>{token.expires_at ? formatMoment(token.expires_at) : "Never"}</td>
                      <td>
                        <span className={`status-pill status-${status.tone}`}>{status.label}</span>
                      </td>
                      <td>
                        {token.is_active ? (
                          <button
                            type="button"
                            className="icon-button danger"
                            title={`Revoke ${token.label}`}
                            disabled={revokingId === token.id}
                            onClick={() => void revoke(token)}
                          >
                            {revokingId === token.id ? (
                              <LoaderCircle size={14} className="spin" />
                            ) : (
                              <Trash2 size={14} />
                            )}
                          </button>
                        ) : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <p className="section-hint">
          The token value is never shown again — only its hash is stored. If one is
          lost, revoke it and create another.
        </p>
      </section>
    </main>
  );
}
