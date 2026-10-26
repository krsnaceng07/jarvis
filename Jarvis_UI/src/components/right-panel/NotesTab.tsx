import React, { useState } from 'react';
import { Plus, Trash2, Tag } from 'lucide-react';
import { useChat } from '../../state/chatStore';

export const NotesTab: React.FC = () => {
  const { notes, addNote, deleteNote } = useChat();
  const [newTitle, setNewTitle] = useState('');
  const [newContent, setNewContent] = useState('');
  const [isCreating, setIsCreating] = useState(false);

  const handleCreate = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    addNote(newTitle.trim(), newContent.trim(), ['Operator Note']);
    setNewTitle('');
    setNewContent('');
    setIsCreating(false);
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden p-4">
      {/* Top Action Bar */}
      <div className="flex items-center justify-between pb-2 mb-3 border-b border-cyan-500/15">
        <span className="text-xs font-mono text-slate-400">
          SAVED MEMOS ({notes.length})
        </span>

        <button
          onClick={() => setIsCreating(!isCreating)}
          className="flex items-center space-x-1 px-2 py-0.5 rounded bg-cyan-950/60 border border-cyan-400/40 text-cyan-300 text-xs font-medium hover:bg-cyan-900/60 transition-colors"
        >
          <Plus className="w-3 h-3" />
          <span>New Note</span>
        </button>
      </div>

      {/* Note Creation Form Drawer */}
      {isCreating && (
        <form onSubmit={handleCreate} className="p-3 mb-3 rounded-lg bg-slate-900 border border-cyan-500/30 space-y-2">
          <input
            type="text"
            placeholder="Note Title..."
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1 text-xs text-slate-100 focus:outline-none focus:border-cyan-400"
            autoFocus
          />
          <textarea
            placeholder="Note Content / Architectural Memo..."
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            rows={3}
            className="w-full bg-slate-950 border border-slate-700 rounded px-2.5 py-1 text-xs text-slate-100 focus:outline-none focus:border-cyan-400 resize-none font-sans"
          />
          <div className="flex items-center justify-end space-x-2">
            <button
              type="button"
              onClick={() => setIsCreating(false)}
              className="text-xs text-slate-400 hover:text-slate-200 px-2 py-0.5"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-3 py-0.5 bg-cyan-500 text-slate-950 rounded text-xs font-bold hover:bg-cyan-400 transition-colors"
            >
              Save Note
            </button>
          </div>
        </form>
      )}

      {/* Notes List */}
      <div className="flex-1 overflow-y-auto space-y-2.5 pr-1">
        {notes.map((note) => (
          <div
            key={note.id}
            className="p-3 rounded-lg bg-slate-900/50 border border-cyan-500/15 hover:border-cyan-500/35 transition-colors group"
          >
            <div className="flex items-start justify-between mb-1">
              <h4 className="text-xs font-bold text-slate-100 group-hover:text-cyan-300 transition-colors">
                {note.title}
              </h4>
              <button
                onClick={() => deleteNote(note.id)}
                className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400 transition-opacity p-0.5"
                title="Delete Note"
              >
                <Trash2 className="w-3 h-3" />
              </button>
            </div>

            <p className="text-[11px] text-slate-300 font-sans leading-relaxed whitespace-pre-wrap mb-2">
              {note.content}
            </p>

            <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono">
              <span>{note.updatedAt}</span>
              <div className="flex items-center space-x-1">
                <Tag className="w-2.5 h-2.5 text-cyan-400" />
                <span>{note.tags.join(', ')}</span>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};
