export function extractJsonValue(text: string): string | null {
  const trimmed = text.trim();
  const fenced = trimmed.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  const source = fenced ? fenced[1].trim() : trimmed;
  const objectStart = source.indexOf("{");
  const arrayStart = source.indexOf("[");
  const starts = [objectStart, arrayStart].filter((index) => index >= 0);
  if (starts.length === 0) return null;

  const start = Math.min(...starts);
  const closers: string[] = [];
  let inString = false;
  let escaped = false;

  for (let index = start; index < source.length; index += 1) {
    const character = source[index];
    if (inString) {
      if (escaped) escaped = false;
      else if (character === "\\") escaped = true;
      else if (character === '"') inString = false;
      continue;
    }
    if (character === '"') inString = true;
    else if (character === "{") closers.push("}");
    else if (character === "[") closers.push("]");
    else if (character === "}" || character === "]") {
      if (closers.at(-1) !== character) return null;
      closers.pop();
      if (closers.length === 0) return source.slice(start, index + 1);
    }
  }

  return null;
}

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
