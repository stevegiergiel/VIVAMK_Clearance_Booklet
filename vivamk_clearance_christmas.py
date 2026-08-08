#!/usr/bin/env python3
# VIVAMK CLEARANCE CHRISTMAS VERSION v1.02
# Updated: 2026-08-09 00:30 BST
# Changes: Replaced accidental placeholder with a complete standalone booklet generator.
# Changes: Missing-image products are omitted; card images enlarged; OFF badges and gaps reduced; WAS/SAVE/NOW pricing protected.
# Changes: Back cover no longer fails when an artwork PNG is missing: it uses the PNG if present, otherwise a built-in opportunity advert.

from __future__ import annotations
import argparse, csv, json, math, re, time
from dataclasses import dataclass, asdict
from pathlib import Path
from urllib.parse import urljoin
import fitz, requests
from bs4 import BeautifulSoup
from PIL import Image
from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, A5, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

VERSION='v1.02'
GREEN=colors.HexColor('#064629'); RED=colors.HexColor('#B5121B'); GOLD=colors.HexColor('#E3B341')
CREAM=colors.HexColor('#FFF7E2'); INK=colors.HexColor('#202020'); LIGHT=colors.HexColor('#FFF9EA')
UA='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36'
DEFAULTS={
 'source_price_file':'Christmas_Sale_GBP1.pdf','output_folder':'christmas_booklet_output','cards_per_page':6,
 'request_delay_seconds':0.30,'base_url':'https://stevegiergiel.vivamknetwork.co.uk/',
 'search_url_template':'https://stevegiergiel.vivamknetwork.co.uk/catalogsearch/result/?q={sku}',
 'order_url':'https://stevegiergiel.vivamknetwork.co.uk/clearance/christmas-sale.html',
 'phone':'0771 304 5597','email':'steve@ezeget.com','opportunity_url':'https://ezeget.com',
 'opportunity_phone':'07429 21 21 40','opportunity_art_file':'opportunity_back_cover.png','ezeget_logo_file':'ezeget_logo.png'}
MONEY=r'£\s*\d+(?:\.\d{2})?'; ROW_RE=re.compile(rf'^\s*(\d{{4,8}})\s+(.+?)\s+({MONEY})\s+({MONEY})\s+({MONEY})\s+(\d{{1,3}}%)\s*$')

@dataclass
class SaleRow:
 sku:str; product:str; was:str; now:str; saving:str; percent:str
 product_url:str=''; description:str=''; image_url:str=''; image_file:str=''

def cfgload(path:Path):
 c=dict(DEFAULTS)
 if path.exists(): c.update(json.loads(path.read_text(encoding='utf-8')))
 return c

def clean(s): return re.sub(r'\s+',' ',(s or '').replace('\u00a0',' ').replace('–','-').replace('—','-')).strip()

def extract_rows(pdf):
 doc=fitz.open(pdf); rows=[]
 for page in doc:
  for raw in page.get_text('text').splitlines():
   m=ROW_RE.match(clean(raw))
   if m: rows.append(SaleRow(*[clean(x) for x in m.groups()]))
 if not rows:
  for page in doc:
   lines={}
   for w in page.get_text('words'): lines.setdefault(round(w[1]/3)*3,[]).append(w)
   for k in sorted(lines):
    m=ROW_RE.match(clean(' '.join(w[4] for w in sorted(lines[k],key=lambda q:q[0]))))
    if m: rows.append(SaleRow(*[clean(x) for x in m.groups()]))
 seen=set(); out=[]
 for r in rows:
  if r.sku not in seen: seen.add(r.sku); out.append(r)
 if not out: raise RuntimeError('No sale rows could be read from the source PDF.')
 return out

def sess():
 s=requests.Session(); s.headers.update({'User-Agent':UA,'Accept-Language':'en-GB,en;q=0.9'}); return s

def soupget(s,url):
 r=s.get(url,timeout=35); r.raise_for_status(); return BeautifulSoup(r.text,'html.parser')

