"""Gesture simulation test for index.html (the hand-tracking MR version).

Feeds synthetic MediaPipe hand landmarks into the page, so the grab / pour /
peel logic can be tested without a camera.

Usage:
  pip install playwright && python -m playwright install chromium
  python -m http.server 8000          # from the repo root, in another terminal
  python tests/gesture_sim.py         # writes screenshots to tests/out/

Passes when: the cube melts, water reaches the wide bowl, a sticker comes off,
and the page throws no errors.
"""
import asyncio, os, sys
from playwright.async_api import async_playwright

URL = os.environ.get("VL_URL", "http://localhost:8000/index.html?debug")
OUT = os.path.join(os.path.dirname(__file__), "out")

# Builds 21 landmarks for a right hand. Wrist at screen (wx, wy), palm length p px,
# rotated `ang` degrees clockwise, posture 'open' | 'fist' | 'pinch'.
# Converts screen px back to normalised camera coords, matching lmToScreen()
# (object-fit: cover, mirrored front camera, assumed 1280x720 video).
GEN = """
window.mkHand=(wx,wy,p,ang,st)=>{
 const O={0:[0,0],1:[-.3,-.2],2:[-.5,-.4],3:[-.65,-.6],4:[-.75,-.8],5:[-.3,-1],9:[0,-1],13:[.25,-.95],17:[.45,-.85]};
 const open={8:[-.35,-1.9],12:[0,-2],16:[.28,-1.9],20:[.5,-1.6]},fist={8:[-.3,-.85],12:[0,-.85],16:[.25,-.8],20:[.42,-.75]};
 const tips=st==='fist'?fist:{...open}; if(st==='pinch')tips[8]=[-.75,-.82];
 const pts=[];
 for(let i=0;i<21;i++){ if(O[i]){pts[i]=O[i];continue} const f=Math.floor((i-1)/4)*4+1,t=f+3,k=i-f;
   pts[i]=[O[f][0]+(tips[t][0]-O[f][0])*k/3,O[f][1]+(tips[t][1]-O[f][1])*k/3]; }
 const a=ang*Math.PI/180,c=Math.cos(a),s=Math.sin(a),W=innerWidth,H=innerHeight,vw=1280,vh=720,
   sc=Math.max(W/vw,H/vh),ox=(W-vw*sc)/2,oy=(H-vh*sc)/2;
 return pts.map(([x,y])=>{const X=wx+(x*c-y*s)*p,Y=wy+(x*s+y*c)*p;return{x:1-(X-ox)/(vw*sc),y:(Y-oy)/(vh*sc),z:0}});
};
window.feed=(wx,wy,p,ang,st)=>__vl.processHands({landmarks:[mkHand(wx,wy,p,ang,st)],handednesses:[[{categoryName:'Right'}]]},performance.now());
"""

async def main():
    os.makedirs(OUT, exist_ok=True)
    async with async_playwright() as pw:
        b = await pw.chromium.launch(args=["--use-gl=swiftshader", "--ignore-gpu-blocklist"])
        pg = await b.new_page(viewport={"width": 1280, "height": 800})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        await pg.goto(URL); await pg.wait_for_timeout(1000)
        await pg.evaluate("document.getElementById('start').hidden=true")
        await pg.evaluate(GEN)

        async def feed(wx, wy, ang, st, n=1, wait=40, p=90):
            for _ in range(n):
                await pg.evaluate(f"feed({wx},{wy},{p},{ang},'{st}')")
                await pg.wait_for_timeout(wait)

        p = 90
        # 1. touch the cube with the index fingertip (tip sits at -0.35p, -1.9p from the wrist)
        c = await pg.evaluate("__vl.toScreen(__vl.cube)")
        await feed(c["x"] + 0.35 * p, c["y"] + 1.9 * p, 0, "open", 5)
        await feed(700, 900, 0, "open", 3); await pg.wait_for_timeout(1800)

        # 2. fist on the jug (hand centre sits at 0.04p, -0.71p from the wrist), carry it left of the bowl, turn
        j = await pg.evaluate("__vl.toScreen(__vl.jug,__vl.H/2)")
        wx, wy = j["x"] - 0.04 * p, j["y"] + 0.71 * p
        await feed(wx, wy, 0, "open", 4); await feed(wx, wy, 0, "fist", 4)
        t = await pg.evaluate("__vl.toScreen({getWorldPosition:v=>v.set(__vl.vessels[2].x-0.17,0.3,0.02)})")
        tx, ty = t["x"], t["y"] + 0.71 * p
        for i in range(1, 16):
            await feed(wx + (tx - wx) * i / 15, wy + (ty - wy) * i / 15, 0, "fist", 1, 30)
        for i in range(1, 11):
            await feed(tx, ty, 6 * i, "fist", 1, 30)
        await feed(tx, ty, 60, "fist", 30, 50)
        await pg.screenshot(path=f"{OUT}/pour.png")
        await feed(tx, ty, 60, "open", 4); await pg.wait_for_timeout(1200)

        # 3. pinch the lowest sticker (pinch point at -0.75p, -0.81p from the wrist) and pull
        s = await pg.evaluate("__vl.toScreen(__vl.holes[0].mesh)")
        sx, sy = s["x"] + 0.75 * p, s["y"] + 0.81 * p
        await feed(sx, sy, 0, "open", 3); await feed(sx, sy, 0, "pinch", 3)
        for i in range(1, 12):
            await feed(sx + 8 * i, sy + 6 * i, 0, "pinch", 1, 30)
        await feed(sx + 100, sy + 70, 0, "open", 2); await pg.wait_for_timeout(1500)
        await pg.screenshot(path=f"{OUT}/peel.png")

        st = await pg.evaluate("""({jug:__vl.getV(),vessels:__vl.vessels.map(v=>v.vol),
          open:__vl.holes.map(h=>h.open),total:__vl.getV()+__vl.vessels.reduce((a,v)=>a+v.vol,0)})""")
        await b.close()

    print(st)
    checks = {
        "no page errors": not errs,
        "cube melted": st["total"] > 0,
        "water in bowl": st["vessels"][2] > 50,
        "sticker peeled": st["open"][0],
    }
    for k, ok in checks.items():
        print(("PASS " if ok else "FAIL ") + k)
    if errs:
        print("\n".join(errs))
    sys.exit(0 if all(checks.values()) else 1)

asyncio.run(main())
