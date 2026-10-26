import React, { useEffect } from 'react';
import { useModules } from '../../state/moduleStore';
import { MemoryModal } from '../modals/MemoryModal';
import { SkillsModal } from '../modals/SkillsModal';
import { CharacterModal } from '../modals/CharacterModal';
import { SettingsModal } from '../modals/SettingsModal';
import { HeadlineModal } from '../modals/HeadlineModal';
import { ExpandedMapModal } from '../modals/ExpandedMapModal';
import { HeadlineItem } from '../../types/visualHub';

interface ModalContainerProps {
  selectedHeadline: HeadlineItem | null;
  onCloseHeadline: () => void;
  expandedMap: boolean;
  onCloseMap: () => void;
  infoModal: { title: string; content: string } | null;
  onCloseInfo: () => void;
}

export const ModalContainer: React.FC<ModalContainerProps> = ({
  selectedHeadline,
  onCloseHeadline,
  expandedMap,
  onCloseMap,
  infoModal,
  onCloseInfo,
}) => {
  const { activeModal, closeModal } = useModules();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        closeModal();
        onCloseHeadline();
        onCloseMap();
        onCloseInfo();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [closeModal, onCloseHeadline, onCloseMap, onCloseInfo]);

  const hasAnyModal = activeModal || selectedHeadline || expandedMap || infoModal;
  if (!hasAnyModal) return null;

  if (activeModal === 'CHARACTER') return <CharacterModal />;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-md animate-fadeIn">
      {/* Background click to dismiss */}
      <div 
        className="absolute inset-0" 
        onClick={() => {
          closeModal();
          onCloseHeadline();
          onCloseMap();
          onCloseInfo();
        }} 
      />

      <div className="relative z-10 animate-scaleUp">
        {activeModal === 'MEMORY' && <MemoryModal />}
        {activeModal === 'SKILLS' && <SkillsModal />}
        {activeModal === 'SETTINGS' && <SettingsModal />}
        {expandedMap && <ExpandedMapModal onClose={onCloseMap} />}
        {selectedHeadline && (
          <HeadlineModal headline={selectedHeadline} onClose={onCloseHeadline} />
        )}
        {infoModal && (
          <div className="w-[450px] max-w-[90vw] bg-[#070e1c] border border-cyan-500/50 rounded-xl p-5 shadow-2xl">
            <h3 className="text-sm font-bold text-slate-100 uppercase mb-2">
              {infoModal.title}
            </h3>
            <p className="text-xs text-slate-300 font-sans leading-relaxed mb-4">
              {infoModal.content}
            </p>
            <div className="flex justify-end">
              <button
                onClick={onCloseInfo}
                className="px-3 py-1 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold rounded text-xs"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
