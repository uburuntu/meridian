/**
 * Validate all mermaid code blocks in content markdown files.
 * Run: node scripts/validate-mermaid.mjs
 * Exit code 1 if any diagram has a syntax error.
 *
 * Uses jsdom to provide the DOM environment mermaid requires.
 */
import { JSDOM } from 'jsdom';

// Set up minimal DOM before importing mermaid
const dom = new JSDOM('<!DOCTYPE html><html><body></body></html>');
global.window = dom.window;
global.document = dom.window.document;
Object.defineProperty(global, 'navigator', { value: dom.window.navigator, writable: true });
global.DOMParser = dom.window.DOMParser;
global.XMLSerializer = dom.window.XMLSerializer;

const { default: mermaid } = await import('mermaid');

import fs from 'node:fs';
import path from 'node:path';

const contentDir = path.resolve(import.meta.dirname, '../src/content');

function findMarkdownFiles(dir) {
  const results = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) results.push(...findMarkdownFiles(full));
    else if (entry.name.endsWith('.md')) results.push(full);
  }
  return results;
}

function extractMermaidBlocks(filePath) {
  const content = fs.readFileSync(filePath, 'utf8');
  const blocks = [];
  const regex = /```mermaid\n([\s\S]*?)```/g;
  let match;
  while ((match = regex.exec(content)) !== null) {
    const before = content.slice(0, match.index);
    const line = before.split('\n').length;
    blocks.push({ code: match[1].trim(), line });
  }
  return blocks;
}

mermaid.initialize({ startOnLoad: false, securityLevel: 'loose' });

const files = findMarkdownFiles(contentDir);
let errors = 0;
let total = 0;

for (const file of files) {
  const blocks = extractMermaidBlocks(file);
  if (!blocks.length) continue;

  const rel = path.relative(path.resolve(import.meta.dirname, '..'), file);
  for (const { code, line } of blocks) {
    total++;
    try {
      await mermaid.parse(code);
    } catch (e) {
      errors++;
      const msg = e.message || String(e);
      const firstLine = msg.split('\n')[0];
      console.error(`\x1b[31mERROR\x1b[0m ${rel}:${line} — ${firstLine}`);
      // Show the first few lines of the failing block for context
      const preview = code.split('\n').slice(0, 4).join('\n');
      console.error(`  ${preview.replace(/\n/g, '\n  ')}\n`);
    }
  }
}

if (errors > 0) {
  console.error(`\x1b[31m${errors} mermaid error(s)\x1b[0m in ${total} diagrams`);
  process.exit(1);
} else {
  console.log(`\x1b[32m✓\x1b[0m ${total} mermaid diagrams validated`);
}
