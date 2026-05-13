/**
 * Citation preprocessing utilities.
 *
 * Converts HMRC section references like [VIT55400] or 【VIT55400】
 * into markdown links [VIT55400](cite:VIT55400) that react-markdown
 * can parse and our `a` component override can intercept.
 */

// Regex to match [CODE] or fullwidth 【CODE】
export const CITATION_RE = /(\[[A-Z]{2,6}\d{4,6}\]|【[A-Z]{2,6}\d{4,6}】)/g;
export const CITATION_EXTRACT_RE = /^[\[【]([A-Z]{2,6}\d{4,6})[\]】]$/;

/**
 * Pre-process a markdown string to convert citation patterns into
 * markdown links with a `cite:` protocol.
 *
 * Examples:
 *   "[VIT55400]"  → "[VIT55400](cite:VIT55400)"
 *   "【PE63500】" → "[PE63500](cite:PE63500)"
 *   "normal text" → "normal text" (unchanged)
 */
export function preprocessCitations(content: string): string {
  // Pull standalone citations that the LLM placed on a new line back into the previous paragraph
  let processed = content.replace(/(?:\r?\n)+\s*(\[[A-Z]{2,6}\d{4,6}\]|【[A-Z]{2,6}\d{4,6}】)/g, ' $1');

  return processed.replace(CITATION_RE, (match) => {
    const inner = match.match(CITATION_EXTRACT_RE);
    if (inner) {
      return `[${inner[1]}](cite:${inner[1]})`;
    }
    return match;
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
  return href.replace("cite:", "");
}
