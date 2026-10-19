export type Shortage = { date: string; balance: number; gap: number };

export type Dashboard = {
  business: { name: string; currency: string };
  as_of: string;
  balance: number;
  threshold: number;
  month_to_date: { income: number; expense: number; net: number };
  receivables: { outstanding: number; overdue: number; customers_overdue: number };
  cash_alert: Shortage | null;
  forecast_preview: { date: string; balance: number; status: string }[];
  credit_score: { score: number; band: string };
  top_collections: { customer_id: number; customer_name: string; overdue_amount: number; max_days_overdue: number }[];
  summary: string;
  notifications: { id: number; type: string; message: string; severity?: string; link?: string | null }[];
};

export type ForecastRow = {
  date: string; income: number; expense: number; expected_inflow: number; expected_outflow: number;
  balance: number; low: number; high: number; status: "ok" | "at_risk" | "shortage";
};

export type Forecast = {
  as_of: string; days: number; method: string; history_days: number; start_balance: number; threshold: number;
  series: ForecastRow[]; shortages: Shortage[]; first_shortage: Shortage | null; largest_gap: number;
  min_balance: { date: string; balance: number }; at_risk_days: number; overdue_receivables: number;
  expected_inflows: { date: string; invoice_id: number; customer_id: number; amount: number; expected: number; probability: number }[];
  expected_outflows: { date: string; kind: string; supplier?: string; amount: number; overdue: boolean }[];
  drivers: { date: string; kind: string; supplier?: string; amount: number }[];
};

export type RecoveryCustomer = {
  rank: number; customer_id: number; customer_name: string; score: number; outstanding: number; overdue_amount: number;
  max_days_overdue: number; aging_bucket: "current" | "0-30" | "31-60" | "61-90" | "90+"; p_pay_7d: number;
  action: "stop_credit" | "visit" | "call" | "discount" | "send_reminder" | "wait"; action_label: string;
  softened_for_relationship: boolean; credit_limit: number; credit_limit_basis: string; new_customer: boolean;
  history: { paid_invoices: number; on_time_rate: number | null; avg_delay_days: number | null; partial_rate: number };
  relationship: { purchases_12m: number; invoices_per_month: number; top_customer: boolean };
  late_payment_share: number; closes_shortage: boolean; priority: number;
  tone: "friendly" | "firm" | "final"; risk_level: "low" | "medium" | "high";
  invoices: { invoice_id: number; amount: number; original_amount: number; due_date: string; days_overdue: number }[];
};

export type CollectionPriority = {
  as_of: string; currency: string; shortage_gap: number; total_outstanding: number; total_overdue: number;
  expected_in_7_days: number; model: { method: string; samples: number; positives: number; train_accuracy?: number };
  customers: RecoveryCustomer[];
};

export type ProductClass = "star" | "cash_cow" | "slow" | "dead" | "new" | "inactive";

export type ProductPerf = {
  product_id: number; name: string; product_class: ProductClass; speed?: "fast" | "medium" | "slow";
  unit_cost: number; unit_price: number; stock_qty: number; inventory_value: number;
  units_30d: number; units_90d: number; revenue_30d: number; revenue_90d: number; growth_pct: number | null;
  margin_per_unit: number; margin_pct: number | null; profit_90d: number; profit_share_pct: number;
  daily_units: number; days_of_stock: number | null; turnover: number | null;
  cash_share_pct: number | null; credit_collection_days: number | null; cash_conversion_days: number | null;
  last_sale: string | null; days_since_last_sale: number | null; is_new: boolean;
  demand_30d: number; recommended_qty_change: number; cash_impact: number; action: string;
  discount_pct?: number; scale_up_cash_needed?: number;
};

export type ProductPerformance = {
  as_of: string; currency: string; products: ProductPerf[];
  thresholds: { turnover_median: number; margin_median_pct: number };
  counts: Record<ProductClass, number>;
  cash_budget: number; scale_up_spent: number; scale_up_wanted: number;
  cash_freed_if_cleared: number; cash_tied_in_slow_and_dead: number; shortage_gap: number;
};

