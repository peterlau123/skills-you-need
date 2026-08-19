# PPTX Text + Image Extraction (Zero-Dependency Fallback)

Worked example from a 61-slide deck downloaded from Feishu (`/tmp/feishu_ppt.pptx`).
The task: find slides about "超节点服务器 GPU与Switch PCB走线", extract their images,
and deliver them to the user.

## When to use this method

- `python-pptx` fails to import (missing pip, broken lxml in the sandbox venv)
- `lxml` has version conflicts (`cannot import name 'etree'`)
- You need to extract **images** from specific slides, not just text
- You need to **keyword-search** across all slides to find the relevant one

## Step-by-step

### 1. Unzip the PPTX

```bash
mkdir -p /tmp/pptx_extract
unzip -o /tmp/feishu_ppt.pptx -d /tmp/pptx_extract > /dev/null 2>&1
```

Key paths inside the extracted tree:
- `ppt/slides/slideN.xml` — slide content (text + shape references)
- `ppt/slides/_rels/slideN.xml.rels` — relationship file (maps rId → media path)
- `ppt/media/imageNN.png` — actual image files

### 2. Keyword-search all slides

Find which slide(s) contain your topic. Adjust the range to match the slide count
(check `ls ppt/slides/slide*.xml | wc -l`).

```python
import xml.etree.ElementTree as ET
ns_a = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
for i in range(1, 62):
    f = f'/tmp/pptx_extract/ppt/slides/slide{i}.xml'
    try:
        root = ET.parse(f).getroot()
    except:
        continue
    texts = [t.text for t in root.iter(f'{ns_a}t') if t.text]
    combined = ' '.join(texts)
    if 'PCB' in combined or '超节点服务器' in combined:
        print(f'--- Slide {i} ---')
        print(combined[:400])
```

### 3. Extract images from a specific slide

Each slide's XML references images via `<a:blip r:embed="rIdN"/>`. The `.rels` file
maps those rIds to actual media file paths.

```python
import xml.etree.ElementTree as ET, re

# Parse slide XML for image references
tree = ET.parse('/tmp/pptx_extract/ppt/slides/slide29.xml')
ns_r = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'
ns_a = '{http://schemas.openxmlformats.org/drawingml/2006/main}'
for blip in tree.getroot().iter(f'{ns_a}blip'):
    rid = blip.get(f'{ns_r}embed')
    print(f'Image rId: {rid}')

# Parse rels file to map rId → media file
with open('/tmp/pptx_extract/ppt/slides/_rels/slide29.xml.rels') as f:
    content = f.read()
    for m in re.finditer(r'Id="(.*?)".*?Target="\.\./(media/.*?)"', content):
        print(f'{m.group(1)} → {m.group(2)}')
```

Output example:
```
Image rId: rId3
Image rId: rId4
Image rId: rId5
rId3 → media/image70.png
rId4 → media/image71.png
rId5 → media/image72.png
```

### 4. Deliver images to the user

Copy the images to clean paths and deliver via `MEDIA:` prefix:

```bash
cp /tmp/pptx_extract/ppt/media/image70.png /tmp/slide29_img1.png
cp /tmp/pptx_extract/ppt/media/image71.png /tmp/slide29_img2.png
cp /tmp/pptx_extract/ppt/media/image72.png /tmp/slide29_img3.png
```

In the response, include:
```
MEDIA:/tmp/slide29_img1.png
MEDIA:/tmp/slide29_img2.png
MEDIA:/tmp/slide29_img3.png
```

### 5. When vision_analyze can't read the images

If the active model lacks vision capability, `vision_analyze` returns generic
"I cannot see images" text. In that case:
- Do NOT retry vision_analyze in a loop — it's a model limitation, not a tool failure
- Deliver the images directly via `MEDIA:` paths (the user sees them natively in Feishu)
- Explain the image content textually based on the slide's extracted text
- The slide text + your domain knowledge is usually enough to explain what the image shows

## Namespaces reference

```python
ns_a = '{http://schemas.openxmlformats.org/drawingml/2006/main}'        # text, blip, shapes
ns_r = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}'  # r:embed
ns_p = '{http://schemas.openxmlformats.org/presentationml/2006/main}'   # slide structure
```

## vs. python-pptx

| Aspect | python-pptx | ZIP+XML method |
|--------|------------|----------------|
| Dependencies | python-pptx + lxml | none (stdlib only) |
| Text extraction | `shape.text_frame.paragraphs` | `ET.iter('{ns}t')` |
| Image extraction | `shape.shape_type == 13` | `ET.iter('{ns}blip')` + rels |
| Slide search | loop over `prs.slides` | loop over `slideN.xml` files |
| Reliability | fails if lxml broken | always works |
