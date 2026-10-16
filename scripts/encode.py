"""Encode exported frames into a portrait MP4 and a GIF (method from sao-paulo-em-movimento/scripts/encode.py).

Usage: python encode.py frames out/antarctic-iceberg-drift 0x0a1118 [gif_every=3] [gif_width=540] [gif_only]
The README preview is the GIF alone, lighter:  ... encode.py frames media/preview 0x0a1118 6 380 gif_only
"""
import sys, subprocess, imageio_ffmpeg

frames, out, bg = sys.argv[1], sys.argv[2], sys.argv[3]
every = int(sys.argv[4]) if len(sys.argv) > 4 else 3
width = int(sys.argv[5]) if len(sys.argv) > 5 else 540
gif_only = len(sys.argv) > 6 and sys.argv[6] == "gif_only"
ff = imageio_ffmpeg.get_ffmpeg_exe()
pat = f"{frames}/f%05d.png"
if not gif_only:
    # MP4: 1080x1920 portrait (TikTok/Reels), 30 fps; the card is fitted inside 1000x1840 and padded with the page colour
    subprocess.run([ff, "-y", "-framerate", "30", "-i", pat,
        "-vf", f"scale=1000:1840:force_original_aspect_ratio=decrease:flags=lanczos,pad=1080:1920:(ow-iw)/2:(oh-ih)/2:color={bg},format=yuv420p",
        "-c:v", "libx264", "-crf", "18", "-preset", "slow", "-movflags", "+faststart", f"{out}.mp4"], check=True)
# GIF: every n-th frame at 20 fps (default every 3rd, 540 wide)
vf = (f"select='not(mod(n\\,{every}))',setpts=N/20/TB,scale={width}:-2:flags=lanczos,split[a][b];"
      "[a]palettegen=max_colors=192:stats_mode=diff[p];[b][p]paletteuse=dither=sierra2_4a:diff_mode=rectangle")
subprocess.run([ff, "-y", "-i", pat, "-vf", vf, "-r", "20", f"{out}.gif"], check=True)
