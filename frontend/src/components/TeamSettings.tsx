import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Card, CardContent } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";
import {
  Crown,
  Loader2,
  Plus,
  Trash2,
  Users,
  ChevronDown,
  ChevronUp,
  Code,
  Eye,
  TestTube2,
  Search,
  ClipboardList,
  Server,
  Brain,
  Shield,
  Database,
  MessageSquare,
  Settings,
  BarChart3,
  Layout,
} from "lucide-react";
import type {
  AgentRoleCatalogItem,
  AgentTeam,
  AgentTeamMember,
} from "@/services/api";
import {
  fetchAgentCatalog,
  fetchAgentPresets,
  fetchAgentTeam,
  updateAgentTeam,
  applyTeamPreset,
  addTeamMember,
  removeTeamMember,
  updateTeamMember,
} from "@/services/api";

const EXECUTOR_OPTIONS = [
  { id: "claude", name: "Claude" },
  { id: "cursor-agent", name: "Cursor Agent" },
  { id: "codex", name: "Codex" },
  { id: "gemini", name: "Gemini" },
];

const ICON_MAP: Record<string, React.ReactNode> = {
  crown: <Crown className="h-4 w-4" />,
  clipboard: <ClipboardList className="h-4 w-4" />,
  search: <Search className="h-4 w-4" />,
  code: <Code className="h-4 w-4" />,
  eye: <Eye className="h-4 w-4" />,
  "test-tube": <TestTube2 className="h-4 w-4" />,
  layout: <Layout className="h-4 w-4" />,
  server: <Server className="h-4 w-4" />,
  brain: <Brain className="h-4 w-4" />,
  "chart-line": <BarChart3 className="h-4 w-4" />,
  "message-square": <MessageSquare className="h-4 w-4" />,
  settings: <Settings className="h-4 w-4" />,
  shield: <Shield className="h-4 w-4" />,
  database: <Database className="h-4 w-4" />,
};

interface TeamSettingsProps {
  boardId: string;
}