def txt(soup, sels):
 for sel in sels:
  n=soup.select_one(sel)
  if n and clean(n.get_text(' ',strip=True)): return clean(n.get_text(' ',strip=True))
 return ''

def attr(soup, choices):
 for sel,a in choices:
  n=soup.select_one(sel)
  if n and n.get(a): return clean(str(n.get(a)))
 return ''

def save_image(s,url,dst):
 try:
  r=s.get(url,timeout=35); r.raise_for_status()
  if len(r.content)<500: return False
  dst.write_bytes(r.content)
  with Image.open(dst) as im: im.verify()
  return True
 except Exception: dst.unlink(missing_ok=True); return False

def enrich(rows,cfg,cache,refresh=False):
 cache.mkdir(parents=True,exist_ok=True); s=sess(); out=[]
 for i,row in enumerate(rows,1):
  meta=cache/f'{row.sku}.json'
  if meta.exists() and not refresh:
   try:
    d=json.loads(meta.read_text(encoding='utf-8'))
    for k,v in d.items():
     if hasattr(row,k): setattr(row,k,v)
    if row.image_file and Path(row.image_file).exists(): out.append(row); print(f'[{i:02d}/{len(rows):02d}] {row.sku} cached'); continue
   except Exception: pass
  print(f'[{i:02d}/{len(rows):02d}] {row.sku} {row.product}')
  try:
   search=soupget(s,cfg['search_url_template'].format(sku=row.sku))
   link=search.select_one('a.product-item-link') or search.select_one('.product-item-name a')
   if not link or not link.get('href'): print('  SKIP: product page not found'); continue
   row.product_url=urljoin(cfg['base_url'],link['href']); p=soupget(s,row.product_url)
   title=txt(p,['h1.page-title span','h1.page-title','h1']); row.product=title or row.product
   row.description=txt(p,['.product.attribute.overview .value','.product.attribute.description .value','[itemprop="description"]'])
   row.image_url=attr(p,[('meta[property="og:image"]','content'),('meta[name="twitter:image"]','content'),('.gallery-placeholder img','src'),('.product.media img','src')])
   if not row.image_url: row.image_url=attr(search,[('img.product-image-photo','src'),('img.product-image-photo','data-src')])
   if row.image_url:
    row.image_url=urljoin(cfg['base_url'],row.image_url); ext=Path(row.image_url.split('?')[0]).suffix.lower()
    if ext not in {'.jpg','.jpeg','.png','.webp'}: ext='.jpg'
    dest=cache/f'{row.sku}{ext}'
    if save_image(s,row.image_url,dest): row.image_file=str(dest)
   meta.write_text(json.dumps(asdict(row),indent=2),encoding='utf-8')
   if row.image_file and Path(row.image_file).exists(): out.append(row)
   else: print('  SKIP: image not available')
  except Exception as e: print('  SKIP:',e)
  time.sleep(float(cfg.get('request_delay_seconds',0.3)))
 return out

def wrap(c,text,font,size,width,max_lines):
 words=clean(text).split(); lines=[]; line=''
 for word in words:
  test=(line+' '+word).strip()
  if stringWidth(test,font,size)<=width: line=test
  else:
   if line: lines.append(line)
   line=word
   if len(lines)>=max_lines: break
 if line and len(lines)<max_lines: lines.append(line)
 if lines and len(lines)==max_lines: lines[-1]=lines[-1].rstrip(' ,;:-')+'…'
 return lines

def draw_image(c,file,x,y,w,h):
 if not file or not Path(file).exists(): return
 with Image.open(file) as im: iw,ih=im.size
 sc=min(w/iw,h/ih); dw,dh=iw*sc,ih*sc
 c.drawImage(file,x+(w-dw)/2,y+(h-dh)/2,dw,dh,preserveAspectRatio=True,mask='auto')

