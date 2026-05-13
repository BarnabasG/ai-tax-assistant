from bs4 import BeautifulSoup
import re

html = """
<p class="MsoNormal"><span>This option would apply for:</span></p>
<p>
</p>
<p class="MsoNormal"><span><span>·<span>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
</span></span></span><span>company cars:</span></p>
<p>
</p>
<p class="MsoNormal"><span><span>·<span>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
</span></span></span><span>stock in trade cars; and</span></p>
<p>
</p>
<p class="MsoNormal"><span><span>·<span>&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
</span></span></span><span>taxis and private hire cars</span></p>
<p>
</p>
<p class="MsoNormal"><span>that are used for private as well as business
purposes.</span></p>
"""

def strip_html_new(html: str) -> str:
    if not html:
        return ""
    
    html = html.replace('\u00b7', '-')
    soup = BeautifulSoup(html, "html.parser")
    
    for br in soup.find_all("br"):
        br.replace_with("\n")
        
    for tag in soup.find_all(["p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "tr"]):
        tag.insert_after("\n\n")
        
    text = soup.get_text(separator=" ")
    
    text = re.sub(r'[ \t\xa0]+', ' ', text)
    
    blocks = text.split("\n\n")
    clean_blocks = []
    for block in blocks:
        block = block.replace("\n", " ").strip()
        if block:
            clean_blocks.append(block)
            
    text = "\n\n".join(clean_blocks)
    text = re.sub(r'^-\s*', '- ', text, flags=re.MULTILINE)
    
    return text

print("--- NEW ---")
print(strip_html_new(html))
