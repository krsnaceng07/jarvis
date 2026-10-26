export type VisualHubTab = 'visual hub' | 'gesture';

export interface VisualPrompt {
  id: string;
  number: string;
  title: string;
  description: string;
  tags: string[];
}

export interface VisualHistoryItem {
  id: string;
  title: string;
  date: string;
  thumbnailType: 'blueprint' | 'concept' | 'diagram' | 'audio' | 'anatomy';
  category: string;
  resolution?: string;
}

export interface MapEvent {
  id: string;
  name: string;
  lat: number;
  lng: number;
  status: 'active' | 'warning' | 'alert';
  type: string;
  country: string;
  telemetry: string;
}

export interface HeadlineItem {
  id: string;
  number: string;
  title: string;
  source: string;
  timestamp: string;
  category: string;
  content: string;
  url?: string;
}
