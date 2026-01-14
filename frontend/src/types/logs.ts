/**
 * Type definitions for normalized log entries
 */

export type LogEntryType =
  | "thinking"
  | "assistant_message"
  | "file_edit"
  | "file_create"
  | "file_delete"
  | "command_run"
  | "tool_call"
  | "error"
  | "user_message"
  | "system_message"
  | "loading"
  | "todo_list";

export interface NormalizedLogEntry {
  id: string;
  job_id: string;
  sequence: number;
  timestamp: string;
  entry_type: LogEntryType;
  content: string;
  metadata: Record<string, any>;
  collapsed?: boolean;
  highlight?: boolean;
}

export interface FileEditMetadata {
  file_path: string;
  diff?: string;
  new_content?: string;
  language?: string;
}

export interface CommandRunMetadata {
  command: string;
  output?: string;
  exit_code?: number;
}

export interface ToolCallMetadata {
  tool_name: string;
  args?: Record<string, any>;
  result?: any;
}

export interface ErrorMetadata {
  error_type?: string;
  traceback?: string;
}
