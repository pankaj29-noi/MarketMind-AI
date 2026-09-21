/** Multi-table Lead Marketplace — only join-safe questions the demo answers. */
export const MARKETPLACE_SAMPLE_QUESTIONS: string[] = [
  'Which product categories generated the highest order value?',
  'Which states generate the most buyer enquiries?',
  'Which suppliers have the highest number of orders?',
  'Which cities have the highest number of buyers?',
  'Which categories have the most leads?',
  'Which suppliers have the best average rating?',
];

/**
 * Analytics demo (4k orders CSV) — populate input only when adaptive panel is off.
 * Answers MUST come from POST /analyze — never hardcode results here.
 * Kept in sync with backend ANALYTICS_DEMO_SUGGESTED_QUESTIONS.
 */
export const ANALYTICS_DEMO_QUESTION_CATEGORIES: Record<string, string[]> = {
  'Quick totals': [
    'What is the total revenue?',
    'What is the total profit?',
    'How many orders are there?',
    'How many unique customers are there?',
  ],
  'Breakdowns & rankings': [
    'Which product category generated the most revenue?',
    'Which region generated the most revenue?',
    'Show revenue by region.',
    'Show the top 10 suppliers by revenue.',
  ],
};

export const ANALYTICS_DEMO_FLAT_QUESTIONS: string[] = Object.values(
  ANALYTICS_DEMO_QUESTION_CATEGORIES
).flat();
