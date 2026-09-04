// Local-only E2E helper: serves frontend/dist and proxies /api/* to a
// locally-running uvicorn API (start it with:
//   OPENOJ_PROBLEMS_DIR=../openoj-problems/problems \
//   OPENOJ_DATA_DIR=/tmp/openoj-e2e-data \
//   uvicorn app.main:app --port 8010    (from api/)
// ). No external deps.
import http from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join } from "node:path";
import { fileURLToPath } from "node:url";

const DIST = fileURLToPath(new URL("../frontend/dist", import.meta.url));
const API_HOST = "127.0.0.1";
const API_PORT = 8010;

const types = { ".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon", ".woff2": "font/woff2" };

http.createServer(async (req, res) => {
  if (req.url.startsWith("/api/")) {
    const upstream = http.request({ host: API_HOST, port: API_PORT, path: req.url.replace(/^\/api/, ""), method: req.method, headers: { ...req.headers, host: `${API_HOST}:${API_PORT}` } }, (proxyRes) => {
      res.writeHead(proxyRes.statusCode, proxyRes.headers);
      proxyRes.pipe(res);
    });
    upstream.on("error", () => {
      res.writeHead(502);
      res.end("api unreachable");
    });
    req.pipe(upstream);
    return;
  }
  const path = req.url === "/" ? "/index.html" : req.url.split("?")[0];
  try {
    const body = await readFile(join(DIST, path));
    res.writeHead(200, { "content-type": types[extname(path)] ?? "application/octet-stream" });
    res.end(body);
  } catch {
    const body = await readFile(join(DIST, "index.html"));
    res.writeHead(200, { "content-type": "text/html" });
    res.end(body);
  }
}).listen(4174, () => console.log("e2e server on http://127.0.0.1:4174"));
