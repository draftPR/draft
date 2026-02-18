import { useState } from "react";
import { Settings, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  EditorSettingsCard,
  AgentSettingsCard,
  BudgetSettingsCard,
  KeyboardShortcutsCard,
  WelcomeTutorialCard,
  PlannerSettingsCard,
  type BudgetSettings,
  loadBudgetSettings,
  saveBudgetSettings,
} from "@/components/SettingsPanel";
import {
  getPreferredEditor,
  setPreferredEditor,
  type EditorType,
} from "@/services/editorIntegration";
import { playSound } from "@/services/soundNotifications";

export function SettingsPage() {
  const [editor, setEditor] = useState<EditorType>(getPreferredEditor());
  const [defaultAgent, setDefaultAgent] = useState(() =>
    localStorage.getItem("smartkanban_default_agent") ?? "claude"
  );
  const [budget, setBudget] = useState<BudgetSettings>(loadBudgetSettings);
  const [hasChanges, setHasChanges] = useState(false);

  const handleEditorChange = (value: string) => {
    setEditor(value as EditorType);
    setPreferredEditor(value as EditorType);
    setHasChanges(true);
  };

  const handleBudgetChange = (key: keyof BudgetSettings, value: number | boolean) => {
    setBudget(prev => ({ ...prev, [key]: value }));
    setHasChanges(true);
  };

  const handleSave = () => {
    saveBudgetSettings(budget);
    if (typeof window !== "undefined") {
      localStorage.setItem("smartkanban_default_agent", defaultAgent);
    }
    setHasChanges(false);
    playSound("success");
  };

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="page-title flex items-center gap-2">
            <Settings className="h-5 w-5" />
            Settings
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Configure Alma Kanban to match your workflow
          </p>
        </div>
        {hasChanges && (
          <Button onClick={handleSave}>
            <Save className="h-4 w-4 mr-2" />
            Save Changes
          </Button>
        )}
      </div>

      <Tabs defaultValue="general">
        <TabsList>
          <TabsTrigger value="general">General</TabsTrigger>
          <TabsTrigger value="executors">Executors</TabsTrigger>
          <TabsTrigger value="budget">Budget</TabsTrigger>
        </TabsList>

        <TabsContent value="general" className="space-y-6 mt-4">
          <EditorSettingsCard editor={editor} onEditorChange={handleEditorChange} />
          <KeyboardShortcutsCard />
          <WelcomeTutorialCard />
        </TabsContent>

        <TabsContent value="executors" className="space-y-6 mt-4">
          <AgentSettingsCard
            defaultAgent={defaultAgent}
            onAgentChange={(v) => { setDefaultAgent(v); setHasChanges(true); }}
          />
          <PlannerSettingsCard onDirty={() => setHasChanges(true)} />
        </TabsContent>

        <TabsContent value="budget" className="space-y-6 mt-4">
          <BudgetSettingsCard budget={budget} onBudgetChange={handleBudgetChange} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