export function TeamSettings({ boardId }: TeamSettingsProps) {
  const [loading, setLoading] = useState(true);
  const [team, setTeam] = useState<AgentTeam | null>(null);
  const [catalog, setCatalog] = useState<AgentRoleCatalogItem[]>([]);
  const [presets, setPresets] = useState<string[]>([]);
  const [expandedMember, setExpandedMember] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [boardId]);

  const loadData = async () => {
    setLoading(true);
    try {
      const [teamData, catalogData, presetsData] = await Promise.all([
        fetchAgentTeam(boardId),
        fetchAgentCatalog(),
        fetchAgentPresets(),
      ]);
      setTeam(teamData);
      setCatalog(catalogData);
      setPresets(presetsData);
    } catch (err) {
      toast.error("Failed to load team configuration");
    } finally {
      setLoading(false);
    }
  };

  const handleToggleActive = async (active: boolean) => {
    setSaving(true);
    try {
      const updated = await updateAgentTeam(boardId, { is_active: active });
      setTeam(updated);
      toast.success(active ? "Multi-agent mode enabled" : "Multi-agent mode disabled");
    } catch (err) {
      toast.error("Failed to update team");
    } finally {
      setSaving(false);
    }
  };

  const handleApplyPreset = async (preset: string) => {
    setSaving(true);
    try {
      const updated = await applyTeamPreset(boardId, preset);
      setTeam(updated);
      toast.success(`Applied "${preset}" preset`);
    } catch (err) {
      toast.error("Failed to apply preset");
    } finally {
      setSaving(false);
    }
  };

  const handleAddMember = async (role: string) => {
    setSaving(true);
    try {
      const member = await addTeamMember(boardId, { role });
      // Refresh team to get updated members list
      const updated = await fetchAgentTeam(boardId);
      setTeam(updated);
      toast.success(`Added ${member.display_name}`);
    } catch (err) {
      toast.error("Failed to add member");
    } finally {
      setSaving(false);
    }
  };

  const handleRemoveMember = async (memberId: string) => {
    setSaving(true);
    try {
      await removeTeamMember(boardId, memberId);
      const updated = await fetchAgentTeam(boardId);
      setTeam(updated);
      toast.success("Member removed");
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Failed to remove member";
      toast.error(msg);
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateExecutor = async (memberId: string, executorType: string) => {
    try {
      await updateTeamMember(boardId, memberId, { executor_type: executorType });
      const updated = await fetchAgentTeam(boardId);
      setTeam(updated);
    } catch (err) {
      toast.error("Failed to update executor");
    }
  };

  const handleUpdatePrompt = async (memberId: string, prompt: string) => {
    try {
      await updateTeamMember(boardId, memberId, { behavior_prompt: prompt });
      toast.success("Prompt updated");
    } catch (err) {
      toast.error("Failed to update prompt");
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Roles already in the team
  const teamRoles = new Set(team?.members?.map((m) => m.role) ?? []);
  // Available roles to add (not yet in team)
  const availableRoles = catalog.filter((r) => !teamRoles.has(r.role));

  return (
    <div className="space-y-6">
      {/* Enable/Disable Toggle */}
      <div className="flex items-center justify-between">
        <div className="space-y-1">
          <Label className="text-sm font-medium">Multi-Agent Execution</Label>
          <p className="text-xs text-muted-foreground">
            When enabled, tickets are executed by a team of specialized agents instead of a single executor.
          </p>
        </div>
        <Switch
          checked={team?.is_active ?? false}
          onCheckedChange={handleToggleActive}
          disabled={saving}
        />
      </div>

      {/* Preset Selector */}
      <div className="space-y-2">
        <Label className="text-sm font-medium">Team Preset</Label>
        <div className="flex flex-wrap gap-2">
          {presets.map((preset) => (
            <Button
              key={preset}
              variant="outline"
              size="sm"
              onClick={() => handleApplyPreset(preset)}
              disabled={saving}
              className="capitalize"
            >
              {preset.replace(/_/g, " ")}
            </Button>
          ))}
        </div>
        <p className="text-xs text-muted-foreground">
          Apply a preset to quickly configure your team composition.
        </p>
      </div>

      {/* Current Team Members */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <Label className="text-sm font-medium flex items-center gap-2">
            <Users className="h-4 w-4" />
            Team Members ({team?.members?.length ?? 0})
          </Label>
        </div>

        {team?.members && team.members.length > 0 ? (
          <div className="space-y-2">
            {team.members.map((member) => (
              <MemberCard
                key={member.id}
                member={member}
                expanded={expandedMember === member.id}
                onToggleExpand={() =>
                  setExpandedMember(
                    expandedMember === member.id ? null : member.id
                  )
                }
                onRemove={() => handleRemoveMember(member.id)}
                onUpdateExecutor={(exec) =>
                  handleUpdateExecutor(member.id, exec)
                }
                onUpdatePrompt={(prompt) =>
                  handleUpdatePrompt(member.id, prompt)
                }
                saving={saving}
              />
            ))}
          </div>
        ) : (
          <Card>
            <CardContent className="py-8 text-center text-sm text-muted-foreground">
              No team members configured. Apply a preset or add members from the catalog below.
            </CardContent>
          </Card>
        )}
      </div>

      {/* Add Member from Catalog */}
      {availableRoles.length > 0 && (
        <div className="space-y-3">
          <Label className="text-sm font-medium flex items-center gap-2">
            <Plus className="h-4 w-4" />
            Add from Catalog
          </Label>
          <div className="grid grid-cols-2 gap-2">
            {availableRoles.map((role) => (
              <button
                key={role.role}
                onClick={() => handleAddMember(role.role)}
                disabled={saving}
                className="flex items-center gap-2 p-2 rounded-md border border-dashed border-muted-foreground/30 hover:border-foreground/50 hover:bg-muted/50 transition-colors text-left text-sm disabled:opacity-50"
              >
                <span className="text-muted-foreground">
                  {ICON_MAP[role.icon] ?? <Code className="h-4 w-4" />}
                </span>
                <div className="min-w-0">
                  <div className="font-medium truncate">{role.display_name}</div>
                  <div className="text-xs text-muted-foreground truncate">
                    {role.description}
                  </div>
                </div>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Member Card sub-component
// ---------------------------------------------------------------------------

function MemberCard({
  member,
  expanded,
  onToggleExpand,
  onRemove,
  onUpdateExecutor,
  onUpdatePrompt,
  saving,
}: {
  member: AgentTeamMember;
  expanded: boolean;
  onToggleExpand: () => void;
  onRemove: () => void;
  onUpdateExecutor: (exec: string) => void;
  onUpdatePrompt: (prompt: string) => void;
  saving: boolean;
}) {
  const [localPrompt, setLocalPrompt] = useState(member.behavior_prompt ?? "");
  const catalogIcon = ICON_MAP[member.role === "team_lead" ? "crown" : "code"];

  return (
    <Card className="overflow-hidden">
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-muted/30 transition-colors"
        onClick={onToggleExpand}
      >
        <span className="text-muted-foreground">{catalogIcon}</span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm">{member.display_name}</span>
            {member.is_required && (
              <Badge variant="secondary" className="text-[10px] px-1 py-0">
                Required
              </Badge>
            )}
            {member.receive_mode === "all" && (
              <Badge variant="outline" className="text-[10px] px-1 py-0">
                Orchestrator
              </Badge>
            )}
          </div>
          <div className="text-xs text-muted-foreground">
            {member.executor_type} &middot; {member.role}
          </div>
        </div>
        <div className="flex items-center gap-2">
          {!member.is_required && (
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={(e) => {
                e.stopPropagation();
                onRemove();
              }}
              disabled={saving}
            >
              <Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-red-500" />
            </Button>
          )}
          {expanded ? (
            <ChevronUp className="h-4 w-4 text-muted-foreground" />
          ) : (
            <ChevronDown className="h-4 w-4 text-muted-foreground" />
          )}
        </div>
      </div>

      {expanded && (
        <CardContent className="pt-0 pb-4 space-y-4 border-t">
          {/* Executor */}
          <div className="space-y-1.5 pt-3">
            <Label className="text-xs">Executor</Label>
            <Select
              value={member.executor_type}
              onValueChange={onUpdateExecutor}
            >
              <SelectTrigger className="h-8 text-xs">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {EXECUTOR_OPTIONS.map((opt) => (
                  <SelectItem key={opt.id} value={opt.id}>
                    {opt.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {/* Behavior Prompt */}
          <div className="space-y-1.5">
            <Label className="text-xs">Behavior Prompt</Label>
            <Textarea
              value={localPrompt}
              onChange={(e) => setLocalPrompt(e.target.value)}
              rows={4}
              className="text-xs font-mono"
              placeholder="Instructions for this agent..."
            />
            <Button
              variant="outline"
              size="sm"
              className="text-xs h-7"
              onClick={() => onUpdatePrompt(localPrompt)}
              disabled={saving || localPrompt === (member.behavior_prompt ?? "")}
            >
              Save Prompt
            </Button>
          </div>
        </CardContent>
      )}
    </Card>
  );
}
