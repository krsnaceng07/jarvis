import React, { useState } from 'react';
import { Brain, Search, Plus, Trash2, X } from 'lucide-react';
import { useModules } from '../../state/moduleStore';

export const MemoryModal: React.FC = () => {
  const { memories, addMemory, deleteMemory, closeModal } = useModules();
  const [searchTerm, setSearchTerm] = useState('');
  const [newKey, setNewKey] = useState('');
  const [newValue, setNewValue] = useState('');
  const [category, setCategory] = useState<'preference' | 'fact' | 'credential' | 'workflow'>('fact');

  const filtered = memories.filter(
    (m) =>
      m.key.toLowerCase().includes(searchTerm.toLowerCase()) ||
      m.value.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const handleAdd = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newKey.trim() || !newValue.trim()) return;
    addMemory(newKey.trim(), newValue.trim(), category);
    setNewKey('');
    setNewValue('');
  };

  return (
    <div className="w-[540px] max-w-[90vw] bg-[#070e1c] border border-cyan-500/50 rounded-xl shadow-[0_0_35px_rgba(0,240,255,0.25)] p-5 flex flex-col max-h-[85vh]">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-cyan-500/20">
        <div className="flex items-center space-x-2.5">
          <div className="w-8 h-8 rounded bg-cyan-950/60 border border-cyan-400 flex items-center justify-center">
            <Brain className="w-4 h-4 text-cyan-400" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wider">
              MEMORY SUBSYSTEM (SQLite FTS5 + LanceDB)
            </h3>
            <p className="text-[11px] text-cyan-400/80 font-mono">
              Deterministic Dual-Persistence & Semantic Vectors
            </p>
          </div>
        </div>
        <button
          onClick={closeModal}
          className="text-slate-400 hover:text-cyan-300 p-1"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Search Input */}
      <div className="my-3 relative">
        <Search className="w-3.5 h-3.5 text-cyan-400 absolute left-3 top-2.5" />
        <input
          type="text"
          placeholder="Search associative memories by key or vector semantics..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full bg-slate-950 border border-cyan-500/30 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-cyan-400 font-mono"
        />
      </div>

      {/* Memory Records List */}
      <div className="flex-1 overflow-y-auto space-y-2 pr-1 my-2">
        {filtered.map((item) => (
          <div
            key={item.id}
            className="p-2.5 rounded bg-slate-900/60 border border-cyan-500/15 hover:border-cyan-500/40 flex items-start justify-between group"
          >
            <div>
              <div className="flex items-center space-x-2 mb-1">
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-cyan-950 text-cyan-400 uppercase">
                  {item.category}
                </span>
                <span className="text-xs font-bold text-slate-200 font-mono">
                  {item.key}
                </span>
              </div>
              <p className="text-xs text-slate-300 font-sans leading-relaxed">
                {item.value}
              </p>
              <div className="mt-1 flex items-center space-x-2 text-[10px] text-slate-500 font-mono">
                <span>Source: {item.source}</span>
                <span>•</span>
                <span>{item.updatedAt}</span>
              </div>
            </div>

            <button
              onClick={() => deleteMemory(item.id)}
              className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-red-400 p-1 transition-opacity"
              title="Delete memory record"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          </div>
        ))}
      </div>

      {/* Add New Memory Form */}
      <form onSubmit={handleAdd} className="mt-3 pt-3 border-t border-cyan-500/20 space-y-2">
        <div className="grid grid-cols-12 gap-2">
          <select
            value={category}
            onChange={(e) => setCategory(e.target.value as 'preference' | 'fact' | 'credential' | 'workflow')}
            className="col-span-4 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 font-mono"
          >
            <option value="fact">Fact</option>
            <option value="preference">Preference</option>
            <option value="workflow">Workflow</option>
            <option value="credential">Credential</option>
          </select>
          <input
            type="text"
            placeholder="Key (e.g. user_preferred_editor)"
            value={newKey}
            onChange={(e) => setNewKey(e.target.value)}
            className="col-span-8 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 font-mono"
          />
        </div>
        <div className="flex items-center space-x-2">
          <input
            type="text"
            placeholder="Value..."
            value={newValue}
            onChange={(e) => setNewValue(e.target.value)}
            className="flex-1 bg-slate-950 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 font-mono"
          />
          <button
            type="submit"
            className="flex items-center space-x-1 px-3 py-1 bg-cyan-500 hover:bg-cyan-400 text-slate-950 rounded text-xs font-bold transition-colors"
          >
            <Plus className="w-3 h-3" />
            <span>Store</span>
          </button>
        </div>
      </form>
    </div>
  );
};
