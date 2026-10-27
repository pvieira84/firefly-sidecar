"""Code-native extension icon concepts; none is activated until selected."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
root=Path(__file__).parent
S=4
navy='#263544';gold='#efa829';mint='#79d6bf';blue='#2874ad';paper='#eef4f7'
def make(kind,accent=True):
 im=Image.new('RGBA',(512,512));d=ImageDraw.Draw(im)
 def b(coords):return tuple(int(x*S) for x in coords)
 def line(points,color,width=5):d.line([(int(x*S),int(y*S)) for x,y in points],fill=color,width=width*S,joint='curve')
 def rect(coords,color,r=0):d.rounded_rectangle(b(coords),r*S,fill=color)
 def bug(x,y):
  d.ellipse(b((x-15,y-8,x-1,y+1)),fill=mint);d.ellipse(b((x+1,y-8,x+15,y+1)),fill=mint)
  line([(x,y-5),(x,y+9)],mint,5);d.ellipse(b((x-5,y+5,x+5,y+15)),fill='#e1f7a7')
 def arrow(x,y):
  line([(x,y+20),(x+20,y)],paper,6);line([(x+5,y),(x+20,y),(x+20,y+15)],paper,6)
 rect((0,0,128,128),navy,27)
 if kind=='a':
  d.polygon([(26*S,48*S),(63*S,28*S),(100*S,48*S),(63*S,69*S)],fill='#ffc765')
  d.polygon([(26*S,48*S),(63*S,69*S),(63*S,108*S),(26*S,87*S)],fill=gold)
  d.polygon([(63*S,69*S),(100*S,48*S),(100*S,87*S),(63*S,108*S)],fill='#ce8822')
  line([(63,69),(63,108)],'#ffe4a5',3);line([(44,38),(82,59),(82,73)],'#fff0bf',4)
  d.ellipse(b((78,8,122,52)),fill=blue);arrow(89,20);
  if accent:bug(27,18)
 elif kind=='b':
  bug(64,30);line([(64,48),(64,61)],mint,6)
  rect((35,59,93,105),gold,6);rect((59,59,69,78),'#ffe0a1')
  d.arc(b((43,72,85,98)),15,165,fill=navy,width=4*S)
  d.ellipse(b((82,8,122,48)),fill=blue);arrow(91,18)
 else:
  rect((28,18,89,109),paper,7);rect((39,30,77,36),gold,2)
  for y in (50,65,80):
   rect((39,y,44,y+5),gold,1);rect((50,y,77,y+4),'#8da0b0',1)
  d.ellipse(b((75,65,122,112)),fill=blue);arrow(87,78);bug(99,24)
 return im.resize((128,128),Image.Resampling.LANCZOS)
if __name__=='__main__' and '--selected' in __import__('sys').argv:
 icon=make('a',accent=False)
 for n in (16,32,48,128):icon.resize((n,n),Image.Resampling.LANCZOS).save(root/f'icon-{n}.png')
 raise SystemExit()

labels=[('a','Parcel export','A clear package, outgoing arrow and firefly.'),('b','Firefly courier','The companion carrying your Amazon order.'),('c','Orders to Sidecar','An order sheet with a prominent export arrow.')]
canvas=Image.new('RGB',(1050,430),'#f3f6f9');d=ImageDraw.Draw(canvas)
def font(n,bold=False):
 try:return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans'+('-Bold' if bold else '')+'.ttf',n)
 except OSError:return ImageFont.load_default()
d.text((30,20),'Choose an extension icon',font=font(25,True),fill=navy)
for index,(key,label,caption) in enumerate(labels):
 x=24+index*344;d.rounded_rectangle((x,70,x+328,407),radius=14,fill='white',outline='#dce5eb',width=2)
 icon=make(key);icon.save(root/f'option-{key}.png');canvas.paste(icon.resize((160,160)),(x+84,94),icon.resize((160,160)))
 d.text((x+20,275),key.upper()+' · '+label,font=font(20,True),fill=navy)
 # Explicitly wrap captions for a compact comparison.
 text={'a':['A clear package, outgoing arrow','and a small firefly accent.'],'b':['The firefly companion carrying','your Amazon order.'],'c':['An order sheet with a prominent','export arrow.']}[key]
 for j,line in enumerate(text):d.text((x+20,307+j*19),line,font=font(13),fill='#71808e')
 d.text((x+20,367),'Toolbar preview',font=font(11),fill='#71808e');small=icon.resize((24,24));canvas.paste(small,(x+143,358),small)
canvas.save(root/'icon-options.png')
