import { registerHooks } from "node:module";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import ts from "typescript";

registerHooks({
  resolve(specifier, context, nextResolve) {
    let s = specifier;
    if (s.startsWith("@/")) {
      s = pathToFileURL(path.resolve(process.cwd(), "src", s.slice(2))).href;
    }
    try {
      return nextResolve(s, context);
    } catch (err) {
      if (err && err.code === "ERR_MODULE_NOT_FOUND") {
        for (const ext of [".ts", ".tsx"]) {
          try {
            return nextResolve(s + ext, context);
          } catch {
            // Try next extension
          }
        }
      }
      throw err;
    }
  },
  load(url, context, nextLoad) {
    if (url.endsWith(".tsx")) {
      const filePath = fileURLToPath(url);
      const source = fs.readFileSync(filePath, "utf8");
      const transpiled = ts.transpileModule(source, {
        compilerOptions: {
          module: ts.ModuleKind.ESNext,
          target: ts.ScriptTarget.ES2022,
          jsx: ts.JsxEmit.ReactJSX,
        },
        fileName: filePath,
      });
      return {
        format: "module",
        shortCircuit: true,
        source: transpiled.outputText,
      };
    }
    return nextLoad(url, context);
  },
});

