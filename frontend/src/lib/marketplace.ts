/** Multi-table Lead Intelligence curated samples (existing demo). */
export const MARKETPLACE_SAMPLE_QUESTIONS: string[] = [
  'Which product categories generated the highest order value?',
  'What is the lead conversion rate by category?',
  'Which suppliers have the fastest response times?',
  'Show monthly marketplace GMV trends.',
  'Which states generate the most buyer enquiries?',
  'Identify suppliers with high ratings but low order volume.',
  'What are the top products by total demand?',
  'Compare lead volumes across major states.',
];

/**
 * Analytics demo (4k orders CSV) — populate input only.
 * Answers MUST come from POST /analyze — never hardcode results here.
 */
export const ANALYTICS_DEMO_QUESTION_CATEGORIES: Record<string, string[]> = {
  'Quick Questions': [
    'What is the total revenue?',
    'What is the total profit?',
    'How many orders are there?',
    'What is the average order value?',
    'What is the average delivery time?',
  ],
  'Business Analytics': [
    'Show revenue by region.',
    'Compare revenue between different sales channels.',
    'What percentage of orders were cancelled?',
    'Show the top 5 regions by revenue and calculate each region\'s percentage contribution to total revenue.',
  ],
  'Supplier Analytics': [
    'Show the top 10 suppliers by revenue.',
    'Find the top 10 suppliers by revenue, but only include suppliers with at least 20 completed orders.',
    'Which suppliers have above-average profit but below-average delivery time?',
    'Find suppliers whose revenue increased while their order count decreased compared with the previous year.',
  ],
  'Customer Analytics': [
    'How many unique customers are there?',
    'Top 10 customers by total revenue.',
    'Find customers who placed at least 5 completed orders and calculate their average order value.',
    'Which customers have an above-average order value?',
  ],
  'Product Analytics': [
    'Which product category generated the most revenue?',
    'What are the top 10 products by revenue?',
    'Identify the top 5 products within each category by revenue and calculate each product\'s percentage contribution to its category.',
    'Find the top 3 products in each category.',
  ],
  'Time Analysis': [
    'Show monthly revenue for the latest year.',
    'Yearly total revenue.',
    'YoY percent change in total revenue by year.',
    'Compare yearly revenue growth by supplier.',
  ],
  'Advanced Analytics': [
    'What are the top 5 suppliers by profit in each region, excluding suppliers with fewer than 5 completed orders?',
    'Find regions where revenue is above the overall regional average, order count is below the overall regional average, and average delivery time is also below the overall average.',
    'Identify suppliers that rank in the top 20% by revenue but bottom 20% by delivery performance.',
    'Which regions have high revenue but low delivery time?',
  ],
  'Reliability Checks': [
    'Which supplier has the highest employee satisfaction?',
    'Delete all orders from the database.',
  ],
};

export const ANALYTICS_DEMO_FLAT_QUESTIONS: string[] = Object.values(
  ANALYTICS_DEMO_QUESTION_CATEGORIES
).flat();
