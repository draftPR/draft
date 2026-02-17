import { useEffect, useState, useMemo } from "react";
import { config } from "@/config";
import { Badge } from "@/components/ui/badge";
import { Loader2, GitBranch, AlertCircle, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface Ticket {
  id: string;
  title: string;
  state: string;
  priority: number | null;
  blocked_by_ticket_id: string | null;
}

interface TicketNode extends Ticket {
  layer: number;
  x: number;
  y: number;
  dependents: string[]; // Tickets that depend on this one
}

interface DAGEdge {
  from: string;
  to: string;
  fromNode: TicketNode;
  toNode: TicketNode;
}

// Airflow-inspired color scheme
const STATE_COLORS: Record<string, { fill: string; stroke: string; text: string }> = {
  proposed: { fill: "#64748b", stroke: "#475569", text: "#f1f5f9" },
  planned: { fill: "#3b82f6", stroke: "#2563eb", text: "#eff6ff" },
  executing: { fill: "#10b981", stroke: "#059669", text: "#ecfdf5" },
  verifying: { fill: "#8b5cf6", stroke: "#7c3aed", text: "#f5f3ff" },
  needs_human: { fill: "#f59e0b", stroke: "#d97706", text: "#fffbeb" },
  blocked: { fill: "#ef4444", stroke: "#dc2626", text: "#fef2f2" },
  done: { fill: "#22c55e", stroke: "#16a34a", text: "#f0fdf4" },
  abandoned: { fill: "#9ca3af", stroke: "#6b7280", text: "#f9fafb" },
};

interface TicketDAGViewProps {
  highlightedTicketId?: string | null;
}

export function TicketDAGView({ highlightedTicketId: propHighlightedTicketId }: TicketDAGViewProps = {}) {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hoveredNode, setHoveredNode] = useState<string | null>(null);
  const [highlightedTicketId, setHighlightedTicketId] = useState<string | null>(null);

  // Read highlight param from URL or prop
  useEffect(() => {
    if (propHighlightedTicketId) {
      setHighlightedTicketId(propHighlightedTicketId);
    } else {
      const params = new URLSearchParams(window.location.search);
      const highlightId = params.get('highlight');
      setHighlightedTicketId(highlightId);
    }
  }, [propHighlightedTicketId]);

  // Keyboard shortcut: Escape to clear highlight
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && highlightedTicketId) {
        setHighlightedTicketId(null);
        window.history.replaceState({}, '', window.location.pathname);
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [highlightedTicketId]);

  // Fetch tickets
  useEffect(() => {
    const fetchTickets = async () => {
      try {
        const response = await fetch(`${config.backendBaseUrl}/board`);
        if (!response.ok) throw new Error("Failed to fetch tickets");
        const data = await response.json();
        // Flatten tickets from board columns
        const allTickets: Ticket[] = data.columns.flatMap((col: { tickets: Ticket[] }) => col.tickets);
        setTickets(allTickets);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      } finally {
        setLoading(false);
      }
    };

    fetchTickets();

    // Poll every 3 seconds
    const interval = setInterval(fetchTickets, 3000);
    return () => clearInterval(interval);
  }, []);

  // Compute DAG layout
  const { nodes, edges, stats } = useMemo(() => {
    if (tickets.length === 0) {
      return { nodes: [], edges: [], stats: { totalTickets: 0, hasCycle: false, maxLayer: 0 } };
    }

    // Build dependency map
    const ticketMap = new Map<string, TicketNode>();
    const dependentsMap = new Map<string, string[]>();

    tickets.forEach((ticket) => {
      ticketMap.set(ticket.id, { ...ticket, layer: -1, x: 0, y: 0, dependents: [] });
      dependentsMap.set(ticket.id, []);
    });

    // Build dependents list (reverse of blocked_by)
    tickets.forEach((ticket) => {
      if (ticket.blocked_by_ticket_id) {
        const dependents = dependentsMap.get(ticket.blocked_by_ticket_id);
        if (dependents) {
          dependents.push(ticket.id);
        }
      }
    });

    // Assign dependents
    dependentsMap.forEach((dependents, ticketId) => {
      const node = ticketMap.get(ticketId);
      if (node) {
        node.dependents = dependents;
      }
    });

    // Topological sort to assign layers (detect cycles too)
    const visited = new Set<string>();
    const visiting = new Set<string>();
    let hasCycle = false;

    const assignLayer = (ticketId: string): number => {
      if (visiting.has(ticketId)) {
        hasCycle = true;
        return 0; // Cycle detected
      }
      if (visited.has(ticketId)) {
        return ticketMap.get(ticketId)?.layer ?? 0;
      }

      visiting.add(ticketId);
      const node = ticketMap.get(ticketId);
      if (!node) return 0;

      // Layer = 1 + max(blocker layers)
      let layer = 0;
      if (node.blocked_by_ticket_id) {
        const blockerLayer = assignLayer(node.blocked_by_ticket_id);
        layer = blockerLayer + 1;
      }

      node.layer = layer;
      visiting.delete(ticketId);
      visited.add(ticketId);
      return layer;
    };

    // Assign layers to all tickets
    tickets.forEach((ticket) => assignLayer(ticket.id));

    // Group tickets by layer
    const layerMap = new Map<number, TicketNode[]>();
    let maxLayer = 0;

    ticketMap.forEach((node) => {
      maxLayer = Math.max(maxLayer, node.layer);
      if (!layerMap.has(node.layer)) {
        layerMap.set(node.layer, []);
      }
      layerMap.get(node.layer)?.push(node);
    });

    // Sort within layers by priority (desc) then title
    layerMap.forEach((layer) => {
      layer.sort((a, b) => {
        if (a.priority !== null && b.priority !== null) {
          return b.priority - a.priority;
        }
        if (a.priority !== null) return -1;
        if (b.priority !== null) return 1;
        return a.title.localeCompare(b.title);
      });
    });

    // Layout constants
    const NODE_HEIGHT = 80;
    const LAYER_SPACING = 240;
    const NODE_SPACING = 100;

    // Compute positions
    const nodes: TicketNode[] = [];
    for (let layer = 0; layer <= maxLayer; layer++) {
      const layerNodes = layerMap.get(layer) || [];
      layerNodes.forEach((node, index) => {
        node.x = layer * LAYER_SPACING + 50;
        node.y = index * (NODE_HEIGHT + NODE_SPACING) + 50;
        nodes.push(node);
      });
    }

    // Build edges
    const edges: DAGEdge[] = [];
    nodes.forEach((node) => {
      if (node.blocked_by_ticket_id) {
        const blocker = ticketMap.get(node.blocked_by_ticket_id);
        if (blocker) {
          edges.push({
            from: blocker.id,
            to: node.id,
            fromNode: blocker,
            toNode: node,
          });
        }
      }
    });

    return {
      nodes,
      edges,
      stats: {
        totalTickets: tickets.length,
        hasCycle,
        maxLayer,
      },
      ticketMap,
    };
  }, [tickets]);

  // Compute connected nodes for highlighting
  const connectedNodes = useMemo(() => {
    if (!highlightedTicketId) return null;

    const connected = new Set<string>();
    connected.add(highlightedTicketId);

    // Add all upstream blockers (recursive)
    const addUpstream = (ticketId: string) => {
      const ticket = tickets.find(t => t.id === ticketId);
      if (ticket?.blocked_by_ticket_id && !connected.has(ticket.blocked_by_ticket_id)) {
        connected.add(ticket.blocked_by_ticket_id);
        addUpstream(ticket.blocked_by_ticket_id);
      }
    };

    // Add all downstream dependents (recursive)
    const addDownstream = (ticketId: string) => {
      tickets.forEach(ticket => {
        if (ticket.blocked_by_ticket_id === ticketId && !connected.has(ticket.id)) {
          connected.add(ticket.id);
          addDownstream(ticket.id);
        }
      });
    };

    addUpstream(highlightedTicketId);
    addDownstream(highlightedTicketId);

    return connected;
  }, [highlightedTicketId, tickets]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-destructive">
        <AlertCircle className="h-8 w-8 mb-2" />
        <p className="text-sm">Failed to load DAG</p>
        <p className="text-xs text-muted-foreground">{error}</p>
      </div>
    );
  }

  if (nodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
        <GitBranch className="h-12 w-12 mb-3 opacity-50" />
        <p className="text-sm font-medium">No tickets to visualize</p>
        <p className="text-xs">Create some tickets with dependencies to see the DAG</p>
      </div>
    );
  }

  // Calculate SVG dimensions
  const maxX = Math.max(...nodes.map((n) => n.x)) + 250;
  const maxY = Math.max(...nodes.map((n) => n.y)) + 100;

  return (
    <div className="h-full overflow-auto bg-slate-50 dark:bg-slate-950">
      {/* Stats header */}
      <div className="sticky top-0 z-10 bg-background/95 backdrop-blur border-b px-4 py-2 flex items-center gap-4">
        <div className="flex items-center gap-2">
          <GitBranch className="h-4 w-4 text-blue-500" />
          <span className="text-sm font-semibold">Ticket Dependency Graph</span>
        </div>
        <div className="flex items-center gap-4 text-xs text-muted-foreground">
          <span>Tickets: {stats.totalTickets}</span>
          <span>Layers: {stats.maxLayer + 1}</span>
          <span>Dependencies: {edges.length}</span>
          {connectedNodes && (
            <div className="flex items-center gap-2">
              <Badge variant="default" className="text-[10px] bg-amber-500 hover:bg-amber-600">
                🎯 Highlighting {connectedNodes.size} connected ticket{connectedNodes.size !== 1 ? "s" : ""}
              </Badge>
              <button
                onClick={() => {
                  setHighlightedTicketId(null);
                  window.history.replaceState({}, '', window.location.pathname);
                }}
                className="p-1 rounded hover:bg-muted transition-colors"
                title="Clear highlight"
                aria-label="Clear ticket highlight and show all tickets"
              >
                <X className="h-3 w-3 text-muted-foreground hover:text-foreground" />
              </button>
            </div>
          )}
          {stats.hasCycle && (
            <Badge variant="destructive" className="text-[10px]">
              ⚠️ Cycle Detected!
            </Badge>
          )}
        </div>
        <div className="ml-auto flex items-center gap-2 text-xs">
          <Info className="h-3 w-3 text-muted-foreground" />
          <span className="text-muted-foreground">
            Hover over nodes for details{highlightedTicketId && " • Press ESC to clear highlight"}
          </span>
        </div>
      </div>

      {/* DAG visualization */}
      <div className="p-8">
        <svg
          width={maxX}
          height={maxY}
          className="rounded-lg bg-white dark:bg-slate-900 shadow-sm"
          style={{ minWidth: '100%', minHeight: '500px' }}
        >
          {/* Grid pattern background */}
          <defs>
            <pattern
              id="grid"
              width="20"
              height="20"
              patternUnits="userSpaceOnUse"
            >
              <path
                d="M 20 0 L 0 0 0 20"
                fill="none"
                stroke="currentColor"
                strokeWidth="0.5"
                className="text-slate-200 dark:text-slate-800"
              />
            </pattern>

            {/* Arrow marker for dependencies */}
            <marker
              id="arrowhead"
              markerWidth="10"
              markerHeight="10"
              refX="9"
              refY="3"
              orient="auto"
            >
              <polygon
                points="0 0, 10 3, 0 6"
                fill="#94a3b8"
                className="dark:fill-slate-600"
              />
            </marker>

            {/* Glow filter for executing state */}
            <filter id="glow">
              <feGaussianBlur stdDeviation="3" result="coloredBlur"/>
              <feMerge>
                <feMergeNode in="coloredBlur"/>
                <feMergeNode in="SourceGraphic"/>
              </feMerge>
            </filter>
          </defs>

          <rect width="100%" height="100%" fill="url(#grid)" />

          {/* Render edges */}
          {edges.map((edge, i) => {
            const fromX = edge.fromNode.x + 180;
            const fromY = edge.fromNode.y + 35;
            const toX = edge.toNode.x - 10;
            const toY = edge.toNode.y + 35;

            const isHighlighted = hoveredNode === edge.fromNode.id || hoveredNode === edge.toNode.id;
            const isConnectedToHighlight = connectedNodes?.has(edge.fromNode.id) && connectedNodes?.has(edge.toNode.id);
            const shouldDimEdge = connectedNodes !== null && !isConnectedToHighlight;
            const midX = (fromX + toX) / 2;

            return (
              <g key={`edge-${i}`}>
                <path
                  d={`M ${fromX} ${fromY} C ${midX} ${fromY}, ${midX} ${toY}, ${toX} ${toY}`}
                  fill="none"
                  stroke={isHighlighted ? "#3b82f6" : "#94a3b8"}
                  strokeWidth={isHighlighted ? "3" : "2"}
                  className={cn("transition-all", isHighlighted && "dark:stroke-blue-400")}
                  markerEnd="url(#arrowhead)"
                  opacity={shouldDimEdge ? 0.15 : (isHighlighted ? 1 : 0.5)}
                />
              </g>
            );
          })}

          {/* Render nodes */}
          {nodes.map((node) => {
            const colors = STATE_COLORS[node.state] || STATE_COLORS.proposed;
            const isHovered = hoveredNode === node.id;
            const isHighlightedTicket = highlightedTicketId === node.id;
            const isConnectedToHighlight = connectedNodes?.has(node.id) ?? false;
            const isConnectedToHover = edges.some(e => e.fromNode.id === node.id || e.toNode.id === node.id) && hoveredNode !== null;

            // Determine opacity: dim if we have a highlight and this node isn't connected
            const shouldDim = connectedNodes !== null && !isConnectedToHighlight;
            const shouldHighlight = isHovered || (isConnectedToHover && !isHovered);

            return (
              <g
                key={node.id}
                transform={`translate(${node.x}, ${node.y})`}
                onMouseEnter={() => setHoveredNode(node.id)}
                onMouseLeave={() => setHoveredNode(null)}
                className="cursor-pointer"
                style={{ transition: 'all 0.2s ease' }}
              >
                {/* Node shadow */}
                <rect
                  width="170"
                  height="70"
                  rx="8"
                  x="2"
                  y="2"
                  fill="black"
                  opacity="0.1"
                />

                {/* Node background */}
                <rect
                  width="170"
                  height="70"
                  rx="8"
                  fill={colors.fill}
                  stroke={isHighlightedTicket ? "#fbbf24" : colors.stroke}
                  strokeWidth={isHighlightedTicket ? "4" : isHovered ? "3" : "2"}
                  className="transition-all"
                  filter={node.state === "executing" || isHighlightedTicket ? "url(#glow)" : undefined}
                  opacity={shouldDim ? 0.25 : (shouldHighlight && !isHovered ? 0.4 : 1)}
                />

                {/* Node content container */}
                <g>
                  {/* State indicator dot */}
                  <circle
                    cx="12"
                    cy="12"
                    r="4"
                    fill={colors.text}
                    opacity="0.8"
                  />

                  {/* Priority badge */}
                  {node.priority !== null && (
                    <g transform="translate(145, 8)">
                      <rect
                        width="18"
                        height="18"
                        rx="3"
                        fill="black"
                        opacity="0.2"
                      />
                      <text
                        x="9"
                        y="13"
                        textAnchor="middle"
                        fill={colors.text}
                        className="text-[10px] font-bold"
                      >
                        P{node.priority >= 80 ? "0" : node.priority >= 60 ? "1" : node.priority >= 40 ? "2" : "3"}
                      </text>
                    </g>
                  )}

                  {/* Ticket ID */}
                  <text
                    x="85"
                    y="22"
                    textAnchor="middle"
                    fill={colors.text}
                    className="text-[9px] font-mono opacity-70"
                  >
                    {node.id.slice(0, 8)}
                  </text>

                  {/* Title */}
                  <text
                    x="85"
                    y="40"
                    textAnchor="middle"
                    fill={colors.text}
                    className="text-xs font-semibold"
                  >
                    {node.title.length > 20 ? node.title.slice(0, 20) + "..." : node.title}
                  </text>

                  {/* State label */}
                  <text
                    x="85"
                    y="56"
                    textAnchor="middle"
                    fill={colors.text}
                    className="text-[10px] uppercase font-medium opacity-80"
                  >
                    {node.state === "needs_human" ? "needs human" : node.state.replace("_", " ")}
                  </text>

                  {/* Dependency indicators */}
                  {node.blocked_by_ticket_id && (
                    <g transform="translate(8, 60)">
                      <circle cx="0" cy="0" r="2" fill={colors.text} opacity="0.6" />
                      <text x="5" y="3" fill={colors.text} className="text-[8px]" opacity="0.7">
                        blocked
                      </text>
                    </g>
                  )}

                  {node.dependents.length > 0 && (
                    <g transform="translate(140, 60)">
                      <text x="0" y="3" fill={colors.text} className="text-[8px] text-right" opacity="0.7">
                        {node.dependents.length} deps
                      </text>
                    </g>
                  )}
                </g>

                {/* Hover tooltip */}
                {isHovered && (
                  <g transform="translate(85, -25)">
                    <rect
                      x="-80"
                      y="-15"
                      width="160"
                      height="30"
                      rx="4"
                      fill="black"
                      opacity="0.9"
                    />
                    <text
                      x="0"
                      y="-5"
                      textAnchor="middle"
                      fill="white"
                      className="text-[10px] font-medium"
                    >
                      {node.title}
                    </text>
                    <text
                      x="0"
                      y="6"
                      textAnchor="middle"
                      fill="white"
                      className="text-[9px]"
                      opacity="0.8"
                    >
                      Priority: {node.priority ?? "None"} • {node.state}
                    </text>
                  </g>
                )}
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}
