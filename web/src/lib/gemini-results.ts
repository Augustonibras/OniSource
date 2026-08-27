export function extractJsonArray(text: string): string | null {
  const trimmed = text.trim();
  const fenced = trimmed.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  const unfenced = fenced ? fenced[1].trim() : trimmed;
  const completeArray = unfenced.match(/\[[\s\S]*\]/)?.[0];
  if (completeArray) {
    return completeArray;
  }

  const arrayStart = unfenced.indexOf("[");
  if (arrayStart === -1) {
    return null;
  }

  const truncatedArray = unfenced.slice(arrayStart).trim();
  if (truncatedArray.endsWith("]")) {
    return truncatedArray;
  }

  const lastCompleteObject = truncatedArray.lastIndexOf("}");
  if (lastCompleteObject === -1) {
    return truncatedArray;
  }

  return `${truncatedArray.slice(0, lastCompleteObject + 1)}]`;
}