def header(c,w,h,title='CHRISTMAS CLEARANCE',sub='Limited stocks - order your favourites quickly'):
 c.setFillColor(GREEN); c.rect(0,h-28*mm,w,28*mm,stroke=0,fill=1); c.setFillColor(RED); c.rect(0,h-2.5*mm,w,2.5*mm,stroke=0,fill=1)
 c.setFillColor(colors.white); c.setFont('Helvetica-Bold',17); c.drawCentredString(w/2,h-13.5*mm,title)
 c.setFillColor(GOLD); c.setFont('Helvetica-Bold',7.5); c.drawCentredString(w/2,h-20.5*mm,sub)

def card(c,r,x,y,w,h):
 c.setFillColor(colors.white); c.setStrokeColor(colors.HexColor('#D9CCAF')); c.roundRect(x,y,w,h,2.5*mm,stroke=1,fill=1)
 pad=2.2*mm; price_h=16.5*mm; image_h=h*.50; iy=y+h-image_h-pad; draw_image(c,r.image_file,x+pad,iy,w-2*pad,image_h)
 br=6.2*mm; bx=x+w-7.6*mm; by=y+h-7.6*mm; c.setFillColor(RED); c.circle(bx,by,br,stroke=0,fill=1); c.setFillColor(colors.white); c.setFont('Helvetica-Bold',8); c.drawCentredString(bx,by+1.2,r.percent); c.setFont('Helvetica-Bold',4.5); c.drawCentredString(bx,by-4.2,'OFF')
 ty=iy-1.8*mm; c.setFillColor(GREEN); c.setFont('Helvetica-Bold',7.4)
 for line in wrap(c,r.product,'Helvetica-Bold',7.4,w-2*pad,2): c.drawString(x+pad,ty,line); ty-=8
 if ty>y+price_h+7:
  c.setFillColor(INK); c.setFont('Helvetica',5.3); lines=wrap(c,r.description or 'Christmas clearance special - limited stock while available.','Helvetica',5.3,w-2*pad,1)
  if lines: c.drawString(x+pad,ty-1,lines[0])
 py=y+1.4*mm; ph=price_h-2*mm; c.setFillColor(LIGHT); c.setStrokeColor(colors.HexColor('#E7D7AF')); c.roundRect(x+1.3*mm,py,w-2.6*mm,ph,1.5*mm,stroke=1,fill=1)
 left=x+pad; right=x+w-pad; wy=py+ph-4.8*mm; c.setFillColor(colors.HexColor('#555555')); c.setFont('Helvetica-Bold',6); c.drawString(left,wy,'WAS')
 px=left+stringWidth('WAS ','Helvetica-Bold',6); c.setFont('Helvetica-Bold',6.8); c.drawString(px,wy,r.was); ww=stringWidth(r.was,'Helvetica-Bold',6.8); c.setStrokeColor(colors.HexColor('#777777')); c.line(px,wy+2,px+ww,wy+2)
 c.setFillColor(GREEN); c.setFont('Helvetica-Bold',5.8); c.drawRightString(right,wy,f'SAVE {r.saving}'); c.setFillColor(RED); c.setFont('Helvetica-Bold',11.8); c.drawString(left,py+2.4*mm,f'NOW {r.now}'); c.setFillColor(colors.HexColor('#555555')); c.setFont('Helvetica',5); c.drawRightString(right,py+3.1*mm,f'SKU {r.sku}')

def cover(c,w,h,cfg):
 c.setFillColor(GREEN); c.rect(0,0,w,h,stroke=0,fill=1); c.setFillColor(colors.white); c.setFont('Helvetica-Bold',25); c.drawCentredString(w/2,h-55*mm,'CHRISTMAS'); c.drawCentredString(w/2,h-72*mm,'CLEARANCE'); c.setFillColor(GOLD); c.setFont('Helvetica-Bold',13); c.drawCentredString(w/2,h-88*mm,'SPECIAL OFFERS')
 c.setFillColor(CREAM); c.roundRect(12*mm,25*mm,w-24*mm,48*mm,4*mm,stroke=0,fill=1); c.setFillColor(RED); c.setFont('Helvetica-Bold',12); c.drawCentredString(w/2,61*mm,"ONCE THEY'RE GONE, THEY'RE GONE"); c.setFillColor(GREEN); c.setFont('Helvetica-Bold',8); c.drawCentredString(w/2,47*mm,'ORDER ONLINE'); c.setFont('Helvetica',6.7); c.drawCentredString(w/2,40*mm,cfg['order_url']); c.setFont('Helvetica-Bold',8); c.drawCentredString(w/2,31*mm,f"Text {cfg['phone']} | {cfg['email']}")

