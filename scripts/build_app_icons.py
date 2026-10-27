"""Build browser/PWA icon files from the selected Reconciled artwork (Pillow)."""
from pathlib import Path
from PIL import Image
root=Path(__file__).resolve().parents[1]
source=Image.open(root/'assets/branding/sidecar-reconciled.png').convert('RGBA')
static=root/'sidecar/static'
for size in (16,32,180,192,512):
    source.resize((size,size),Image.Resampling.LANCZOS).save(static/f'icon-{size}.png',optimize=True)
source.save(static/'favicon.ico',format='ICO',sizes=[(16,16),(32,32),(48,48)])
maskable=Image.new('RGBA',(512,512),'#142a3a')
art=source.resize((400,400),Image.Resampling.LANCZOS)
maskable.alpha_composite(art,(56,56))
maskable.convert('RGB').save(static/'icon-maskable-512.png',optimize=True)
