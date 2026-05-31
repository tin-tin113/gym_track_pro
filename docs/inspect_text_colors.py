import pypdf

reader = pypdf.PdfReader("docs/Capstone Template Manuscript (2026).docx.pdf")

color_map = {
    ".0902 .1686 .302": "Dark Navy (#172B4D)",
    ".3569 .6078 .8353": "Steel Blue (#5B9BD5)",
    ".7725 .349 .0667": "Brick Red (#C55911)",
    ".9059 .902 .902": "Light Gray (#E7E6E6)",
    ".0196 .3882 .7569": "Link Blue (#0563C1)"
}

print("Searching for color usages with text...")

for idx, page in enumerate(reader.pages):
    contents = page.get("/Contents")
    if not contents:
        continue
    contents_obj = contents.get_object()
    if isinstance(contents_obj, pypdf.generic.ArrayObject):
        data = b"".join([c.get_object().get_data() for c in contents_obj])
    elif hasattr(contents_obj, "get_data"):
        data = contents_obj.get_data()
    else:
        continue
        
    decoded = data.decode("utf-8", errors="ignore")
    # Let's see if this page has any target colors
    found_colors = []
    for c_code, c_name in color_map.items():
        if c_code in decoded:
            found_colors.append(c_name)
            
    if found_colors:
        print(f"\n--- Page {idx+1} has colors: {', '.join(found_colors)} ---")
        # Let's extract some text from this page to see the context
        text = page.extract_text()
        lines = text.split("\n")
        print("Page text snippet (first 10 lines):")
        for line in lines[:10]:
            print(f"  {line.strip()[:80]}")
        # Stop printing after a few pages to avoid clutter
        if idx > 40:
            print("... and more pages")
            break
