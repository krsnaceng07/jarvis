import React, { useState } from 'react';
import { 
  Bot, 
  MessageSquare, 
  CreditCard, 
  HelpCircle, 
  Activity, 
  ChevronDown, 
  Check
} from 'lucide-react';
import { useAssistant } from '../../state/assistantStore';
import { audioService } from '../../services/audioService';

interface TopBarProps {
  onOpenFeedback: () => void;
  onOpenBilling: () => void;
  onOpenSupport: () => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  onOpenFeedback,
  onOpenBilling,
  onOpenSupport
}) => {
  const { systemName, version, awarenessEnabled, toggleAwareness } = useAssistant();
  const [themeOpen, setThemeOpen] = useState(false);
  const [profileOpen, setProfileOpen] = useState(false);
  const [currentTheme, setCurrentTheme] = useState('Dark Cyan (Default)');
  const themes = ['Dark Cyan (Default)', 'Cyberpunk Neon', 'Deep Space Navy', 'Obsidian Minimal'];

  return (
    <header className="z-40 flex h-[38px] w-full shrink-0 items-center justify-between border-b border-[#15353e] bg-[#02070b] px-[10px] select-none">
      {/* Left: Branding & Core Navigation Links */}
      <div className="flex items-center space-x-5">
        {/* Logo / App Name */}
        <div className="flex items-center space-x-2 text-cyan-400 font-bold tracking-wider cursor-pointer group" onClick={() => audioService.playClick()}>
          <div className="flex h-5 w-5 items-center justify-center rounded-[3px] border border-[#1c3f49] bg-[#061019] text-cyan-300">
            <Bot className="w-3.5 h-3.5" />
          </div>
          <span className="text-[13px] font-semibold tracking-[0.22em] text-slate-100 group-hover:text-cyan-300 transition-colors uppercase">
            {systemName} AI
          </span>
        </div>

        {/* Action Links */}
        <nav className="ml-1 flex items-center space-x-2">
          <button
            onClick={() => { audioService.playClick(); onOpenFeedback(); }}
            className="flex h-[22px] items-center space-x-1.5 rounded-[3px] border border-[#1c3f49] bg-[#050e13] px-2 text-[11px] text-slate-400 transition-colors hover:border-cyan-500/60 hover:text-cyan-200"
            title="Send User Feedback"
          >
            <MessageSquare className="w-3 h-3" />
            <span>Feedback</span>
          </button>

          <button
            onClick={() => { audioService.playClick(); onOpenBilling(); }}
            className="flex h-[22px] items-center space-x-1.5 rounded-[3px] border border-[#1c3f49] bg-[#050e13] px-2 text-[11px] text-slate-400 transition-colors hover:border-emerald-500/60 hover:text-emerald-200"
            title="Account Subscription & Billing"
          >
            <CreditCard className="w-3 h-3 text-emerald-500/80" />
            <span>Manage Billing</span>
          </button>

          <button
            onClick={() => { audioService.playClick(); onOpenSupport(); }}
            className="flex h-[22px] items-center space-x-1.5 rounded-[3px] border border-[#1c3f49] bg-[#050e13] px-2 text-[11px] text-slate-400 transition-colors hover:border-cyan-500/60 hover:text-cyan-200"
            title="System Documentation & Support"
          >
            <HelpCircle className="w-3 h-3 text-cyan-500/80" />
            <span>Support</span>
          </button>
        </nav>
      </div>

      {/* Right Controls: Version, Awareness Toggle, Theme, Profile */}
      <div className="flex items-center space-x-3">
        {/* Version Badge */}
        <div className="flex items-center space-x-1.5 text-[11px] text-slate-400 font-mono tracking-wider">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse"></span>
          <span>{version}</span>
        </div>

        {/* Awareness Pulse Switch */}
        <div 
          onClick={toggleAwareness}
          className={`flex items-center space-x-1.5 px-2 py-0.5 rounded cursor-pointer border transition-all ${
            awarenessEnabled 
              ? 'bg-amber-950/30 border-amber-500/40 text-amber-300' 
              : 'bg-slate-900 border-slate-700/50 text-slate-400'
          }`}
          title="Neural Context Awareness & Ambient Perception"
        >
          <Activity className={`w-3 h-3 ${awarenessEnabled ? 'animate-pulse text-amber-400' : ''}`} />
          <span className="text-[11px] font-semibold tracking-wider uppercase">Awareness</span>
          <div className={`w-5 h-2.5 rounded-full p-0.5 flex items-center transition-colors ${
            awarenessEnabled ? 'bg-amber-500 justify-end' : 'bg-slate-700 justify-start'
          }`}>
            <div className="w-1.5 h-1.5 rounded-full bg-slate-950"></div>
          </div>
        </div>

        {/* Theme Dropdown */}
        <div className="relative">
          <button 
            onClick={() => { audioService.playClick(); setThemeOpen(!themeOpen); setProfileOpen(false); }}
            className="flex items-center space-x-1 px-2 py-0.5 text-xs text-slate-300 hover:text-cyan-300 bg-slate-900/60 border border-cyan-500/20 rounded hover:border-cyan-400/40 transition-all"
          >
            <span className="text-[11px]">Theme</span>
            <ChevronDown className="w-3 h-3 text-slate-400" />
          </button>

          {themeOpen && (
            <div className="absolute right-0 mt-1 w-44 bg-[#0a1120] border border-cyan-500/40 rounded shadow-xl py-1 z-50 text-xs">
              {themes.map((t) => (
                <div 
                  key={t}
                  onClick={() => {
                    audioService.playClick();
                    setCurrentTheme(t);
                    setThemeOpen(false);
                  }}
                  className="px-3 py-1.5 flex items-center justify-between hover:bg-cyan-950/50 text-slate-300 hover:text-cyan-300 cursor-pointer"
                >
                  <span>{t}</span>
                  {currentTheme === t && <Check className="w-3 h-3 text-cyan-400" />}
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Profile Dropdown */}
        <div className="relative">
          <button 
            onClick={() => { audioService.playClick(); setProfileOpen(!profileOpen); setThemeOpen(false); }}
            className="flex items-center space-x-1.5 px-2 py-0.5 text-xs text-slate-300 hover:text-cyan-300 bg-slate-900/60 border border-cyan-500/20 rounded hover:border-cyan-400/40 transition-all"
          >
            <div className="w-3.5 h-3.5 rounded-full bg-gradient-to-tr from-amber-500 to-cyan-400 flex items-center justify-center text-[8px] font-bold text-slate-950">
              K
            </div>
            <span className="text-[11px]">Profile</span>
            <ChevronDown className="w-3 h-3 text-slate-400" />
          </button>

          {profileOpen && (
            <div className="absolute right-0 mt-1 w-48 bg-[#0a1120] border border-cyan-500/40 rounded shadow-xl py-1 z-50 text-xs">
              <div className="px-3 py-1.5 border-b border-cyan-500/20">
                <p className="font-semibold text-slate-200">Krishna Singh</p>
                <p className="text-[10px] text-cyan-400/80 font-mono">Operator ID: ARCHITECT-01</p>
              </div>
              <div 
                onClick={() => { audioService.playClick(); setProfileOpen(false); }}
                className="px-3 py-1.5 hover:bg-cyan-950/50 text-slate-300 hover:text-cyan-300 cursor-pointer"
              >
                Access Standing Grants
              </div>
              <div 
                onClick={() => { audioService.playClick(); setProfileOpen(false); }}
                className="px-3 py-1.5 hover:bg-cyan-950/50 text-slate-300 hover:text-cyan-300 cursor-pointer"
              >
                Security Credentials
              </div>
            </div>
          )}
        </div>

      </div>
    </header>
  );
};
