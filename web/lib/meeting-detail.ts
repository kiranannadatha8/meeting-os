/**
 * Shared types for the meeting detail page.
 *
 * These mirror `api/app/models/io.py::MeetingDetail`. If the backend contract
 * changes, update both sides in the same commit — the proxy route is a thin
 * passthrough, so type drift here shows up as a runtime render bug.
 */

export type MeetingStatus = 'queued' | 'processing' | 'complete' | 'failed';
export type SourceType = 'text' | 'audio';

export interface Decision {
  id: string;
  title: string;
  rationale: string;
  source_quote: string;
}

export interface ActionItem {
  id: string;
  title: string;
  owner: string | null;
  due_date: string | null;
  source_quote: string;
}

export interface MeetingSummary {
  tldr: string;
  highlights: string[];
}

export interface MeetingDetail {
  id: string;
  title: string;
  status: MeetingStatus;
  source_type: SourceType;
  source_filename: string;
  transcript: string;
  error_message: string | null;
  created_at: string;
  updated_at: string;
  decisions: Decision[];
  action_items: ActionItem[];
  summary: MeetingSummary | null;
  langsmith_run_ids: string[] | null;
}
