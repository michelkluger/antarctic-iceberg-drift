"""Render one PNG per frame of docs/index.html with Playwright, in a portrait layout for video.

Same method as sao-paulo-em-movimento/scripts/export.py: hide the controls, seek the page through its
window.__seek hook, screenshot, and split frames across workers (frame i goes to worker i % K).
Frames already on disk are skipped, so an interrupted run resumes.
Usage: python export.py docs/index.html frames dark <days_per_frame> <worker> <workers>
"""
import sys, os
from playwright.sync_api import sync_playwright

src, out, theme = os.path.abspath(sys.argv[1]), sys.argv[2], sys.argv[3]
step = float(sys.argv[4])  # simulated days per frame
k, K = int(sys.argv[5]), int(sys.argv[6])  # this worker / workers
HOLD = 60  # extra frames on the final date: 2 s at 30 fps
# Portrait card: title, map, date, quadrant legend in two columns, highlighted families, credits.
# Every block gets a fixed height so all frames share one size.
VIDEO_CSS = """
.controls,.about,.lede,#blkSize,#blkStates,#blkDisplay,#blkHighlight .note,.sub2,.tip{display:none!important}
.vidsub,.vidcredit{display:block!important}
body{padding:20px 18px 18px!important}
.app{gap:12px!important}
.stage{gap:12px!important}
.panel{max-width:none!important;gap:10px!important}
.readout{padding-bottom:8px!important}
.legend{grid-template-columns:1fr 1fr;gap:0 6px!important}
.row{padding:4px 4px 5px!important}
.row:hover{background:none!important}
.now{height:2.9em;overflow:hidden}
"""
os.makedirs(out, exist_ok=True)
with sync_playwright() as p:
    b = p.chromium.launch(channel=os.environ.get("PW_CHANNEL", "msedge"))
    pg = b.new_page(viewport={"width": 560, "height": 1400}, device_scale_factor=2, color_scheme=theme, reduced_motion="reduce")
    pg.goto("file:///" + src.replace("\\", "/"))
    pg.wait_for_function("window.__ready === true", timeout=120_000)
    pg.add_style_tag(content=VIDEO_CSS)
    pg.wait_for_timeout(800)  # let the resize observer redraw the map at the new size
    t0, t1 = pg.evaluate("window.__range")
    box = pg.locator(".app").bounding_box()
    m = 14  # margin of page background around the card; one clip for every frame keeps sizes identical
    clip = {'x': round(box['x']) - m, 'y': round(box['y']) - m, 'width': round(box['width']) + 2 * m, 'height': round(box['height']) + 2 * m}
    n = int((t1 - t0) // step) + 1
    for i in range(k, n + HOLD, K):
        path = f"{out}/f{i:05d}.png"
        if os.path.exists(path):
            continue
        pg.evaluate(f"window.__seek({min(t0 + i * step, t1)})")
        pg.screenshot(path=path, clip=clip)
    b.close()
print("frames done", clip)
