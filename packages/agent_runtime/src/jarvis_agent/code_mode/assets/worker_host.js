import { Worker } from "node:worker_threads";
import { resolve } from "node:path";

let inputStr = "";
process.stdin.setEncoding("utf8");

process.stdin.on("data", (chunk) => {
  inputStr += chunk;
});

process.stdin.on("end", () => {
  if (!inputStr.trim()) return;
  try {
    const msg = JSON.parse(inputStr);
    
    // Revive snapshotBytes from base64
    if (msg.kind === "resume" && typeof msg.snapshotBytes === "string") {
      msg.snapshotBytes = Buffer.from(msg.snapshotBytes, "base64");
    }

    const workerPath = resolve(import.meta.dirname, "worker.mjs");
    const worker = new Worker(workerPath, {
      workerData: msg,
    });

    worker.on("message", (resultMsg) => {
      // Convert snapshotBytes to base64 before JSON stringify
      if (resultMsg.status === "waiting" && resultMsg.snapshotBytes) {
        resultMsg.snapshotBytes = Buffer.from(resultMsg.snapshotBytes).toString("base64");
      }
      process.stdout.write(JSON.stringify(resultMsg) + "\n");
    });

    worker.on("error", (err) => {
      console.error("Worker error:", err);
      process.exit(1);
    });

    worker.on("exit", (code) => {
      process.exit(code);
    });

  } catch (err) {
    console.error("Failed to parse message from host:", err);
    process.exit(1);
  }
});