export type PlanAction = {
  id: number; rank: number; kind: "collect" | "clear_stock" | "delay_payable" | "cut_expense" | "scale_up" | "financing";
  title: string; target_ref: string | null; cash_impact: number; days_to_impact: number;
  risk: "low" | "medium" | "high"; reasoning: string; optional: boolean; status: "open" | "done" | "dismissed";
  data: Record<string, unknown> & { lands_after_shortage?: boolean }; actual_amount: number | null;
};

export type ActionPlan = {
  currency: string; as_of: string; gap: number; first_shortage: Shortage | null; expected_from_plan: number;
  gap_covered: boolean; remaining_gap: number; done_count: number; realized_so_far: number; actions: PlanAction[];
};

export type AdvisorSummary = {
  as_of: string; currency: string;
  advice: { text: string; generated_by: string; llm_rejected: boolean };
  gap_card: {
    balance: number; threshold: number; first_shortage: Shortage | null; largest_gap: number; shortage_days: number;
    min_balance: { date: string; balance: number }; plan_expected: number; gap_covered: boolean; remaining_gap: number;
  };
  forecast: { date: string; balance: number; low: number; high: number; status: string }[];
  collections: RecoveryCustomer[];
  products: {
    counts: Record<ProductClass, number>; thresholds: { turnover_median: number; margin_median_pct: number };
    cash_budget: number; cash_freed_if_cleared: number; cash_tied_in_slow_and_dead: number;
    items: { product_id: number; name: string; product_class: ProductClass; margin_pct: number | null;
             turnover: number | null; revenue_90d: number; cash_impact: number; action: string }[];
  };
};

// Supplier negotiation assistant
export type Installment = { due_date: string; amount: number };

export type BillOption = {
  bill_id: number; kind: "pay_on_time" | "extension" | "partial"; installments: Installment[]; days_extended: number;
  estimated_fee: number; fee_basis: string; min_balance_after: number; days_below_after: number;
  keeps_cash_safe: boolean; reasoning: string;
};

export type UpcomingBill = {
  bill_id: number; supplier_id: number; supplier: string; outstanding: number; amount: number; due_date: string;
  plan_id: number | null; overdue: boolean;
};

export type Conflict = {
  start: string; end: string; days: number; worst_date: string; worst_gap: number; first_gap: number;
  explanation: string; causes: { date: string; kind: string; supplier?: string; name?: string; amount: number }[];
};

export type DatedRow = {
  date: string; estimated_in: number; receivables_in: number; estimated_out: number; confirmed_out: number;
  adjustment: number; balance: number; below_threshold: boolean;
};

export type Receipt = {
  invoice_id: number; customer: string; outstanding: number; due_date: string; expected_date: string;
  days_late_expected: number; weight: number; counted: number; at_risk: boolean; in_window: boolean; basis: string;
};

export type FinancingOption = {
  offer_id: number; provider: string; name: string; kind: string; is_demo: boolean; label: string;
  funds_available: string; meets_deadline: boolean; principal: number; fees: number; interest: number;
  total_repayment: number; total_cost: number; cost_per_100: number | null; effective_annual_rate_pct: number | null;
  days: number; risk: "low" | "medium" | "high"; repaid_from: string; covers_need?: boolean;
  repayments: { date: string; amount: number; source: string }[];
  invoices?: { invoice_id: number; customer: string; face: number; advance: number }[];
};

export type RecStep = {
  type: "supplier_plan" | "financing"; kind: string; cost: number; relief: number; risk: "low" | "medium" | "high";
  why: string; needs_agreement: boolean; supplier?: string; bill_id?: number; name?: string; plan?: BillOption;
  financing?: FinancingOption; why_not?: string;
};

