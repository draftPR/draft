/**
 * Editor integration service for opening files in external editors.
 * Supports VS Code, Cursor, and generic file:// protocol.
 */

export type EditorType = "vscode" | "cursor" | "default";

interface EditorConfig {
  name: string;
  protocol: string;
  fileTemplate: string;
  lineTemplate?: string;
}

const EDITOR_CONFIGS: Record<EditorType, EditorConfig> = {
  vscode: {
    name: "VS Code",
    protocol: "vscode://",
    fileTemplate: "vscode://file{path}",
    lineTemplate: "vscode://file{path}:{line}",
  },
  cursor: {
    name: "Cursor",
    protocol: "cursor://",
    fileTemplate: "cursor://file{path}",
    lineTemplate: "cursor://file{path}:{line}",
  },
  default: {
    name: "System Default",
    protocol: "file://",
    fileTemplate: "file://{path}",
    lineTemplate: "file://{path}",
  },
};

let preferredEditor: EditorType = "vscode";

/**
 * Get the URL to open a file in an editor
 */
export function getEditorUrl(
  path: string,
  line?: number,
  editor?: EditorType
): string {
  const config = EDITOR_CONFIGS[editor || preferredEditor];
  
  // Normalize path - ensure it starts with /
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  
  if (line && config.lineTemplate) {
    return config.lineTemplate
      .replace("{path}", normalizedPath)
      .replace("{line}", String(line));
  }
  
  return config.fileTemplate.replace("{path}", normalizedPath);
}

/**
 * Open a file in the preferred editor
 */
export function openInEditor(
  path: string,
  line?: number,
  editor?: EditorType
): void {
  const url = getEditorUrl(path, line, editor);
  window.open(url, "_blank");
}

/**
 * Set the preferred editor
 */
export function setPreferredEditor(editor: EditorType): void {
  preferredEditor = editor;
  if (typeof window !== "undefined") {
    localStorage.setItem("smartkanban_preferred_editor", editor);
  }
}

/**
 * Get the preferred editor
 */
export function getPreferredEditor(): EditorType {
  return preferredEditor;
}

/**
 * Get list of available editors
 */
export function getAvailableEditors(): { type: EditorType; name: string }[] {
  return Object.entries(EDITOR_CONFIGS).map(([type, config]) => ({
    type: type as EditorType,
    name: config.name,
  }));
}

/**
 * Initialize editor settings from localStorage
 */
export function initEditorSettings(): void {
  if (typeof window === "undefined") return;
  
  const stored = localStorage.getItem("smartkanban_preferred_editor");
  if (stored && stored in EDITOR_CONFIGS) {
    preferredEditor = stored as EditorType;
  }
}

/**
 * Open a workspace/folder in the editor
 */
export function openWorkspaceInEditor(
  workspacePath: string,
  editor?: EditorType
): void {
  const config = EDITOR_CONFIGS[editor || preferredEditor];
  
  // Normalize path
  const normalizedPath = workspacePath.startsWith("/") 
    ? workspacePath 
    : `/${workspacePath}`;
  
  // Build folder URL
  let url: string;
  if (config.protocol === "vscode://") {
    url = `vscode://file${normalizedPath}`;
  } else if (config.protocol === "cursor://") {
    url = `cursor://file${normalizedPath}`;
  } else {
    url = `file://${normalizedPath}`;
  }
  
  window.open(url, "_blank");
}

/**
 * Check if a file path is likely code (for syntax highlighting decisions)
 */
export function getFileLanguage(path: string): string {
  const ext = path.split(".").pop()?.toLowerCase();
  
  const languageMap: Record<string, string> = {
    // Web
    js: "javascript",
    jsx: "javascript",
    ts: "typescript",
    tsx: "typescript",
    html: "html",
    css: "css",
    scss: "scss",
    json: "json",
    
    // Python
    py: "python",
    pyw: "python",
    
    // Systems
    rs: "rust",
    go: "go",
    c: "c",
    cpp: "cpp",
    h: "c",
    hpp: "cpp",
    
    // JVM
    java: "java",
    kt: "kotlin",
    scala: "scala",
    
    // Config/Data
    yaml: "yaml",
    yml: "yaml",
    toml: "toml",
    xml: "xml",
    
    // Shell
    sh: "bash",
    bash: "bash",
    zsh: "bash",
    
    // Other
    md: "markdown",
    sql: "sql",
    graphql: "graphql",
    dockerfile: "dockerfile",
  };
  
  return languageMap[ext || ""] || "plaintext";
}

/**
 * Generate a clickable file link for a diff
 */
export function generateFileLink(
  filePath: string,
  workspacePath?: string,
  lineNumber?: number
): { url: string; display: string } {
  const fullPath = workspacePath 
    ? `${workspacePath}/${filePath}`
    : filePath;
  
  return {
    url: getEditorUrl(fullPath, lineNumber),
    display: filePath + (lineNumber ? `:${lineNumber}` : ""),
  };
}

// Initialize on module load
if (typeof window !== "undefined") {
  initEditorSettings();
}
