import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const srcDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../src");

export async function resolve(specifier, context, nextResolve) {
  if (specifier.startsWith("@/")) {
    const target = path.join(srcDir, `${specifier.slice(2)}.ts`);
    return nextResolve(pathToFileURL(target).href, context);
  }
  return nextResolve(specifier, context);
}
