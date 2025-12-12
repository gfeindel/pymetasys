export type UserRole = "user" | "admin";

export interface User {
  id: number;
  email: string;
  role: UserRole;
  created_at: string;
  updated_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

export interface ActionDefinition {
  id: number;
  name: string;
  slug: string;
  description?: string | null;
  input_sequence: string;
  result_regex: string;
  timeout_seconds?: number | null;
  is_enabled: boolean;
  created_by_user_id?: number | null;
  created_at: string;
  updated_at: string;
}

export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "timeout";

export interface ActionJob {
  id: number;
  action_definition_id: number;
  requested_by_user_id: number;
  action_name?: string | null;
  requested_by_email?: string | null;
  status: JobStatus;
  created_at: string;
  started_at?: string | null;
  finished_at?: string | null;
  raw_request_payload?: string | null;
  raw_response?: string | null;
  parsed_result?: string | null;
  error_message?: string | null;
}
