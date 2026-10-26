import React, { useState } from 'react';
import { TopBar } from './components/shell/TopBar';
import { SatLinkFeed } from './components/left-panel/SatLinkFeed';
import { ModuleConnectorStack } from './components/center/ModuleConnectorStack';
import { AssistantHologramPanel } from './components/center/AssistantHologramPanel';
import { VisualHubPanel } from './components/visual-hub/VisualHubPanel';
import { RightPanelWorkspace } from './components/right-panel/RightPanelWorkspace';
import { ModalContainer } from './components/shell/ModalContainer';
import { HeadlineItem } from './types/visualHub';

export const App: React.FC = () => {
  const [selectedHeadline, setSelectedHeadline] = useState<HeadlineItem | null>(null);
  const [expandedMap, setExpandedMap] = useState(false);
  const [infoModal, setInfoModal] = useState<{ title: string; content: string } | null>(null);

  return (
    <div className="relative flex h-screen w-screen flex-col overflow-hidden bg-[#000408] font-hud text-slate-100">
      {/* 1. Global Full-Width Header Bar */}
      <TopBar
        onOpenFeedback={() =>
          setInfoModal({
            title: 'Operator Feedback',
            content:
              'Thank you for test-driving the JARVIS Holographic Interface. Feedback telemetry is transmitted directly to local logs and system diagnostic telemetry.',
          })
        }
        onOpenBilling={() =>
          setInfoModal({
            title: 'Manage Billing & Model Grants',
            content:
              'Active Tier: Sovereign Developer Edition. All local LLM gateways, neural VAD pipelines, and autonomous agent lanes are unlocked with unlimited execution quota.',
          })
        }
        onOpenSupport={() =>
          setInfoModal({
            title: 'System Architecture & Documentation',
            content:
              'JARVIS runs an autonomous multi-package workspace with Silero VAD, SQLite dual-persistence, LanceDB vector indexing, and Three.js WebGL visualization.',
          })
        }
      />

      {/* 2. Three-column workspace locked to the reference 1536x831 grid. */}
      <main className="grid min-h-0 w-full flex-1 grid-cols-[minmax(240px,276fr)_minmax(560px,750fr)_minmax(360px,469fr)] gap-[11px] overflow-hidden px-[10px] pb-[7px] pt-0">
        {/* Left Column: satellite and headlines panels */}
        <section className="h-full min-w-0 overflow-hidden">
          <SatLinkFeed
            onSelectHeadline={(hl) => setSelectedHeadline(hl)}
            onExpandMap={() => setExpandedMap(true)}
          />
        </section>

        {/* Center Workspace: connector stack, hologram and visual hub */}
        <section className="grid h-full min-w-0 grid-rows-[371fr_384fr] gap-[17px] overflow-hidden">
          <div className="flex h-full min-h-0 w-full items-end justify-between overflow-visible pl-[17px]">
            <div className="h-full min-h-0 min-w-0 flex-1">
              <ModuleConnectorStack />
            </div>

            {/* Reference card is 341x340, bottom-aligned inside a 371px row. */}
            <div className="mr-7 h-[calc(100%-31px)] w-[45.5%] min-w-[300px] max-w-[360px] shrink-0">
              <AssistantHologramPanel />
            </div>
          </div>

          <div className="min-h-0 w-full overflow-hidden">
            <VisualHubPanel />
          </div>
        </section>

        {/* Right Column: VOICE / AGENT / NOTES Workspace */}
        <section className="h-full min-w-0 overflow-hidden">
          <RightPanelWorkspace />
        </section>
      </main>

      {/* 3. Global Modal & Dialog Container */}
      <ModalContainer
        selectedHeadline={selectedHeadline}
        onCloseHeadline={() => setSelectedHeadline(null)}
        expandedMap={expandedMap}
        onCloseMap={() => setExpandedMap(false)}
        infoModal={infoModal}
        onCloseInfo={() => setInfoModal(null)}
      />
    </div>
  );
};

export default App;
