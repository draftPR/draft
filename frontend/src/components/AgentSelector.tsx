import { useState, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  Bot,
  Check,
  X,
  Zap,
  MessageSquare,
  Plug,
  DollarSign,
  Info,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { fetchAgents, type AgentInfo, type AgentListResponse } from "@/services/api";

interface AgentSelectorProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  className?: string;
  showDetails?: boolean;
}

const AGENT_ICONS: Record<string, React.ReactNode> = {
  claude: <Bot className="h-4 w-4" />,
  cursor: <Bot className="h-4 w-4" />,
  amp: <Zap className="h-4 w-4" />,
  aider: <Bot className="h-4 w-4" />,
  gemini: <Bot className="h-4 w-4" />,
  codex: <Bot className="h-4 w-4" />,
};

function AgentFeatureBadge({ 
  enabled, 
  label, 
  icon 
}: { 
  enabled: boolean; 
  label: string; 
  icon: React.ReactNode;
}) {
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <Badge 
            variant={enabled ? "default" : "outline"} 
            className={cn(
              "text-xs gap-1",
              !enabled && "opacity-50"
            )}
          >
            {icon}
            {enabled ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
          </Badge>
        </TooltipTrigger>
        <TooltipContent>
          <p>{label}: {enabled ? "Supported" : "Not supported"}</p>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

function AgentDetails({ agent }: { agent: AgentInfo }) {
  return (
    <div className="mt-2 p-3 bg-muted/50 rounded-lg space-y-2">
      <div className="flex items-center gap-2 text-sm">
        <Badge variant={agent.available ? "default" : "destructive"}>
          {agent.available ? "Available" : "Not Installed"}
        </Badge>
        <span className="text-muted-foreground">{agent.description}</span>
      </div>
      
      <div className="flex flex-wrap gap-2">
        <AgentFeatureBadge 
          enabled={agent.supports_yolo} 
          label="Auto Mode (YOLO)" 
          icon={<Zap className="h-3 w-3" />}
        />
        <AgentFeatureBadge 
          enabled={agent.supports_session_resume} 
          label="Session Resume" 
          icon={<MessageSquare className="h-3 w-3" />}
        />
        <AgentFeatureBadge 
          enabled={agent.supports_mcp} 
          label="MCP Support" 
          icon={<Plug className="h-3 w-3" />}
        />
      </div>
      
      {(agent.cost_per_1k_input || agent.cost_per_1k_output) && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <DollarSign className="h-3 w-3" />
          <span>
            ${agent.cost_per_1k_input?.toFixed(3) || "?"}/1K in, 
            ${agent.cost_per_1k_output?.toFixed(3) || "?"}/1K out
          </span>
        </div>
      )}
    </div>
  );
}

export function AgentSelector({ 
  value, 
  onChange, 
  disabled = false,
  className,
  showDetails = false,
}: AgentSelectorProps) {
  const [agents, setAgents] = useState<AgentInfo[]>([]);
  const [defaultAgent, setDefaultAgent] = useState("claude");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  useEffect(() => {
    const loadAgents = async () => {
      try {
        const response = await fetchAgents();
        setAgents(response.agents);
        setDefaultAgent(response.default_agent);
        
        // Set default value if not already set
        if (!value && response.default_agent) {
          onChange(response.default_agent);
        }
      } catch (err) {
        console.error("Failed to load agents:", err);
        setError("Failed to load agents");
      } finally {
        setLoading(false);
      }
    };
    
    loadAgents();
  }, []);
  
  const selectedAgent = agents.find(a => a.type === value);
  
  if (loading) {
    return (
      <Select disabled>
        <SelectTrigger className={className}>
          <SelectValue placeholder="Loading agents..." />
        </SelectTrigger>
      </Select>
    );
  }
  
  if (error) {
    return (
      <div className="text-sm text-red-500">{error}</div>
    );
  }
  
  return (
    <div className="space-y-2">
      <Select 
        value={value || defaultAgent} 
        onValueChange={onChange}
        disabled={disabled}
      >
        <SelectTrigger className={cn("w-full", className)}>
          <SelectValue placeholder="Select an AI agent">
            {selectedAgent && (
              <div className="flex items-center gap-2">
                {AGENT_ICONS[selectedAgent.type] || <Bot className="h-4 w-4" />}
                <span>{selectedAgent.name}</span>
                {!selectedAgent.available && (
                  <Badge variant="outline" className="ml-auto text-xs">
                    Not installed
                  </Badge>
                )}
              </div>
            )}
          </SelectValue>
        </SelectTrigger>
        <SelectContent>
          {agents.map((agent) => (
            <SelectItem 
              key={agent.type} 
              value={agent.type}
              disabled={!agent.available}
            >
              <div className="flex items-center gap-2 w-full">
                {AGENT_ICONS[agent.type] || <Bot className="h-4 w-4" />}
                <span>{agent.name}</span>
                {!agent.available && (
                  <Badge variant="outline" className="ml-auto text-xs opacity-50">
                    Not installed
                  </Badge>
                )}
                {agent.available && agent.supports_yolo && (
                  <Zap className="h-3 w-3 text-amber-500 ml-auto" />
                )}
              </div>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      
      {showDetails && selectedAgent && (
        <AgentDetails agent={selectedAgent} />
      )}
    </div>
  );
}

// Simple compact version for inline use
export function AgentBadge({ agentType }: { agentType: string }) {
  const [agent, setAgent] = useState<AgentInfo | null>(null);
  
  useEffect(() => {
    fetchAgents().then(response => {
      const found = response.agents.find(a => a.type === agentType);
      if (found) setAgent(found);
    }).catch(() => {});
  }, [agentType]);
  
  if (!agent) return null;
  
  return (
    <Badge variant="outline" className="gap-1">
      {AGENT_ICONS[agent.type] || <Bot className="h-3 w-3" />}
      {agent.name}
    </Badge>
  );
}
