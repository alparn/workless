export interface Client {
  id: string;
  company_name: string;
  legal_form: string | null;
  tax_number: string | null;
  vat_id: string | null;
  tax_office: string | null;
  industry: string | null;
  industry_detail: string | null;
  datev_consultant_number: number | null;
  datev_client_number: number | null;
  chart_of_accounts: string;
  account_length: number;
  fiscal_year_start: string;
  default_vat_rate: string;
  auto_booking_threshold: string;
  created_at: string;
  updated_at: string;
}

export const INDUSTRY_KEYS = [
  "gastro",
  "it_services",
  "handel",
  "handwerk",
  "beratung",
  "gesundheit",
  "immobilien",
  "freiberufler",
  "logistik",
  "produktion",
  "landwirtschaft",
  "sonstige",
] as const;

/** @deprecated Use INDUSTRY_KEYS with useTranslations("industries") instead */
export const INDUSTRY_OPTIONS = [
  { key: "gastro", label: "Gastronomie & Hotellerie" },
  { key: "it_services", label: "IT & Software" },
  { key: "handel", label: "Handel (Einzel-/Großhandel)" },
  { key: "handwerk", label: "Handwerk & Bau" },
  { key: "beratung", label: "Beratung & Dienstleistungen" },
  { key: "gesundheit", label: "Gesundheit & Medizin" },
  { key: "immobilien", label: "Immobilien & Vermietung" },
  { key: "freiberufler", label: "Freiberufler / Einzelunternehmen" },
  { key: "logistik", label: "Logistik & Transport" },
  { key: "produktion", label: "Produktion & Fertigung" },
  { key: "landwirtschaft", label: "Landwirtschaft" },
  { key: "sonstige", label: "Sonstige" },
] as const;

export interface ClientCreate {
  company_name: string;
  legal_form?: string | null;
  tax_number?: string | null;
  vat_id?: string | null;
  tax_office?: string | null;
  industry?: string | null;
  industry_detail?: string | null;
  datev_consultant_number?: number | null;
  datev_client_number?: number | null;
  chart_of_accounts?: string;
  account_length?: number;
  fiscal_year_start?: string;
  default_vat_rate?: string;
  auto_booking_threshold?: string;
}

export interface Document {
  id: string;
  client_id: string;
  original_filename: string;
  storage_path: string;
  mime_type: string;
  file_size_bytes: number | null;
  ocr_provider: string | null;
  ocr_confidence: string | null;
  extraction: Record<string, unknown> | null;
  status: string;
  error_details: string | null;
  uploaded_at: string;
  ocr_completed_at: string | null;
  approved_at: string | null;
}

export interface DocumentListItem {
  id: string;
  client_id: string;
  original_filename: string;
  mime_type: string;
  file_size_bytes: number | null;
  status: string;
  uploaded_at: string;
  ocr_completed_at: string | null;
  approved_at: string | null;
}

export interface TaxHints {
  deductibility: "full" | "partial" | "none";
  deductible_percent?: number;
  hint?: string;
  action_required?: string;
  legal_basis?: string;
}

export interface Booking {
  id: string;
  document_id: string;
  client_id: string;
  export_batch_id: string | null;
  amount: string;
  debit_credit: string;
  account: string;
  contra_account: string;
  bu_key: string | null;
  document_date: string;
  reference_1: string | null;
  reference_2: string | null;
  booking_text: string | null;
  cost_center_1: string | null;
  cost_center_2: string | null;
  suggested_by: string;
  ai_confidence: string | null;
  ai_reasoning: string | null;
  status: string;
  created_at: string;
  approved_at: string | null;
  exported_at: string | null;
  bank_name: string | null;
  bank_iban: string | null;
  tax_hints: TaxHints | null;
}

export interface BookingWithDocument extends Booking {
  document_filename: string | null;
  document_extraction: Record<string, unknown> | null;
  document_status: string | null;
}

export interface BookingUpdate {
  account?: string;
  contra_account?: string;
  bu_key?: string | null;
  booking_text?: string | null;
  amount?: string;
  debit_credit?: string;
  cost_center_1?: string | null;
  cost_center_2?: string | null;
}

export interface BatchApproveResponse {
  approved_count: number;
  booking_ids: string[];
}

export interface ExportBatch {
  id: string;
  client_id: string;
  consultant_number: number;
  client_number: number;
  fiscal_year_start: string;
  chart_of_accounts: string;
  account_length: number;
  date_from: string;
  date_to: string;
  label: string | null;
  storage_path: string | null;
  booking_count: number;
  is_locked: boolean;
  created_at: string;
  downloaded_at: string | null;
}

export interface ExportPreview {
  booking_count: number;
  date_from: string;
  date_to: string;
  total_amount: string;
  pending_approval_count: number;
  exported_count: number;
  rejected_count: number;
  documents_with_bookings_count: number;
}

export interface ExportCreateRequest {
  client_id: string;
  date_from: string;
  date_to: string;
  label?: string | null;
}

