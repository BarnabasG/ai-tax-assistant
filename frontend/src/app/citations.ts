/**
 * Citation preprocessing utilities.
 *
 * Converts HMRC section references like [VIT55400] or 【VIT55400】
 * into markdown links [VIT55400](cite:VIT55400) that react-markdown
 * can parse and our `a` component override can intercept.
 */

// Regex to match [CODE] or fullwidth 【CODE】 supporting manuals or GOV.UK guides
export const CITATION_RE = /[\[【][\s\u202F]*([A-Z]{2,6}\d{4,6}|GOV:[a-zA-Z0-9\-\/]+)[\s\u202F]*[\]】]/gi;
export const CITATION_EXTRACT_RE = /^[\[【][\s\u202F]*([A-Z]{2,6}\d{4,6}|GOV:[a-zA-Z0-9\-\/]+)[\s\u202F]*[\]】]$/i;

/**
 * Extract unique citations in order of appearance.
 */
export function getSequentialCitations(content: string): string[] {
  const seen = new Set<string>();
  const order: string[] = [];

  CITATION_RE.lastIndex = 0;
  let match;
  while ((match = CITATION_RE.exec(content)) !== null) {
    const code = match[1];
    if (code && !seen.has(code)) {
      seen.add(code);
      order.push(code);
    }
  }
  return order;
}

export function preprocessCitations(content: string): string {
  // Pull standalone citations on new lines back into the previous paragraph
  const pull_re = /(?:\r?\n)+[\s\u202F]*(\[[\s\u202F]*(?:[A-Z]{2,6}\d{4,6}|GOV:[a-zA-Z0-9\-\/]+)[\s\u202F]*\]|【[\s\u202F]*(?:[A-Z]{2,6}\d{4,6}|GOV:[a-zA-Z0-9\-\/]+)[\s\u202F]*】)/gi;
  let processed = content.replace(pull_re, ' $1');

  const seenCodes = new Set<string>();
  const codeToIndex = new Map<string, number>();
  let nextIndex = 1;

  return processed.replace(CITATION_RE, (match, code) => {
    let seqIndex = codeToIndex.get(code);
    if (seqIndex === undefined) {
      seqIndex = nextIndex++;
      codeToIndex.set(code, seqIndex);
    }

    if (seenCodes.has(code)) {
      return `[${code}](cite:${code}?seq=${seqIndex}&dup=true)`;
    }
    seenCodes.add(code);
    return `[${code}](cite:${code}?seq=${seqIndex})`;
  });
}

/**
 * Check if an href is a citation link (cite: protocol).
 */
export function isCitationHref(href: string | undefined): boolean {
  return href?.startsWith("cite:") ?? false;
}

/**
 * Extract the section code from a cite: href.
 * Returns null if the href is not a citation link.
 */
export function extractCitationCode(href: string | undefined): string | null {
  if (!href?.startsWith("cite:")) return null;
  return href.replace("cite:", "").split("?")[0];
}
