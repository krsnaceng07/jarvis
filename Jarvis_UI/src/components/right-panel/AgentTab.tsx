import React from 'react';
import { Cpu, CheckCircle2, Clock, XCircle, Wrench } from 'lucide-react';
import { useChat } from '../../state/chatStore';

export const AgentTab: React.FC = () => {
  const { tasks, cancelTask } = useChat();

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'running':
        return (
          <span className="flex items-center space-x-1 text-[10px] font-mono text-cyan-400 bg-cyan-950/60 border border-cyan-500/40 px-2 py-0.5 rounded">
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-ping" />
            <span>RUNNING</span>
          </span>
        );
      case 'completed':
        return (
          <span className="flex items-center space-x-1 text-[10px] font-mono text-emerald-400 bg-emerald-950/60 border border-emerald-500/40 px-2 py-0.5 rounded">
            <CheckCircle2 className="w-3 h-3 text-emerald-400" />
            <span>COMPLETED</span>
          </span>
        );
      case 'cancelled':
        return (
          <span className="flex items-center space-x-1 text-[10px] font-mono text-red-400 bg-red-950/60 border border-red-500/40 px-2 py-0.5 rounded">
            <XCircle className="w-3 h-3 text-red-400" />
            <span>CANCELLED</span>
          </span>
        );
      default:
        return (
          <span className="flex items-center space-x-1 text-[10px] font-mono text-amber-400 bg-amber-950/60 border border-amber-500/40 px-2 py-0.5 rounded">
            <Clock className="w-3 h-3 text-amber-400" />
            <span>QUEUED</span>
          </span>
        );
    }
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-3">
      {/* Overview stats header */}
      <div className="flex items-center justify-between text-xs font-mono text-slate-400 pb-2 border-b border-cyan-500/15">
        <span>ACTIVE PIPELINES</span>
        <span className="text-cyan-400 font-bold">{tasks.length} REGISTERED</span>
      </div>

      {/* Task Cards */}
      {tasks.map((task) => (
        <div
          key={task.id}
          className="p-3 rounded-lg bg-slate-900/50 border border-cyan-500/20 hover:border-cyan-400/40 transition-colors shadow-sm"
        >
          {/* Header Row */}
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center space-x-2">
              <Cpu className="w-4 h-4 text-cyan-400" />
              <h4 className="text-xs font-bold text-slate-100 tracking-wide">
                {task.title}
              </h4>
            </div>
            {getStatusBadge(task.status)}
          </div>

          {/* Current Step Description */}
          <p className="text-[11px] text-slate-300 font-sans mb-2">
            <span className="text-slate-500 font-mono">Step:</span> {task.currentStep}
          </p>

          {/* Progress Bar (if available) */}
          {task.progress !== null && (
            <div className="w-full bg-slate-800 rounded-full h-1.5 mb-2 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-300 ${
                  task.status === 'completed' ? 'bg-emerald-400' : 'bg-cyan-400'
                }`}
                style={{ width: `${task.progress}%` }}
              />
            </div>
          )}

          {/* Tools Badge & Actions */}
          <div className="flex items-center justify-between pt-1 border-t border-slate-800/80 text-[10px] font-mono">
            <div className="flex items-center space-x-1.5 text-slate-400">
              <Wrench className="w-2.5 h-2.5" />
              <span>{task.toolsUsed.join(', ')}</span>
            </div>

            {task.status === 'running' && (
              <button
                onClick={() => cancelTask(task.id)}
                className="text-red-400 hover:text-red-300 underline font-semibold"
              >
                Cancel Task
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};
