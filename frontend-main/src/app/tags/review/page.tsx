"use client";

import { useEffect, useState, useCallback } from "react";
import { Check, X, ExternalLink, Sparkles, Clock, Tag as TagIcon } from "lucide-react";
import {
  listTagProposals,
  decideTagProposal,
  type TagProposal,
} from "@/lib/api";

export default function TagReviewPage() {
  const [proposals, setProposals] = useState<TagProposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [deciding, setDeciding] = useState<string | null>(null);
  const [filter, setFilter] = useState<"all" | "pending" | "accepted" | "rejected">("pending");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await listTagProposals();
      setProposals(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load proposals");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleDecision(proposalId: string, accepted: boolean) {
    setDeciding(proposalId);
    setError("");
    try {
      await decideTagProposal(proposalId, accepted);
      await load();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to decide");
    } finally {
      setDeciding(null);
    }
  }

  const filtered = proposals.filter((p) => {
    if (filter === "all") return true;
    return p.status === filter;
  });

  const counts = {
    all: proposals.length,
    pending: proposals.filter((p) => p.status === "pending").length,
    accepted: proposals.filter((p) => p.status === "accepted").length,
    rejected: proposals.filter((p) => p.status === "rejected").length,
  };

  return (
    <div className="page-wrap list-page">
      <section className="page-heading-row">
        <div>
          <p className="eyebrow">AI TAGGING</p>
          <h1>Tag Review</h1>
          <p className="page-subtitle">
            Review AI-proposed tags. Accept to apply, reject to dismiss.
          </p>
        </div>
      </section>

      <div className="tag-review-filters">
        {(["pending", "accepted", "rejected", "all"] as const).map((f) => (
          <button
            key={f}
            className={`filter-chip ${filter === f ? "active" : ""}`}
            onClick={() => setFilter(f)}
          >
            {f.charAt(0).toUpperCase() + f.slice(1)}
            <span className="filter-count">{counts[f]}</span>
          </button>
        ))}
      </div>

      {error && <div className="form-error">{error}</div>}

      {loading ? (
        <div className="empty-state">
          <Clock size={32} />
          <p>Loading proposals…</p>
        </div>
      ) : filtered.length === 0 ? (
        <div className="empty-state">
          <TagIcon size={32} />
          <p>
            {filter === "pending"
              ? "No pending proposals. Create a note and the AI will suggest tags."
              : `No ${filter} proposals.`}
          </p>
        </div>
      ) : (
        <section className="list-results">
          <div className="results-meta">{filtered.length} proposals</div>
          <div className="tag-proposal-list">
            {filtered.map((p) => (
              <div key={p.id} className={`tag-proposal-card status-${p.status}`}>
                <div className="proposal-main">
                  <div className="proposal-header">
                    <span className="proposal-slug">#{p.proposed_slug}</span>
                    <span className={`proposal-status status-${p.status}`}>
                      {p.status}
                    </span>
                  </div>
                  <div className="proposal-meta">
                    <span className="proposal-confidence">
                      <Sparkles size={12} />
                      {Math.round(p.confidence * 100)}% confidence
                    </span>
                    <span className="proposal-model">{p.model}</span>
                    <span className="proposal-date">
                      {new Date(p.created_at).toLocaleDateString()}
                    </span>
                  </div>
                  {p.evidence?.reason != null && (
                    <p className="proposal-reason">{String(p.evidence.reason)}</p>
                  )}
                  <a
                    className="proposal-note-link"
                    href={`/notes/${p.note_id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <ExternalLink size={12} />
                    View note
                  </a>
                </div>
                {p.status === "pending" && (
                  <div className="proposal-actions">
                    <button
                      className="btn-accept"
                      disabled={deciding === p.id}
                      onClick={() => handleDecision(p.id, true)}
                    >
                      <Check size={14} />
                      Accept
                    </button>
                    <button
                      className="btn-reject"
                      disabled={deciding === p.id}
                      onClick={() => handleDecision(p.id, false)}
                    >
                      <X size={14} />
                      Reject
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