def intro(c,w,h,cfg):
 c.setFillColor(CREAM); c.rect(0,0,w,h,stroke=0,fill=1); header(c,w,h,'A SPECIAL THANK YOU','For our valued customers'); c.setFillColor(colors.white); c.setStrokeColor(GOLD); c.roundRect(12*mm,30*mm,w-24*mm,h-73*mm,4*mm,stroke=1,fill=1); c.setFillColor(INK); c.setFont('Helvetica',8.5)
 lines=['Steve and Jus bring you special Christmas Offers at amazing prices.','Once they are gone they are gone, so be quick to pick your favourites.','',f"Order online: {cfg['order_url']}",f"Text orders: {cfg['phone']}",'If we may not recognise your number, include your name and postal address.','','If you are receiving this leaflet you are one of our top customers and','we thank you sincerely for your valued custom through the years.',f"Email: {cfg['email']} - include your name and postal address."]
 yy=h-55*mm
 for line in lines: c.drawCentredString(w/2,yy,line); yy-=9.5

def opportunity(c,w,h,cfg):
 art=Path(cfg.get('opportunity_art_file',''))
 if art.exists():
  with Image.open(art) as im: iw,ih=im.size
  sc=min(w/iw,h/ih); dw,dh=iw*sc,ih*sc; c.setFillColor(colors.white); c.rect(0,0,w,h,stroke=0,fill=1); c.drawImage(str(art),(w-dw)/2,(h-dh)/2,dw,dh,preserveAspectRatio=True,mask='auto'); return
 print(f'[INFO] Back-cover artwork not found: {art}; using built-in opportunity advert.')
 c.setFillColor(colors.white); c.rect(0,0,w,h,stroke=0,fill=1); c.setStrokeColor(GREEN); c.setLineWidth(2); c.rect(4*mm,4*mm,w-8*mm,h-8*mm,stroke=1,fill=0); c.setFillColor(GREEN); c.setFont('Helvetica-Bold',13); c.drawCentredString(w/2,h-27*mm,'WE ARE ALWAYS LOOKING FOR'); c.setFillColor(colors.HexColor('#165CB4')); c.setFont('Helvetica-Bold',25); c.drawCentredString(w/2,h-45*mm,'DISTRIBUTORS'); c.setFillColor(INK); c.setFont('Helvetica-Oblique',13); c.drawCentredString(w/2,h-58*mm,'All across the United Kingdom!')
 c.setFont('Helvetica',9); copy=['If you know anyone who would like to earn extra income','and build their own business with quality products people love,','we would love to hear from them!']; yy=h-92*mm
 for t in copy: c.drawCentredString(w/2,yy,t); yy-=6*mm
 c.setFillColor(colors.HexColor('#165CB4')); c.setFont('Helvetica-Bold',11); c.drawCentredString(w/2,h-126*mm,'REGISTER ONLINE'); c.setFont('Helvetica-Bold',13); c.drawCentredString(w/2,h-138*mm,cfg['opportunity_url']); c.setFillColor(INK); c.setFont('Helvetica-Bold',10); c.drawCentredString(w/2,h-157*mm,'OR CALL STEVE'); c.setFillColor(colors.HexColor('#165CB4')); c.setFont('Helvetica-Bold',14); c.drawCentredString(w/2,h-169*mm,cfg['opportunity_phone']); logo=Path(cfg.get('ezeget_logo_file',''))
 if logo.exists(): draw_image(c,str(logo),40*mm,16*mm,w-80*mm,36*mm)
 else: c.setFillColor(colors.HexColor('#1689D8')); c.setFont('Helvetica-Bold',24); c.drawCentredString(w/2,31*mm,'EzeGet'); c.setFont('Helvetica',7); c.drawCentredString(w/2,23*mm,'In business to help You Get into business')

