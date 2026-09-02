interface TimestampedAnnotation {
  created_at: string;
}

function annotationTime(annotation: TimestampedAnnotation) {
  const parsed = Date.parse(annotation.created_at);
  return Number.isNaN(parsed) ? 0 : parsed;
}

export function annotationEntityKey(name: string) {
  return name.trim().toLowerCase();
}

export function groupAnnotationHistory<T extends TimestampedAnnotation>(
  annotations: T[],
  entityName: (annotation: T) => string,
) {
  const grouped: Record<string, T[]> = {};
  const ordered = [...annotations].sort(
    (left, right) => annotationTime(left) - annotationTime(right),
  );
  for (const annotation of ordered) {
    const key = annotationEntityKey(entityName(annotation));
    if (!grouped[key]) {
      grouped[key] = [];
    }
    grouped[key].push(annotation);
  }
  return grouped;
}

export function latestAnnotation<T>(history: T[] | undefined) {
  return history && history.length > 0 ? history[history.length - 1] : undefined;
}

export function appendAnnotationHistory<T extends TimestampedAnnotation>(
  current: Record<string, T[]>,
  key: string,
  annotation: T,
) {
  return {
    ...current,
    [key]: [...(current[key] ?? []), annotation].sort(
      (left, right) => annotationTime(left) - annotationTime(right),
    ),
  };
}
