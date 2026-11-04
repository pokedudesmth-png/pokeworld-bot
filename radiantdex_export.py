import io, os, re, json, zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests
from PIL import Image

API="https://pokeapi.co/api/v2"
OUT="RADIANTDEX_Artwork"
ZIP="RADIANTDEX_Radiant_Artwork.zip"
s=requests.Session()
s.headers["User-Agent"]="RADIANTDEX artwork exporter"

def purple(r,g,b):
    y=(.2126*r+.7152*g+.0722*b)/255
    stops=[(0,(25,3,48)),(.28,(83,13,139)),(.58,(157,42,226)),(.82,(211,126,255)),(1,(255,232,255))]
    for i in range(len(stops)-1):
        p,a=stops[i];q,c=stops[i+1]
        if p<=y<=q:
            t=(y-p)/(q-p)
            return tuple(round(a[k]+(c[k]-a[k])*t) for k in range(3))
    return stops[-1][1]

def get(url):
    r=s.get(url,timeout=30);r.raise_for_status();return r

def job(entry):
    try:
        p=get(entry["url"]).json()
        other=p.get("sprites",{}).get("other",{})
        url=((other.get("official-artwork") or {}).get("front_default")
             or (other.get("home") or {}).get("front_default")
             or p.get("sprites",{}).get("front_default"))
        if not url:return ("skip",entry["name"])
        im=Image.open(io.BytesIO(get(url).content)).convert("RGBA")
        px=im.load()
        for y in range(im.height):
            for x in range(im.width):
                r,g,b,a=px[x,y]
                if a:px[x,y]=(*purple(r,g,b),a)
        name=re.sub(r"[^a-zA-Z0-9._-]+","_",p["name"])
        fn=f'{p.get("id",0):04d}_{name}.png'
        im.save(os.path.join(OUT,fn),optimize=True)
        return ("ok",fn)
    except Exception as e:return ("error",entry["name"]+": "+str(e))

def main():
    os.makedirs(OUT,exist_ok=True)
    print("Getting Pokémon and form list from PokéAPI...")
    entries=get(API+"/pokemon?limit=100000&offset=0").json()["results"]
    print(f"Found {len(entries)} entries. Downloading artwork; this may take a while.")
    counts={"ok":0,"skip":0,"error":0};errors=[]
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures=[pool.submit(job,e) for e in entries]
        for n,f in enumerate(as_completed(futures),1):
            kind,value=f.result();counts[kind]+=1
            if kind=="error":errors.append(value)
            if n%25==0 or n==len(entries):
                print(f"{n}/{len(entries)} | saved {counts['ok']} | unavailable {counts['skip']} | errors {counts['error']}")
    with open(os.path.join(OUT,"export_report.json"),"w",encoding="utf-8") as f:
        json.dump({"entries":len(entries),**counts,"errors":errors},f,indent=2)
    print("Packaging PNG files...")
    with zipfile.ZipFile(ZIP,"w",zipfile.ZIP_DEFLATED) as z:
        for fn in os.listdir(OUT):
            path=os.path.join(OUT,fn)
            if os.path.isfile(path):z.write(path,os.path.join(OUT,fn))
    print("Done! Created "+os.path.abspath(ZIP))
    print("Some forms may not have separate artwork available from PokéAPI.")

if __name__=="__main__":main()
