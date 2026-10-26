import React, { useState, useEffect } from 'react';
import { Settings, X, Server, Mic } from 'lucide-react';
import { useModules } from '../../state/moduleStore';
import { backendBridge } from '../../services/backendBridge';

export const SettingsModal: React.FC = () => {
  const { settings, updateSettings, closeModal } = useModules();

  const [vad, setVad] = useState(settings.vadSensitivity);
  const [bargeIn, setBargeIn] = useState(settings.autoBargeIn);
  const [port, setPort] = useState(settings.localServerPort);

  useEffect(() => {
    backendBridge.fetchSettings().then((s) => {
      if (s) {
        if (s.speech_threshold !== undefined) setVad(s.speech_threshold / 100);
        if (s.gateway_port) setPort(s.gateway_port);
      }
    });
  }, []);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    updateSettings({
      vadSensitivity: vad,
      autoBargeIn: bargeIn,
      localServerPort: port
    });
    closeModal();
  };

  return (
    <div className="w-[520px] max-w-[90vw] bg-[#070e1c] border border-sky-500/50 rounded-xl shadow-[0_0_35px_rgba(56,189,248,0.25)] p-5 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-sky-500/20">
        <div className="flex items-center space-x-2.5">
          <div className="w-8 h-8 rounded bg-sky-950/60 border border-sky-400 flex items-center justify-center">
            <Settings className="w-4 h-4 text-sky-400" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-100 uppercase tracking-wider">
              HARDWARE & RUNTIME CONFIGURATION
            </h3>
            <p className="text-[11px] text-sky-400/80 font-mono">
              Silero VAD • Duplex Pipeline • Gateway RPC
            </p>
          </div>
        </div>
        <button
          onClick={closeModal}
          className="text-slate-400 hover:text-sky-300 p-1"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <form onSubmit={handleSave} className="space-y-4 my-4 text-xs">
        {/* VAD Sensitivity */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-slate-200 font-semibold flex items-center space-x-1.5">
              <Mic className="w-3.5 h-3.5 text-sky-400" />
              <span>Silero VAD Speech Threshold</span>
            </span>
            <span className="text-sky-400 font-mono">{vad.toFixed(2)} (Default: 0.55)</span>
          </div>
          <input
            type="range"
            min="0.3"
            max="0.8"
            step="0.05"
            value={vad}
            onChange={(e) => setVad(parseFloat(e.target.value))}
            className="w-full accent-sky-400"
          />
          <p className="text-[10px] text-slate-400 mt-0.5">
            Probability threshold required to trigger user speech onset within 32ms audio slice.
          </p>
        </div>

        {/* Barge-in Cutoff Toggle */}
        <div className="flex items-center justify-between p-2.5 rounded bg-slate-900/60 border border-sky-500/20">
          <div>
            <span className="text-slate-200 font-semibold block">
              Sub-40ms Audio Barge-in Cutoff
            </span>
            <span className="text-[10px] text-slate-400">
              Immediately mutes assistant speaker when user speaks over audio.
            </span>
          </div>
          <input
            type="checkbox"
            checked={bargeIn}
            onChange={(e) => setBargeIn(e.target.checked)}
            className="w-4 h-4 accent-sky-500 cursor-pointer"
          />
        </div>

        {/* Local Gateway Port */}
        <div>
          <label className="block text-slate-200 font-semibold mb-1 flex items-center space-x-1.5">
            <Server className="w-3.5 h-3.5 text-sky-400" />
            <span>Local Gateway Port</span>
          </label>
          <input
            type="number"
            value={port}
            onChange={(e) => setPort(parseInt(e.target.value, 10))}
            className="w-full bg-slate-950 border border-slate-700 rounded px-3 py-1.5 text-slate-100 focus:outline-none focus:border-sky-400 font-mono"
          />
        </div>

        <div className="pt-3 border-t border-sky-500/20 flex items-center justify-end space-x-2">
          <button
            type="button"
            onClick={closeModal}
            className="px-3 py-1 text-slate-400 hover:text-slate-200"
          >
            Cancel
          </button>
          <button
            type="submit"
            className="px-4 py-1 bg-sky-500 hover:bg-sky-400 text-slate-950 rounded font-bold shadow-[0_0_12px_rgba(56,189,248,0.4)] transition-colors"
          >
            Save Configuration
          </button>
        </div>
      </form>
    </div>
  );
};
