import type { APIRoute, GetStaticPaths } from 'astro';
import { getCollection } from 'astro:content';
import fs from 'node:fs';
import path from 'node:path';

export const getStaticPaths: GetStaticPaths = async () => {
  const docs = await getCollection('docs');
  return docs.map((entry) => ({
    params: { slug: entry.id },
    props: { entry },
  }));
};

export const GET: APIRoute = async ({ props }) => {
  const { entry } = props;

  const filePath = path.resolve(`src/content/docs/${entry.id}.md`);
  let content = '';
  try {
    const raw = fs.readFileSync(filePath, 'utf-8');
    content = raw.replace(/^---[\s\S]*?---\n/, '').trim();
    // Rewrite internal doc links to markdown endpoints for LLM consumers
    content = content.replace(/\(\/docs\//g, '(/md/');
  } catch {
    content = `(Content not available)`;
  }

  const body = `# ${entry.data.title}\n\n${entry.data.description ? `> ${entry.data.description}\n\n` : ''}${content}\n`;

  return new Response(body, {
    headers: { 'Content-Type': 'text/markdown; charset=utf-8' },
  });
};
