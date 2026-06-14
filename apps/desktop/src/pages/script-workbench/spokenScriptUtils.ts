export function countHanCharacters(text: string): number {
  const matches = text.match(/[\u3400-\u9FFF\uF900-\uFAFF]/g);
  return matches?.length ?? 0;
}

export function countLatinWords(text: string): number {
  const withoutCjk = text.replace(/[\u3400-\u9FFF\uF900-\uFAFF]/g, " ");
  return withoutCjk
    .split(/\s+/)
    .map((token) => token.replace(/^[^\w]+|[^\w]+$/g, ""))
    .filter(Boolean).length;
}

export function isCjkHeavyText(text: string): boolean {
  const hanCount = countHanCharacters(text);
  const wordCount = countLatinWords(text);
  return hanCount >= Math.max(wordCount, 1);
}
