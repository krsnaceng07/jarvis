/**
 * Web Speech API Integration for Local Voice Recognition & Synthesis
 */

export interface SpeechRecognitionResultPayload {
  transcript: string;
  isFinal: boolean;
}

type SpeechCallback = (payload: SpeechRecognitionResultPayload) => void;
type StateCallback = (state: 'idle' | 'listening' | 'error') => void;

class SpeechService {
  private recognition: unknown = null;
  private isListening = false;
  private onResultCallback: SpeechCallback | null = null;
  private onStateCallback: StateCallback | null = null;

  constructor() {
    if (typeof window !== 'undefined') {
      const SpeechRecognition =
        (window as unknown as { SpeechRecognition: unknown }).SpeechRecognition ||
        (window as unknown as { webkitSpeechRecognition: unknown }).webkitSpeechRecognition;

      if (SpeechRecognition) {
        try {
          const rec = new (SpeechRecognition as new () => {
            continuous: boolean;
            interimResults: boolean;
            lang: string;
            onresult: (e: { resultIndex: number; results: Array<Array<{ transcript: string }> & { isFinal: boolean }> }) => void;
            onerror: (e: { error: string }) => void;
            onend: () => void;
            start: () => void;
            stop: () => void;
          })();

          rec.continuous = true;
          rec.interimResults = true;
          rec.lang = 'en-US';

          rec.onresult = (event) => {
            for (let i = event.resultIndex; i < event.results.length; ++i) {
              const res = event.results[i];
              if (this.onResultCallback && res[0]) {
                this.onResultCallback({
                  transcript: res[0].transcript,
                  isFinal: res.isFinal,
                });
              }
            }
          };

          rec.onerror = () => {
            this.isListening = false;
            if (this.onStateCallback) this.onStateCallback('error');
          };

          rec.onend = () => {
            this.isListening = false;
            if (this.onStateCallback) this.onStateCallback('idle');
          };

          this.recognition = rec;
        } catch {
          this.recognition = null;
        }
      }
    }
  }

  public isSupported(): boolean {
    return this.recognition !== null;
  }

  public getIsListening(): boolean {
    return this.isListening;
  }

  public startListening(onResult: SpeechCallback, onState: StateCallback): boolean {
    this.onResultCallback = onResult;
    this.onStateCallback = onState;

    if (!this.recognition) {
      // Simulate listening in dev environment
      this.isListening = true;
      onState('listening');
      return false;
    }

    try {
      (this.recognition as { start: () => void }).start();
      this.isListening = true;
      onState('listening');
      return true;
    } catch {
      this.isListening = false;
      onState('error');
      return false;
    }
  }

  public stopListening() {
    this.isListening = false;
    if (this.recognition) {
      try {
        (this.recognition as { stop: () => void }).stop();
      } catch {
        // Safe catch
      }
    }
    if (this.onStateCallback) {
      this.onStateCallback('idle');
    }
  }

  public speak(text: string, onEnd?: () => void) {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.pitch = 0.95;
      utterance.rate = 1.05;

      const voices = window.speechSynthesis.getVoices();
      const englishVoice = voices.find(v => v.lang.startsWith('en') && (v.name.includes('Google') || v.name.includes('Natural') || v.name.includes('David')));
      if (englishVoice) {
        utterance.voice = englishVoice;
      }

      utterance.onend = () => {
        if (onEnd) onEnd();
      };
      utterance.onerror = () => {
        if (onEnd) onEnd();
      };

      window.speechSynthesis.speak(utterance);
    } else {
      setTimeout(() => {
        if (onEnd) onEnd();
      }, 1500);
    }
  }

  public cancelSpeech() {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.cancel();
    }
  }
}

export const speechService = new SpeechService();
