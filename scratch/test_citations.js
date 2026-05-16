
const CITATION_RE = /(\[[\s\u202F]*[A-Z]{2,6}\d{4,6}[\s\u202F]*\]|【[\s\u202F]*[A-Z]{2,6}\d{4,6}[\s\u202F]*】)/g;
const CITATION_EXTRACT_RE = /^[\[【][\s\u202F]*([A-Z]{2,6}\d{4,6})[\s\u202F]*[\]】]$/;

function preprocessCitations(content) {
  let processed = content.replace(/(?:\r?\n)+[\s\u202F]*(\[[\s\u202F]*[A-Z]{2,6}\d{4,6}[\s\u202F]*\]|【[\s\u202F]*[A-Z]{2,6}\d{4,6}[\s\u202F]*】)/g, ' $1');

  return processed.replace(CITATION_RE, (match) => {
    const inner = match.match(CITATION_EXTRACT_RE);
    if (inner) {
      return `[${inner[1]}](cite:${inner[1]})`;
    }
    return match;
  });
}

const text = `
Economic activity test – The VAT manuals state that a holding company must “make or intend to make taxable supplies” in order to be required to register for VAT [ VIT40100 ].
Nature of supplies – Where a holding company provides “management charges” or other services that constitute a supply, it is regarded as carrying on an economic activity and is therefore entitled to register and to reclaim input tax [ VATSC06513 ].
Passive investment only – If the company’s activities are limited to holding shares and receiving dividends – which are classified as “investment activities” and “non‑economic activities for VAT purposes” – it would not be considered to be carrying on a business activity and would not be required (or entitled) to register [ VIT40100 ].
In practice, HMRC will look for evidence that a supply is actually being made (e.g., staff, premises, demonstrable services) before accepting the registration as valid [ VATSC06513 ].
`;

console.log(preprocessCitations(text));
