"use client";

import Graph from "graphology";
import { LoaderCircle, Network, RefreshCw, Search } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { getGraph, type GraphData, type GraphNode } from "@/lib/api";

function graphPosition(index: number, count: number) {
  const ring = Math.floor(index / 36);
  const position = index % 36;
  const radius = 1 + ring * 0.72;
  const angle = (position / Math.min(count, 36)) * Math.PI * 2 + ring * 0.43;
  return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
}

export default function GraphPage() {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const [graphData, setGraphData] = useState<GraphData | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState("all");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = useCallback(async (nextScope = "all") => {
    setLoading(true);
    setError("");
    try {
      const result = await getGraph(nextScope, 2000);
      setGraphData(result);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to load the knowledge graph.");
      setGraphData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh("all");
  }, [refresh]);

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
          size: node.type === "note" ? (node.pinned ? 8 : 5) : 3,
          color: node.type === "note" ? "#28775a" : "#d58b37",
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
        defaultNodeColor: "#28775a",
        defaultEdgeColor: "#c7d4cc",
      });
      killRenderer = () => renderer.kill();
      const nodeById = new Map(graphData.nodes.map((node) => [node.id, node]));
      renderer.on("clickNode", ({ node }) => setSelectedNode(nodeById.get(node) ?? null));
      renderer.on("clickStage", () => setSelectedNode(null));
    });
    return () => {
      active = false;
      killRenderer?.();
    };
  }, [graphData]);

  function submitSearch(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextScope = query.trim() ? `search:${query.trim()}` : "all";
    setScope(nextScope);
    void refresh(nextScope);
  }

  return (
    <div className="page-wrap graph-page">
      <section className="page-heading-row graph-heading">
        <div><p className="eyebrow">KB VIEWER · FAMILY KNOWLEDGE</p><h1>Knowledge graph</h1><p className="page-subtitle">Explore how notes connect through tags, hierarchy, and explicit links.</p></div>
        <button className="icon-button" onClick={() => void refresh(scope)} aria-label="Refresh graph"><RefreshCw size={17} /></button>
      </section>
      <div className="graph-toolbar">
        <form className="search-field graph-search" onSubmit={submitSearch}><Search size={17} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Find connected notes" aria-label="Search graph" /><button type="submit" className="text-button">Explore</button></form>
        {graphData && <span className="graph-count">{graphData.meta.node_count} nodes · {graphData.meta.edge_count} connections{graphData.meta.truncated ? " · showing first 2,000 notes" : ""}</span>}
      </div>
      <div className="graph-workspace">
        <div className="graph-canvas" ref={containerRef} aria-label="Interactive family knowledge graph">
          {loading && <div className="graph-state"><LoaderCircle className="spin" size={20} /><span>Loading graph</span></div>}
          {error && <div className="graph-state graph-error" role="alert"><strong>Graph unavailable</strong><span>{error}</span><button className="text-button" onClick={() => void refresh(scope)}>Retry</button></div>}
          {!loading && !error && graphData?.nodes.length === 0 && <div className="graph-state"><Network size={22} /><strong>No connected notes yet</strong><span>Add notes and tags to grow this graph.</span></div>}
        </div>
        <aside className="graph-inspector" aria-live="polite">
          {selectedNode ? <>
            <p className="eyebrow">{selectedNode.type}</p><h2>{selectedNode.label}</h2>
            {selectedNode.note_type && <p>{selectedNode.note_type.replaceAll("_", " ")}{selectedNode.pinned ? " · pinned" : ""}</p>}
            {selectedNode.tags.length > 0 && <div className="graph-tag-list">{selectedNode.tags.map((tag) => <span className="tag-chip" key={tag}>#{tag}</span>)}</div>}
          </> : <><p className="eyebrow">NODE INSPECTOR</p><h2>Select a node</h2><p>Note and tag connections appear here.</p></>}
        </aside>
      </div>
    </div>
  );
}