def product_page(c,w,h,rows,page_no):
 c.setFillColor(CREAM); c.rect(0,0,w,h,stroke=0,fill=1); header(c,w,h); mx=3.5*mm; top=h-31*mm; bottom=8*mm; gap=1.8*mm; cw=(w-2*mx-gap)/2; ch=(top-bottom-2*gap)/3
 for i,r in enumerate(rows[:6]): rr,cc=divmod(i,2); card(c,r,mx+cc*(cw+gap),top-(rr+1)*ch-rr*gap,cw,ch)
 c.setFillColor(GREEN); c.setFont('Helvetica',6); c.drawCentredString(w/2,4.8*mm,f'Steve & Jus Christmas Clearance | Page {page_no}')

def make_a5(rows,out,cfg):
 w,h=A5; c=canvas.Canvas(str(out),pagesize=A5); cover(c,w,h,cfg); c.showPage(); intro(c,w,h,cfg); c.showPage(); pages=math.ceil(len(rows)/6)
 for p in range(pages): product_page(c,w,h,rows[p*6:(p+1)*6],p+3); c.showPage()
 for _ in range((-(2+pages+1))%4): c.showPage()
 opportunity(c,w,h,cfg); c.showPage(); c.save()

def impose(a5,out):
 r=PdfReader(str(a5)); n=len(r.pages)
 if n%4: raise RuntimeError('A5 page count is not a multiple of four.')
 aw,ah=landscape(A4); half=aw/2; w=PdfWriter()
 def spread(li,ri):
  p=w.add_blank_page(width=aw,height=ah)
  for idx,xoff in ((li,0),(ri,half)):
   src=r.pages[idx]; pw=float(src.mediabox.width); ph=float(src.mediabox.height); sc=min(half/pw,ah/ph); tx=xoff+(half-pw*sc)/2; ty=(ah-ph*sc)/2; p.merge_transformed_page(src,Transformation().scale(sc).translate(tx,ty))
 for s in range(n//4): spread(n-1-2*s,2*s); spread(2*s+1,n-2-2*s)
 with out.open('wb') as f: w.write(f)

def main():
 ap=argparse.ArgumentParser(); ap.add_argument('sale_pdf',nargs='?',type=Path); ap.add_argument('--config',type=Path,default=Path('booklet_config.json')); ap.add_argument('--out',type=Path); ap.add_argument('--refresh',action='store_true'); a=ap.parse_args(); cfg=cfgload(a.config); source=a.sale_pdf or Path(cfg['source_price_file'])
 if not source.exists(): ap.error(f'Source price PDF not found: {source}')
 out=a.out or Path(cfg['output_folder']); out.mkdir(parents=True,exist_ok=True); print(f'VivaMK Christmas Clearance {VERSION}'); rows=extract_rows(source); print(f'Found {len(rows)} sale products'); rows=enrich(rows,cfg,out/'cache',a.refresh); print(f'Publishing {len(rows)} products with usable images')
 if not rows: raise RuntimeError('No products with usable images remain.')
 with (out/'products_collected.csv').open('w',encoding='utf-8-sig',newline='') as f:
  wr=csv.DictWriter(f,fieldnames=list(asdict(rows[0]).keys())); wr.writeheader(); [wr.writerow(asdict(r)) for r in rows]
 a5=out/'christmas_clearance_A5_FOR_EPSON_BOOKLET.pdf'; a4=out/'christmas_clearance_A4_PREIMPOSED_NO_BOOKLET_SETTING.pdf'; make_a5(rows,a5,cfg); impose(a5,a4); print('\nDONE'); print('Epson Booklet PDF:',a5.resolve()); print('Pre-imposed A4 PDF:',a4.resolve()); print('Use Epson Booklet mode ONLY with the A5 PDF. For A4 pre-imposed output turn printer Booklet mode OFF.')

if __name__=='__main__': main()
