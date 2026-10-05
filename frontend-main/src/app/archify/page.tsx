"use client";

import Graph from "graphology";
import {
  ChevronDown,
  LoaderCircle,
  Maximize2,
  Plus,
  RefreshCw,
  Save,
  Trash2,
  Waypoints,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  createGraphView,
  deleteGraphView,
  getGraph,
  listGraphViews,
  updateGraphView,
  type GraphData,
  type GraphNode,
  type GraphView,
} from "@/lib/api";

const NODE_COLORS: Record<string, string> = {
  note: "#28775a",
  tag: "#d58b37",
  member: "#376d87",
  media: "#bf583c",
  event: "#7a5ea8",
};

const NODE_SIZES: Record<string, number> = {
  note: 5,
  tag: 3,
  member: 6,
  media: 4,
  event: 4,
};

function graphPosition(index: number, count: number) {
  const ring = Math.floor(index / 36);
  const position = index % 36;
  const radius = 1 + ring * 0.72;
  const angle = (position / Math.min(count, 36)) * Math.PI * 2 + ring * 0.43;
  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
}

export default function ArchifyPage() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const rendererRef = useRef<{ zoomIn: () => void; zoomOut: () => void; reset: () => void } | null>(null);

  const [views, setViews] = useState<GraphView[]>([]);
  const [activeViewId, setActiveViewId] = useState<string | null>(null);
  const [viewsOpen, setViewsOpen] = useState(false);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const [saveOpen, setSaveOpen] = useState(false);
  const [saveName, setSaveName] = useState("");

  const activeView = useMemo(
    () => views.find((view) => view.id === activeViewId) ?? views[0] ?? null,
    [views, activeViewId],
  );

  const loadViews = useCallback(async () => {
    try {
      const result = await listGraphViews();
      setViews(result.items);
      setActiveViewId((current) => current ?? result.items[0]?.id ?? null);
      return result.items;
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load saved graphs.");
      return [];
    }
  }, []);

  const loadGraph = useCallback(async (scope: string) => {
    setLoading(true);
    setError("");
    try {
      const result = await getGraph(scope, 2000);
      setGraphData(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load the graph.");
      setGraphData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void (async () => {
      const items = await loadViews();
      const first = items[0];
      await loadGraph(first?.config.scope ?? "all");
    })();
  }, [loadViews, loadGraph]);

  // Render with sigma whenever the graph data changes.
  useEffect(() => {
    const container = containerRef.current;
    if (!container || !graphData || graphData.nodes.length === 0) return;
    let active = true;
    let killRenderer: (() => void) | null = null;
    void import("sigma").then(({ default: Sigma }) => {
      if (!active || !containerRef.current) return;
      const graph = new Graph({ multi: true, type: "undirected" });
      graphData.nodes.forEach((node, index) => {
        const position = graphPosition(index, graphData.nodes.length);
        graph.addNode(node.id, {
          label: node.label,
          x: position.x,
          y: position.y,
          size: (NODE_SIZES[node.type] ?? 4) + (node.pinned ? 3 : 0),
          color: NODE_COLORS[node.type] ?? "#8a9a90",
          type: "circle",
        });
      });
      graphData.edges.forEach((edge) => {
        if (!graph.hasNode(edge.source) || !graph.hasNode(edge.target) || graph.hasEdge(edge.id)) return;
        graph.addEdgeWithKey(edge.id, edge.source, edge.target, {
          size: edge.type === "relation" ? 1.8 : 0.8,
          color: edge.type === "relation" ? "#55816d" : "#c7d4cc",
          type: "line",
        });
      });

      const renderer = new Sigma(graph, containerRef.current, {
        renderEdgeLabels: false,
        labelColor: { color: "#22362d" },
        labelSize: 12,
        labelFont: "Arial, sans-serif",
        stagePadding: 28,
      });
      rendererRef.current = {
        zoomIn: () => renderer.getCamera().animatedZoom({ duration: 220 }),
        zoomOut: () => renderer.getCamera().animatedUnzoom({ duration: 220 }),
        reset: () => renderer.getCamera().animatedReset({ duration: 220 }),
      };
      killRenderer = () => {
        rendererRef.current = null;
        renderer.kill();
      };
      const nodeById = new Map(graphData.nodes.map((node) => [node.id, node]));
      renderer.on("clickNode", ({ node }) => setSelectedNode(nodeById.get(node) ?? null));
      renderer.on("clickStage", () => setSelectedNode(null));
    });
    return () => {
      active = false;
      killRenderer?.();
    };
  }, [graphData]);

  async function openView(view: GraphView) {
    setActiveViewId(view.id);
    setViewsOpen(false);
    setSelectedNode(null);
    await loadGraph(view.config.scope ?? "all");
  }

  async function handleSave() {
    const name = saveName.trim();
    if (!name) return;
    setBusy(true);
    setError("");
    try {
      const created = await createGraphView({
        name,
        description: `${graphData?.meta.node_count ?? 0} nodes`,
        config: { scope: activeView?.config.scope ?? "all", layout: "force" },
      });
      setViews((current) => [...current, created]);
      setActiveViewId(created.id);
      setSaveOpen(false);
      setSaveName("");
      setStatus(`Saved “${created.name}”.`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to save this graph.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRename(view: GraphView) {
    const next = window.prompt("Rename graph", view.name);
    if (next === null || !next.trim()) return;
    setBusy(true);
    try {
      const updated = await updateGraphView(view.id, { name: next.trim() });
      setViews((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setStatus("Graph renamed.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to rename this graph.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(view: GraphView) {
    if (!window.confirm(`Delete “${view.name}”? This only removes the saved view.`)) return;
    setBusy(true);
    try {
      await deleteGraphView(view.id);
      const remaining = views.filter((item) => item.id !== view.id);
      setViews(remaining);
      if (activeViewId === view.id) setActiveViewId(remaining[0]?.id ?? null);
      setStatus("Graph deleted.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to delete this graph.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="page-wrap graph-page archify-page">
      <section className="page-heading-row graph-heading">
        <div>
          <p className="eyebrow">ARCHIFY · SYSTEM GRAPHS</p>
          <h1>Archify</h1>
          <p className="page-subtitle">
            Browse graphs produced by other systems and agents. Save a view, reopen it, or hand it back to an agent.
          </p>
        </div>
        <div className="inline-actions">
          <button className="secondary-button" onClick={() => void loadGraph(activeView?.config.scope ?? "all")} disabled={loading}>
            <RefreshCw className={loading ? "spin" : undefined} size={16} /> Refresh
          </button>
          <button className="secondary-button" onClick={() => setSaveOpen((value) => !value)} disabled={busy}>
            <Save size={16} /> Save view
          </button>
        </div>
      </section>

      <div className="graph-toolbar archify-toolbar">
        <div className="archify-view-picker">
          <button
            className="view-picker-trigger"
            onClick={() => setViewsOpen((value) => !value)}
            aria-expanded={viewsOpen}
            aria-haspopup="listbox"
          >
            <Waypoints size={16} />
            <span>{activeView?.name ?? "No saved graphs"}</span>
            <ChevronDown size={15} />
          </button>
          {viewsOpen && (
            <div className="view-picker-menu" role="listbox">
              {views.length === 0 && <p className="view-picker-empty">No saved graphs yet.</p>}
              {views.map((view) => (
                <div
                  key={view.id}
                  className={`view-picker-row${view.id === activeView?.id ? " selected" : ""}`}
                >
                  <button className="view-picker-open" onClick={() => void openView(view)} role="option" aria-selected={view.id === activeView?.id}>
                    <strong>{view.name}</strong>
                    <small>{view.kind} · {view.config.scope ?? "all"}</small>
                  </button>
                  <button className="icon-button" onClick={() => void handleRename(view)} aria-label={`Rename ${view.name}`}>✎</button>
                  <button className="icon-button" onClick={() => void handleDelete(view)} aria-label={`Delete ${view.name}`}><Trash2 size={15} /></button>
                </div>
              ))}
            </div>
          )}
        </div>
        {graphData && (
          <span className="graph-count">
            {graphData.meta.node_count} nodes · {graphData.meta.edge_count} connections
            {graphData.meta.truncated ? " · showing first 2,000 notes" : ""}
          </span>
        )}
      </div>

      {saveOpen && (
        <div className="archify-save-row">
          <input
            className="archify-save-input"
            value={saveName}
            onChange={(event) => setSaveName(event.target.value)}
            placeholder="Name this graph view"
            aria-label="Graph view name"
          />
          <button className="primary-button" onClick={() => void handleSave()} disabled={busy || !saveName.trim()}>
            <Plus size={15} /> Save
          </button>
        </div>
      )}

      {status && <p className="archify-status">{status}</p>}

      <div className="graph-workspace">
        <div className="graph-canvas" ref={containerRef} aria-label="Archify system graph canvas">
          {loading && (
            <div className="graph-state">
              <LoaderCircle className="spin" size={20} />
              <span>Loading graph</span>
            </div>
          )}
          {error && (
            <div className="graph-state graph-error" role="alert">
              <strong>Graph unavailable</strong>
              <span>{error}</span>
              <button className="text-button" onClick={() => void loadGraph(activeView?.config.scope ?? "all")}>Retry</button>
            </div>
          )}
          {!loading && !error && graphData?.nodes.length === 0 && (
            <div className="graph-state">
              <Waypoints size={22} />
              <strong>Nothing to display yet</strong>
              <span>Save a graph from an agent or connect notes to populate this canvas.</span>
            </div>
          )}
        </div>

        <aside className="graph-inspector" aria-live="polite">
          {selectedNode ? (
            <>
              <p className="eyebrow">{selectedNode.type}</p>
              <h2>{selectedNode.label}</h2>
              {selectedNode.note_type && (
                <p>{selectedNode.note_type.replaceAll("_", " ")}{selectedNode.pinned ? " · pinned" : ""}</p>
              )}
              {selectedNode.tags.length > 0 && (
                <div className="graph-tag-list">
                  {selectedNode.tags.map((tag) => <span className="tag-chip" key={tag}>#{tag}</span>)}
                </div>
              )}
            </>
          ) : (
            <>
              <p className="eyebrow">NODE INSPECTOR</p>
              <h2>Select a node</h2>
              <p>Node details appear here.</p>
            </>
          )}
          <div className="archify-zoom-row">
            <button className="icon-button" onClick={() => rendererRef.current?.zoomIn()} aria-label="Zoom in"><ZoomIn size={16} /></button>
            <button className="icon-button" onClick={() => rendererRef.current?.zoomOut()} aria-label="Zoom out"><ZoomOut size={16} /></button>
            <button className="icon-button" onClick={() => rendererRef.current?.reset()} aria-label="Reset zoom"><Maximize2 size={16} /></button>
          </div>
        </aside>
      </div>
    </div>
  );
}
