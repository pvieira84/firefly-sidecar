"""Render the parcel/smile, firefly and export badge at Chrome icon sizes."""
from pathlib import Path
from PIL import Image, ImageDraw
root=Path(__file__).parent
s=4
im=Image.new('RGBA',(128*s,128*s));d=ImageDraw.Draw(im)
def box(v):return tuple(int(x*s) for x in v)
def line(points,fill,width):d.line([(int(x*s),int(y*s)) for x,y in points],fill=fill,width=width*s,joint='curve')
d.rounded_rectangle(box((0,0,128,128)),27*s,fill='#263544')
d.rectangle(box((26,44,92,103)),fill='#efa829')
d.arc(box((48,15,72,51)),180,360,fill='#ffd986',width=7*s)
line([(48,33),(48,44)],'#ffd986',7);line([(72,33),(72,44)],'#ffd986',7)
d.arc(box((32,61,86,93)),20,155,fill='#263544',width=5*s)
line([(71,80),(83,78),(81,89)],'#263544',5)
d.ellipse(box((12,24,30,36)),fill='#9de2d5');d.ellipse(box((34,23,52,35)),fill='#9de2d5')
line([(32,27),(32,43)],'#60d7b4',8);d.ellipse(box((26,37,38,49)),fill='#d5f79d')
d.ellipse(box((75,13,121,59)),fill='#2874ad')
line([(85,43),(92,43),(92,26)],'white',5);line([(86,32),(92,26),(98,32)],'white',5);line([(92,34),(106,34)],'white',5)
for n in (16,32,48,128):im.resize((n,n),Image.Resampling.LANCZOS).save(root/f'icon-{n}.png')
