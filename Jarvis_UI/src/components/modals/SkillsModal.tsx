import React, { useState } from 'react';
import { BookOpen, CheckCircle2, PauseCircle, X, Search } from 'lucide-react';
import { useModules } from '../../state/moduleStore';

export const SkillsModal: React.FC = () => {
  const { skills, toggleSkill, closeModal } = useModules();
  const [filter, setFilter] = useState('');

  const filtered = skills.filter(
    (s) =>
      s.name.toLowerCase().includes(filter.toLowerCase()) ||
      s.category.toLowerCase().includes(filter.toLowerCase()) ||
      s.description.toLowerCase().includes(filter.toLowerCase())
  );

  return (
    <div className="w-[560px] max-w-[90vw] bg-[#070e1c] border border-emerald-500/50 rounded-xl shadow-[0_0_35px_rgba(16,185,129,0.25)] p-5 flex flex-col max-h-[85vh]">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-emerald-500/20">
        <div className="flex items-center space-x-2.5">
          <div className="w-8 h-8 rounded bg-emerald-950/60 border border-emerald-400 flex items-center justify-center">
            <BookOpen className="w-4 h-4 text-emerald-400" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wider">
              DECLARATIVE AGENT SKILLS REGISTRY
            </h3>
            <p className="text-[11px] text-emerald-400/80 font-mono">
              Self-Healing Tool Pipelines & Atomic Execution
            </p>
          </div>
        </div>
        <button
          onClick={closeModal}
          className="text-slate-400 hover:text-emerald-300 p-1"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Filter */}
      <div className="my-3 relative">
        <Search className="w-3.5 h-3.5 text-emerald-400 absolute left-3 top-2.5" />
        <input
          type="text"
          placeholder="Filter skills by capability, category, or tool name..."
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="w-full bg-slate-950 border border-emerald-500/30 rounded-lg pl-9 pr-3 py-1.5 text-xs text-slate-200 placeholder:text-slate-500 focus:outline-none focus:border-emerald-400 font-mono"
        />
      </div>

      {/* Skills Grid */}
      <div className="flex-1 overflow-y-auto space-y-2 pr-1">
        {filtered.map((skill) => {
          const isActive = skill.status === 'active';
          return (
            <div
              key={skill.id}
              className="p-3 rounded-lg bg-slate-900/60 border border-emerald-500/20 hover:border-emerald-500/50 flex items-start justify-between transition-colors"
            >
              <div className="pr-3">
                <div className="flex items-center space-x-2 mb-1">
                  <span className="text-xs font-bold text-slate-100 font-mono">
                    {skill.name}
                  </span>
                  <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-500/30">
                    {skill.category}
                  </span>
                  <span className="text-[10px] text-slate-500 font-mono">
                    v{skill.version}
                  </span>
                </div>
                <p className="text-xs text-slate-300 font-sans leading-relaxed">
                  {skill.description}
                </p>
              </div>

              {/* Status Toggle Button */}
              <button
                onClick={() => toggleSkill(skill.id)}
                className={`flex items-center space-x-1 px-2.5 py-1 rounded text-xs font-semibold shrink-0 transition-colors ${
                  isActive
                    ? 'bg-emerald-950/80 border border-emerald-400 text-emerald-300 shadow-[0_0_8px_rgba(0,255,136,0.3)]'
                    : 'bg-slate-800 text-slate-400 border border-slate-700'
                }`}
              >
                {isActive ? (
                  <>
                    <CheckCircle2 className="w-3 h-3 text-emerald-400" />
                    <span>ACTIVE</span>
                  </>
                ) : (
                  <>
                    <PauseCircle className="w-3 h-3 text-slate-400" />
                    <span>STANDBY</span>
                  </>
                )}
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
};