export type PayablesRecommendation = {
  shortfall: number; shortfall_date: string | null; headline: string; steps: RecStep[]; alternatives: RecStep[];
  total_cost: number; remaining_gap: number; lowest_balance_before?: number; lowest_balance_after?: number;
  reasoning: string[];
};

export type PayablesAnalysis = {
  as_of: string; currency: string; disclaimer: string;
  cashflow: { start_balance: number; threshold: number; series: DatedRow[]; receipts: Receipt[];
              outflows: { date: string; kind: string; supplier?: string; name?: string; amount: number; basis: string }[] };
  conflicts: Conflict[]; upcoming_bills: UpcomingBill[]; bill_options: BillOption[][]; financing: FinancingOption[];
  recommendation: PayablesRecommendation; at_risk_invoices: Receipt[];
};

export type PaymentPlan = {
  id: number; bill_id: number; supplier: string; bill_amount: number; bill_outstanding: number;
  kind: "extension" | "partial" | "custom"; status: "draft" | "approved" | "accepted" | "rejected" | "cancelled" | "completed";
  note: string | null; supplier_response_note: string | null; estimated_fee: number; paid_so_far: number;
  remaining: number; affects_forecast: boolean;
  installments: { id: number; due_date: string; amount: number; status: "scheduled" | "paid"; paid_date: string | null }[];
};

export type NegotiationDraft = {
  id: number; bill_id: number; plan_id: number | null; lang: string; message: string; generated_by: string;
  status: "draft" | "marked_sent"; note: string;
};

export type RecHistoryItem = {
  id: number; created_at: string; shortfall: number; shortfall_date: string | null; headline: string;
  total_cost: number; steps: { type: string; kind: string; cost: number; relief: number; name: string | null }[];
};

export type Reminder = {
  id: number; invoice_id: number; message: string; tone: string; channel: string; status: string; generated_by: string;
};

export type Bill = {
  id: number; supplier_id: number; supplier_name: string; amount: number; due_date: string;
  paid_date: string | null; status: string; note: string | null;
};

export type CreditFactor = {
  key: string; label: string; weight: number; value: number; baseline: number; contribution: number; tip?: string;
};

export type Credit = {
  score: number; band: string; factors: CreditFactor[]; reasons_positive: string[]; reasons_negative: string[];
  confidence?: { level: "low" | "medium" | "high"; months_used: number; missing: string[] };
  inputs: Record<string, number>;
};

export type LoanOption = {
  product_id: number; name: string; lender: string; kind: string; rate: number; tenure_months: number;
  recommended_amount: number; monthly_installment: number; total_interest: number; cost_per_100: number;
};

export type LoanReadiness = {
  ready: boolean; score: number; band: string; safe_monthly_installment: number; max_recommended_amount: number;
  capacity: { months_used: number; monthly_net_cash_flow: number[]; ncf_p25: number; alpha: number; existing_emi: number; safe_emi: number };
  checklist: { item: string; done: boolean; detail: string }[];
  disclaimer: string;
};

export type WhatIf = {
  inputs: Record<string, number>;
  base: { series: { date: string; balance: number }[]; shortage_days: number; end_balance: number; min_balance: { date: string; balance: number } };
  scenario: { series: { date: string; balance: number }[]; shortage_days: number; end_balance: number; min_balance: { date: string; balance: number } };
  end_balance_change: number;
  threshold: number;
};

export type AgentReply = {
  answer: string; provider: string; tools_used: string[]; grounded: boolean; unverified_figures: string[];
};

export type LoanCatalogItem = {
  product_id: number; name: string; lender: string; kind: string; rate: number; tenure_months: number;
  min_amount: number; max_amount: number; min_score: number;
  status: "eligible" | "capacity_too_low" | "score_too_low";
  reason?: string; points_needed?: number; monthly_needed?: number;
  recommended_amount?: number; monthly_installment?: number; total_interest?: number; cost_per_100?: number | null;
};