export interface ClarificationItem {
  booking_id: string;
  document_id: string;
  document_filename: string;
  amount: string;
  debit_credit: string;
  document_date: string;
  booking_text: string | null;
  clarification_category: string;
  clarification_question: string;
  clarification_answer: string | null;
  clarification_resolved: boolean;
  clarification_resolved_at: string | null;
  clarification_resolved_by: string | null;
}

export interface DocumentClarificationGroup {
  document_id: string;
  document_filename: string;
  uploaded_at: string;
  open_count: number;
  resolved_count: number;
  items: ClarificationItem[];
}

export interface EmailDraft {
  subject: string;
  body_text: string;
}

export interface ClarificationListResponse {
  client_id: string;
  company_name: string;
  total_count: number;
  open_count: number;
  resolved_count: number;
  groups: DocumentClarificationGroup[];
  email_draft: EmailDraft;
}

export interface DashboardStats {
  document_count: number;
  booking_count: number;
  pending_reviews: number;
  approved_bookings: number;
  exported_bookings: number;
  total_export_batches: number;
}

/** GET /api/v1/dashboard/:id/financial */
export interface MonthlyFinancialBucket {
  month: string;
  expenses: string;
  revenue: string;
}

export interface FinancialAccountBucket {
  account: string;
  label: string;
  total: string;
}

export interface FinancialVendorRow {
  name: string;
  total: string;
  count: number;
}

export interface FinancialDashboard {
  monthly: MonthlyFinancialBucket[];
  accounts: FinancialAccountBucket[];
  vendors: FinancialVendorRow[];
  total_expenses: string;
  total_revenue: string;
  period_from: string;
  period_to: string;
}

export interface ActivityEntry {
  id: string;
  entity_type: string;
  entity_id: string;
  action: string;
  performed_by: string | null;
  created_at: string;
  summary: string;
}

export interface BankAccount {
  id: string;
  client_id: string;
  account_number: string;
  bank_name: string;
  iban: string | null;
  bic: string | null;
  is_default: boolean;
  label: string | null;
  created_at: string;
  updated_at: string;
}

export interface BankAccountCreate {
  account_number: string;
  bank_name: string;
  iban?: string | null;
  bic?: string | null;
  is_default?: boolean;
  label?: string | null;
}

export interface AgentNotification {
  id: string;
  client_id: string;
  agent_run_id: string | null;
  severity: string;
  category: string;
  title: string;
  message: string;
  entity_type: string | null;
  entity_id: string | null;
  action_required: boolean;
  action_type: string | null;
  action_data: Record<string, unknown> | null;
  is_read: boolean;
  read_at: string | null;
  is_resolved: boolean;
  resolved_at: string | null;
  created_at: string;
}

export interface AgentNotificationCount {
  total: number;
  unread: number;
  action_required: number;
}

export interface AgentRun {
  id: string;
  client_id: string;
  run_type: string;
  target_entity_type: string | null;
  target_entity_id: string | null;
  status: string;
  strategy: string | null;
  attempt_number: number;
  result_summary: string | null;
  details: Record<string, unknown> | null;
  error: string | null;
  items_checked: number;
  items_fixed: number;
  items_flagged: number;
  started_at: string;
  completed_at: string | null;
  duration_ms: number | null;
}

export interface AgentStatus {
  supervisor_enabled: boolean;
  supervisor_interval_seconds: number;
  max_ocr_retries: number;
  notification_counts: AgentNotificationCount;
  recent_runs_count: number;
}

export interface AiSettings {
  chat_provider: string;
  chat_model: string;
  booking_provider: string;
  booking_model: string;
  ocr_provider: string;
  use_global_fallback: boolean;
  langsmith_enabled: boolean;
  anthropic_key_set: boolean;
  mistral_key_set: boolean;
  openai_key_set: boolean;
  tavily_key_set: boolean;
  anthropic_key_hint: string | null;
  mistral_key_hint: string | null;
  openai_key_hint: string | null;
  tavily_key_hint: string | null;
}

export interface AiSettingsUpdate {
  chat_provider?: string;
  chat_model?: string;
  booking_provider?: string;
  booking_model?: string;
  ocr_provider?: string;
  use_global_fallback?: boolean;
  langsmith_enabled?: boolean;
  anthropic_api_key?: string;
  mistral_api_key?: string;
  openai_api_key?: string;
  tavily_api_key?: string;
}

export interface UsageSummary {
  period: string;
  total_input_tokens: number;
  total_output_tokens: number;
  total_thinking_tokens: number;
  total_tokens: number;
  total_cost_eur: string;
  call_count: number;
  by_operation: {
    operation: string;
    total_tokens: number;
    cost_eur: string;
    count: number;
  }[];
  by_day: {
    date: string;
    input_tokens: number;
    output_tokens: number;
    cost_eur: string;
    count: number;
  }[];
}

export interface UsageLogEntry {
  id: string;
  provider: string;
  model: string;
  operation: string;
  input_tokens: number;
  output_tokens: number;
  thinking_tokens: number;
  total_tokens: number;
  estimated_cost_eur: string;
  duration_ms: number;
  created_at: string;
}

export interface AvailableModels {
  providers: Record<string, { id: string; label: string }[]>;
}
