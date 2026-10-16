"""Encode exported frames into a portrait MP4 and a GIF (method from sao-paulo-em-movimento/scripts/encode.py).

Usage: python encode.py frames out/antarctic-iceberg-drift 0x0a1118 [--hold 5] [--gif-every 3] [--gif-width 540] [--gif-only]
The last frame is held for --hold seconds in both outputs.
"""
import argparse, subprocess, imageio_ffmpeg

ap = argparse.ArgumentParser()
ap.add_argument('frames'); ap.add_argument('out'); ap.add_argument('bg', help='pad colour, e.g. 0x0a1118')
ap.add_argument('--hold', type=float, default=5, help='seconds to hold the last frame')
ap.add_argument('--gif-every', type=int, default=3, help='keep every n-th frame in the GIF')
ap.add_argument('--gif-width', type=int, default=540)
ap.add_argument('--gif-only', action='store_true')
a = ap.parse_args()
ff = imageio_ffmpeg.get_ffmpeg_exe()
pat = f"{a.frames}/f%05d.png"
# hold as a frame count; in the GIF the padding goes before setpts so the cloned frames get their own timestamps
hold = lambda fps: f"tpad=stop_mode=clone:stop={round(a.hold * fps)}"
if not a.gif_only:
    # MP4: 1080x1920 portrait (TikTok/Reels), 30 fps; the card is fitted inside 1000x1840 and padded with the page colour
    subprocess.run([ff, "-y", "-framerate", "30", "-i", pat,
        "-vf", f"scale=1000:1840:force_original_aspect_ratio=decrease:flags=lanczos,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color={a.bg},{hold(30)},format=yuv420p",
        "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-movflags", "+faststart", f"{a.out}.mp4"], check=True)
# GIF: every n-th frame at 20 fps
vf = (f"select='not(mod(n\\,{a.gif_every}))',{hold(20)},setpts=N/20/TB,scale={a.gif_width}:-2:flags=lanczos,split[a][b];"
      "[a]palettegen=max_colors=192:stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle")
subprocess.run([ff, "-y", "-i", pat, "-vf", vf, "-r", "20", f"{a.out}.gif"], check=True)
