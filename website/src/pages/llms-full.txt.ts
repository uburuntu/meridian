import type { APIRoute } from 'astro';
import { getCollection } from 'astro:content';
import fs from 'node:fs';
import path from 'node:path';

export const GET: APIRoute = async () => {
  const docs = await getCollection('docs');
  const enDocs = docs.filter(doc => doc.id.startsWith('en/'));
  const sorted = enDocs.sort((a, b) => (a.data.order ?? 99) - (b.data.order ?? 99));

  const sections: string[] = [
    '# Meridian Documentation',
    '',
    '> Censorship-resistant proxy deployment CLI.',
    '> Source: https://getmeridian.org',
    '',
  ];

  for (const doc of sorted) {
    const filePath = path.resolve(`src/content/docs/${doc.id}.md`);
    try {
      const raw = fs.readFileSync(filePath, 'utf-8');
      let content = raw.replace(/^---[\s\S]*?---\n/, '');
      // Rewrite internal doc links to markdown endpoints for LLM consumers
      content = content.replace(/\(\/docs\//g, '(/md/');
      sections.push(`---\n\n# ${doc.data.title}\n\n${content.trim()}\n`);
    } catch {
      sections.push(`---\n\n# ${doc.data.title}\n\n(Content not available)\n`);
    }
  }

  return new Response(sections.join('\n'), {
    headers: { 'Content-Type': 'text/plain; charset=utf-8' },
  });
};
