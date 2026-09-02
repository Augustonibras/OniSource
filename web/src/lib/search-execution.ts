export const SEARCH_TIME_BUDGET_MS = 45_000;
export const CLASSIFICATION_TIMEOUT_MS = 8_000;
export const CLASSIFICATION_CONCURRENCY = 5;
export const MAX_CLASSIFIED_DOMAINS = 20;
export const CLASSIFICATION_CACHE_TTL_MS = 30 * 24 * 60 * 60 * 1000;

export function remainingMs(deadline: number) {
  return Math.max(0, Math.floor(deadline - performance.now()));
}

export function isFreshClassification(createdAt: string, now = Date.now()) {
  return now - Date.parse(createdAt) <= CLASSIFICATION_CACHE_TTL_MS;
}

export async function mapWithConcurrency<T, R>(
  items: T[],
  concurrency: number,
  worker: (item: T) => Promise<R>,
) {
  const results = new Array<R | undefined>(items.length);
  let nextIndex = 0;
  async function runWorker() {
    while (nextIndex < items.length) {
      const index = nextIndex;
      nextIndex += 1;
      results[index] = await worker(items[index]);
    }
  }
  await Promise.all(
    Array.from(
      { length: Math.min(concurrency, items.length) },
      runWorker,
    ),
  );
  return results;
}
