/**
 * MarkdownEditor -- TipTap-based rich markdown editor for ticket descriptions.
 *
 * Supports: headings, bold, italic, code, code blocks (syntax highlighted),
 * lists, task lists, tables, links, blockquotes.
 */

import { useEditor, EditorContent } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import Placeholder from "@tiptap/extension-placeholder";
import CodeBlockLowlight from "@tiptap/extension-code-block-lowlight";
import { Table } from "@tiptap/extension-table";
import TableRow from "@tiptap/extension-table-row";
import TableCell from "@tiptap/extension-table-cell";
import TableHeader from "@tiptap/extension-table-header";
import Link from "@tiptap/extension-link";
import TaskList from "@tiptap/extension-task-list";
import TaskItem from "@tiptap/extension-task-item";
import { common, createLowlight } from "lowlight";
import { useCallback, useEffect } from "react";
import { Button } from "@/components/ui/button";
import {
  Bold,
  Italic,
  Code,
  List,
  ListOrdered,
  Heading2,
  Undo,
  Redo,
  CodeSquare,
  Quote,
  ListTodo,
  Link as LinkIcon,
  Table as TableIcon,
} from "lucide-react";

const lowlight = createLowlight(common);

function ToolbarButton({
  onClick,
  active,
  children,
  title,
}: {
  onClick: () => void;
  active?: boolean;
  children: React.ReactNode;
  title: string;
}) {
  return (
    <Button
      type="button"
      variant={active ? "secondary" : "ghost"}
      size="sm"
      onClick={onClick}
      className="h-7 w-7 p-0"
      title={title}
    >
      {children}
    </Button>
  );
}

interface MarkdownEditorProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  editable?: boolean;
  className?: string;
  minHeight?: string;
}

export function MarkdownEditor({
  value,
  onChange,
  placeholder = "Write a description...",
  editable = true,
  className = "",
  minHeight = "120px",
}: MarkdownEditorProps) {
  const editor = useEditor({
    extensions: [
      StarterKit.configure({
        heading: { levels: [2, 3] },
        codeBlock: false, // replaced by CodeBlockLowlight
      }),
      Placeholder.configure({
        placeholder,
      }),
      CodeBlockLowlight.configure({
        lowlight,
      }),
      Table.configure({
        resizable: false,
      }),
      TableRow,
      TableCell,
      TableHeader,
      Link.configure({
        openOnClick: false,
        HTMLAttributes: {
          class: "text-primary underline underline-offset-2",
        },
      }),
      TaskList,
      TaskItem.configure({
        nested: true,
      }),
    ],
    content: value,
    editable,
    onUpdate: ({ editor }) => {
      onChange(editor.getHTML());
    },
  });

  // Sync external value changes
  useEffect(() => {
    if (editor && value !== editor.getHTML()) {
      editor.commands.setContent(value || "");
    }
  }, [editor, value]);

  const handleLinkInsert = useCallback(() => {
    if (!editor) return;
    const url = window.prompt("Enter URL:");
    if (url) {
      editor.chain().focus().setLink({ href: url }).run();
    }
  }, [editor]);

  const handleTableInsert = useCallback(() => {
    if (!editor) return;
    editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run();
  }, [editor]);

  if (!editor) return null;

  return (
    <div className={`border border-border rounded-md ${className}`}>
      {/* Toolbar */}
      {editable && (
        <div className="flex items-center gap-0.5 px-2 py-1 border-b border-border bg-muted/30 flex-wrap">
          <ToolbarButton
            onClick={() =>
              editor.chain().focus().toggleHeading({ level: 2 }).run()
            }
            active={editor.isActive("heading", { level: 2 })}
            title="Heading"
          >
            <Heading2 className="h-3.5 w-3.5" />
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleBold().run()}
            active={editor.isActive("bold")}
            title="Bold"
          >
            <Bold className="h-3.5 w-3.5" />
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleItalic().run()}
            active={editor.isActive("italic")}
            title="Italic"
          >
            <Italic className="h-3.5 w-3.5" />
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleCode().run()}
            active={editor.isActive("code")}
            title="Inline code"
          >
            <Code className="h-3.5 w-3.5" />
          </ToolbarButton>

          <div className="w-px h-4 bg-border mx-1" />

          <ToolbarButton
            onClick={() => editor.chain().focus().toggleCodeBlock().run()}
            active={editor.isActive("codeBlock")}
            title="Code block"
          >
            <CodeSquare className="h-3.5 w-3.5" />
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleBlockquote().run()}
            active={editor.isActive("blockquote")}
            title="Blockquote"
          >
            <Quote className="h-3.5 w-3.5" />
          </ToolbarButton>

          <div className="w-px h-4 bg-border mx-1" />

          <ToolbarButton
            onClick={() => editor.chain().focus().toggleBulletList().run()}
            active={editor.isActive("bulletList")}
            title="Bullet list"
          >
            <List className="h-3.5 w-3.5" />
          </ToolbarButton>
          <ToolbarButton
            onClick={() =>
              editor.chain().focus().toggleOrderedList().run()
            }
            active={editor.isActive("orderedList")}
            title="Numbered list"
          >
            <ListOrdered className="h-3.5 w-3.5" />
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().toggleTaskList().run()}
            active={editor.isActive("taskList")}
            title="Task list"
          >
            <ListTodo className="h-3.5 w-3.5" />
          </ToolbarButton>

          <div className="w-px h-4 bg-border mx-1" />

          <ToolbarButton
            onClick={handleLinkInsert}
            active={editor.isActive("link")}
            title="Insert link"
          >
            <LinkIcon className="h-3.5 w-3.5" />
          </ToolbarButton>
          <ToolbarButton
            onClick={handleTableInsert}
            title="Insert table"
          >
            <TableIcon className="h-3.5 w-3.5" />
          </ToolbarButton>

          <div className="w-px h-4 bg-border mx-1" />

          <ToolbarButton
            onClick={() => editor.chain().focus().undo().run()}
            title="Undo"
          >
            <Undo className="h-3.5 w-3.5" />
          </ToolbarButton>
          <ToolbarButton
            onClick={() => editor.chain().focus().redo().run()}
            title="Redo"
          >
            <Redo className="h-3.5 w-3.5" />
          </ToolbarButton>
        </div>
      )}

      {/* Editor content */}
      <EditorContent
        editor={editor}
        className="px-3 py-2 prose prose-sm dark:prose-invert max-w-none focus-within:outline-none"
        style={{ minHeight }}
      />
    </div>
  );
}
