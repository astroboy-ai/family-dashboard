"use client";

import { Eye, EyeOff, Lock, ShieldCheck, X } from "lucide-react";
import { useEffect, useState } from "react";
import { getActor, type Actor } from "@/lib/api";

type PasswordBlock = {
  id: string;
  note_id: string;
  note_title: string | null;
  label: string | null;
  encrypted: boolean;
  masked: boolean;
  created_at: string;
  updated_at: string;
};

type PasswordBlockDetail = PasswordBlock & {
  value: string | null;
};

export default function VaultPage() {
  const [actor, setActor] = useState<Actor | null>(null);
  const [blocks, setBlocks] = useState<PasswordBlock[]>([]);
  const [selected, setSelected] = useState<PasswordBlockDetail | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    getActor()
      .then(setActor)
      .catch(() => setActor(null));
  }, []);

  useEffect(() => {
    if (!actor) return;
    setLoading(true);
    fetch("/api/vault/password-blocks", { credentials: "include" })
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json() as Promise<PasswordBlock[]>;
      })
      .then(setBlocks)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Failed to load vault."))
      .finally(() => setLoading(false));
  }, [actor]);

  async function viewBlock(block: PasswordBlock) {
    setRevealed(false);
    try {
      const res = await fetch(`/api/vault/password-blocks/${block.id}`, { credentials: "include" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const detail = (await res.json()) as PasswordBlockDetail;
      setSelected(detail);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Failed to load block.");
    }
  }

  return (
    <div className="page-wrap">
      <section className="page-heading-row">
        <div>
          <p className="eyebrow">SECURITY</p>
          <h1>Vault</h1>
          <p className="page-subtitle">Password blocks across all notes, encrypted at rest.</p>
        </div>
      </section>

      {error && <div className="inline-state" role="alert">{error}</div>}

      <section className="list-results">
        {loading ? (
          <div className="loading-rows"><i /><i /><i /></div>
        ) : blocks.length === 0 ? (
          <div className="empty-state">
            <span className="empty-mark"><Lock size={24} /></span>
            <strong>No password blocks</strong>
            <p>Add a password block to any note to see it here.</p>
          </div>
        ) : (
          <div className="vault-grid">
            {blocks.map((block) => (
              <button
                key={block.id}
                className="vault-card"
                onClick={() => viewBlock(block)}
              >
                <div className="vault-card-head">
                  <Lock size={16} />
                  <strong>{block.label || block.note_title || "Password"}</strong>
                </div>
                <div className="vault-card-meta">
                  <span>{block.note_title || "Unknown note"}</span>
                  <span className={block.encrypted ? "vault-badge vault-badge-encrypted" : "vault-badge vault-badge-plaintext"}>
                    {block.encrypted ? "Encrypted" : "Plaintext"}
                  </span>
                </div>
              </button>
            ))}
          </div>
        )}
      </section>

      {selected && (
        <div className="text-overlay" role="dialog" aria-modal="true" aria-label="Password detail" onClick={() => setSelected(null)}>
          <div className="text-overlay-card" onClick={(event) => event.stopPropagation()}>
            <div className="text-overlay-head">
              <strong>{selected.label || selected.note_title || "Password"}</strong>
              <div className="inline-actions">
                <button
                  type="button"
                  className="secondary-button"
                  onClick={() => setRevealed((v) => !v)}
                >
                  {revealed ? <EyeOff size={14} /> : <Eye size={14} />}
                  {revealed ? "Hide" : "Reveal"}
                </button>
                <button className="icon-button" onClick={() => setSelected(null)} aria-label="Close">
                  <X size={18} />
                </button>
              </div>
            </div>
            <div className="vault-detail-body">
              <div className="vault-detail-row">
                <span className="vault-detail-label">Note</span>
                <span>{selected.note_title || "Unknown"}</span>
              </div>
              <div className="vault-detail-row">
                <span className="vault-detail-label">Encryption</span>
                <span className={selected.encrypted ? "vault-badge vault-badge-encrypted" : "vault-badge vault-badge-plaintext"}>
                  {selected.encrypted ? "AES-256-GCM" : "Plaintext"}
                </span>
              </div>
              <div className="vault-detail-row">
                <span className="vault-detail-label">Value</span>
                <span className="vault-detail-value">
                  {revealed ? (selected.value || "••••••••") : "••••••••"}
                </span>
              </div>
              <div className="vault-detail-row">
                <span className="vault-detail-label">Created</span>
                <span>{new Date(selected.created_at).toLocaleString()}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
