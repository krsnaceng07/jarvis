import { parsePatchFiles } from "@pierre/diffs";
import { preloadDiffHTML } from "@pierre/diffs/ssr";
import * as fs from "node:fs";

async function main() {
  const chunks = [];
  for await (const chunk of process.stdin) {
    chunks.push(chunk);
  }
  const inputStr = Buffer.concat(chunks).toString("utf-8");
  if (!inputStr.trim()) {
    return;
  }
  
  const req = JSON.parse(inputStr);
  const { command, args } = req;
  
  try {
    if (command === "preloadDiffHTML_before_after") {
      const { oldFile, newFile, options } = args;
      const html = await preloadDiffHTML({ oldFile, newFile, options });
      process.stdout.write(JSON.stringify({ success: true, html }) + "\n");
    } else if (command === "preloadDiffHTML_patch") {
      const { fileDiff, options } = args;
      const html = await preloadDiffHTML({ fileDiff, options });
      process.stdout.write(JSON.stringify({ success: true, html }) + "\n");
    } else if (command === "parsePatchFiles") {
      const { patch } = args;
      const files = parsePatchFiles(patch);
      process.stdout.write(JSON.stringify({ success: true, files }) + "\n");
    } else {
      process.stdout.write(JSON.stringify({ success: false, error: "Unknown command" }) + "\n");
    }
  } catch (err) {
    process.stdout.write(JSON.stringify({ success: false, error: err.message || String(err) }) + "\n");
  }
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
