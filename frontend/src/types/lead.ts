export interface ExtractedRequirement {
  product_name?: string | null;
  product_category?: string | null;
  quantity?: number | null;
  unit?: string | null;
  city?: string | null;
  state?: string | null;
  delivery_time?: string | null;
  buyer_intent?: string | null;
  confidence_score?: number;
}

export interface ValidationResult {
  is_valid: boolean;
  missing_fields: string[];
  warnings: string[];
  message: string;
}

export interface MatchedProduct {
  product_id: number;
  name: string;
  category_id?: number | null;
  category_name?: string | null;
  supplier_id: number;
  price?: number | null;
  moq?: number | null;
  stock?: number | null;
  match_score: number;
  match_reason: string;
}

export interface RankedSupplier {
  rank: number;
  supplier_id: number;
  name: string;
  city?: string | null;
  state?: string | null;
  rating?: number | null;
  verified: boolean;
  response_time_hours?: number | null;
  matching_products: string[];
  matching_product_ids?: number[];
  product_match_score: number;
  rating_score: number;
  verified_score: number;
  response_time_score: number;
  order_performance_score: number;
  location_score: number;
  final_score: number;
  explanation: string;
}

export interface NodeExecution {
  node_name: string;
  execution_order: number;
  duration_ms: number;
  status: string;
  error_message?: string | null;
}

export interface LeadAnalyzeResponse {
  run_id?: string;
  workflow_status: string;
  extracted_requirement: ExtractedRequirement | null;
  validation_result: ValidationResult | null;
  matched_products: MatchedProduct[];
  recommended_suppliers: RankedSupplier[];
  session_id?: string;
  error?: string | null;
  ranking_formula?: string;
  stop_reason?: string | null;
  latency_ms?: number;
  node_executions?: NodeExecution[];
}

export const LEAD_EXAMPLE_REQUIREMENTS: string[] = [
  'Need 500 solar panels in Jaipur',
  'Looking for industrial water pumps for my factory in Delhi',
  'Need bulk packaging boxes in Mumbai',
  'Need 200 agricultural machines',
];
