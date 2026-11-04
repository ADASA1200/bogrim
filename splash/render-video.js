// Renders splash/index.html frame by frame into an MP4 (requires playwright + ffmpeg).
// Usage: node splash/render-video.js [out.mp4] [seconds] [fps]
// Stills mode: STILLS=1,5,10 node splash/render-video.js outdir
const path = require("path");
const fs = require("fs");
const { spawn } = require("child_process");
const { chromium } = require("playwright");

(async () => {
  const out = process.argv[2] || path.join(__dirname, "splash.mp4");
  const seconds = Number(process.argv[3] || 18);
  const fps = Number(process.argv[4] || 30);
  const browser = await chromium.launch({ args: ["--allow-file-access-from-files"] });
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
  await page.goto("file://" + path.join(__dirname, "index.html") + "?capture");
  await page.evaluate(() => window.splashReady);
  const grab = async t => {
    const url = await page.evaluate(t => { window.renderAt(t); return document.getElementById("c").toDataURL("image/jpeg", 0.95); }, t);
    return Buffer.from(url.split(",")[1], "base64");
  };
  if (process.env.STILLS) {
    fs.mkdirSync(out, { recursive: true });
    for (const t of process.env.STILLS.split(",").map(Number)) fs.writeFileSync(path.join(out, `t${t}.jpg`), await grab(t));
  } else {
    const ff = spawn("ffmpeg", ["-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", String(fps), "-c:v", "mjpeg", "-i", "-",
      "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out], { stdio: ["pipe", "inherit", "inherit"] });
    for (let i = 0; i < seconds * fps; i++) {
      const buf = await grab(i / fps);
      if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once("drain", r));
    }
    ff.stdin.end();
    await new Promise(r => ff.on("close", r));
  }
  await browser.close();
})();
