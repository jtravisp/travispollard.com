/**
 * Markdown -> HTML for a /music post, at build time.
 *
 * GitHub-flavoured Markdown plus two container blocks:
 *
 *     :::pullquote          -> <figure class="pullquote"><blockquote>...
 *     A line worth lifting.
 *     :::
 *
 *     :::pullquote{cite="Kelela, to Zane Lowe"}
 *     Someone else's words, credited in a <figcaption> -- set large on its
 *     own, an unattributed quote reads as the reviewer's.
 *     :::
 *
 *     :::notes              -> removed from the body and returned separately,
 *     Musician's notes...      so the template can place it after the
 *     :::                      favourite-tracks list.
 *
 * An image titled "small" -- `![alt](./cover.jpg "small")` -- is capped at
 * 18rem instead of filling the column: right for album art shown alongside
 * text, where full width would make a 660px square of it.
 *
 * Raw HTML in a post is not enabled: remark-rehype drops it. Images must be
 * files in the post's folder, written relatively (`![alt](./photo.jpg)`); each
 * becomes the WebP srcset that scripts/build-music-images.mjs produced, with
 * width and height so the page does not shift as it loads. Anything else --
 * a remote image, a missing file -- fails the build and names the post.
 */

import { existsSync, readFileSync } from 'node:fs';
import { basename, join } from 'node:path';
import type { Element, Root as HastRoot } from 'hast';
import type { Root as MdastRoot, RootContent } from 'mdast';
import rehypeStringify from 'rehype-stringify';
import remarkDirective from 'remark-directive';
import remarkGfm from 'remark-gfm';
import remarkParse from 'remark-parse';
import remarkRehype from 'remark-rehype';
import { unified } from 'unified';
import { visit } from 'unist-util-visit';

export type ImageVariant = { src: string; width: number; height: number };
export type ManifestEntry = {
  width: number;
  height: number;
  variants: ImageVariant[];
  og: ImageVariant | null;
};
type Manifest = Record<string, ManifestEntry>;

const MANIFEST = join(process.cwd(), '.music', 'manifest.json');

export function readManifest(): Manifest {
  if (!existsSync(MANIFEST)) {
    throw new Error(
      '.music/manifest.json is missing: run `node scripts/build-music-images.mjs` ' +
        '(npm run build and npm run dev do it automatically).',
    );
  }
  return JSON.parse(readFileSync(MANIFEST, 'utf8'));
}

/** The processed image for a file in a post's folder, or a build error. */
export function image(manifest: Manifest, slug: string, file: string): ManifestEntry {
  const entry = manifest[`${slug}/${basename(file)}`];
  if (!entry) {
    throw new Error(
      `content/music/${slug}: image "${file}" has no processed version -- it must be a ` +
        'jpg, png, webp or avif file in the post\'s own folder.',
    );
  }
  return entry;
}

/** Container directives -> HTML; `:::notes` removed into `notes`. */
function remarkMusicBlocks(this: unknown, slug: string, notes: RootContent[]) {
  return (tree: MdastRoot) => {
    visit(tree, (node, index, parent) => {
      if (node.type === 'containerDirective') {
        if (node.name === 'notes' && parent && index !== undefined) {
          notes.push(...(node.children as RootContent[]));
          parent.children.splice(index, 1);
          return index; // revisit the node that slid into this position
        }
        if (node.name === 'pullquote') {
          const cite = node.attributes?.cite?.trim();
          node.data = { hName: 'figure', hProperties: { className: ['pullquote'] } };
          node.children = [
            { type: 'blockquote', children: node.children } as never,
            ...(cite
              ? [
                  {
                    type: 'paragraph',
                    data: { hName: 'figcaption' },
                    children: [{ type: 'text', value: cite }],
                  } as never,
                ]
              : []),
          ];
          return;
        }
        throw new Error(`content/music/${slug}: unknown block ":::${node.name}" (use pullquote or notes)`);
      }
      // remark-directive also reads ":word" inside ordinary text and lines as
      // directives. None are used here, so put the text back as written --
      // otherwise "Side A:Intro" would silently lose ":Intro".
      if ((node.type === 'textDirective' || node.type === 'leafDirective') && parent && index !== undefined) {
        const prefix = node.type === 'textDirective' ? ':' : '::';
        const inner = node.children.map((c) => ('value' in c ? String(c.value) : '')).join('');
        parent.children.splice(index, 1, {
          type: 'text',
          value: `${prefix}${node.name}${inner ? `[${inner}]` : ''}`,
        } as never);
      }
    });
  };
}

/** Relative <img> -> processed WebP srcset with intrinsic size. */
function rehypeMusicImages(slug: string, manifest: Manifest) {
  return (tree: HastRoot) => {
    visit(tree, 'element', (node: Element) => {
      if (node.tagName !== 'img') return;
      const src = String(node.properties?.src ?? '');
      if (/^([a-z]+:)?\/\//i.test(src) || src.startsWith('/')) {
        throw new Error(
          `content/music/${slug}: image "${src}" is not a file in the post's folder. ` +
            'Copy it next to index.md and write ![alt](./name.jpg).',
        );
      }
      const entry = image(manifest, slug, src.replace(/^\.\//, ''));
      const largest = entry.variants[entry.variants.length - 1];
      const middle = entry.variants[Math.min(1, entry.variants.length - 1)];
      const small = node.properties?.title === 'small';
      const { title: _title, ...rest } = node.properties ?? {};
      node.properties = {
        ...(small ? rest : node.properties),
        ...(small ? { className: ['music-img-small'] } : {}),
        src: small ? entry.variants[0].src : middle.src,
        srcSet: entry.variants.map((v) => `${v.src} ${v.width}w`).join(', '),
        sizes: small ? '18rem' : '(min-width: 768px) 42rem, 100vw',
        width: largest.width,
        height: largest.height,
        loading: 'lazy',
        decoding: 'async',
      };
    });
  };
}

function plainText(nodes: RootContent[]): string {
  const blocks: string[] = [];
  for (const node of nodes) {
    const parts: string[] = [];
    visit(node, (n) => {
      if (n.type === 'text' || n.type === 'inlineCode') parts.push(n.value);
    });
    if (parts.length) blocks.push(parts.join('').replace(/\s+/g, ' ').trim());
  }
  return blocks.join('\n\n');
}

export type RenderedPost = {
  /** The body, without the notes block. */
  html: string;
  /** The :::notes block, or null if the post has none. */
  notesHtml: string | null;
  /** The body as plain text, for structured data. */
  text: string;
};

export function renderPost(slug: string, markdown: string, manifest = readManifest()): RenderedPost {
  const notes: RootContent[] = [];

  const parser = unified().use(remarkParse).use(remarkGfm).use(remarkDirective);
  const toHtml = unified()
    .use(remarkRehype)
    .use(rehypeMusicImages, slug, manifest)
    .use(rehypeStringify);

  const tree = parser.parse(markdown) as MdastRoot;
  const withBlocks = unified().use(remarkMusicBlocks, slug, notes).runSync(tree) as MdastRoot;

  const html = toHtml.stringify(toHtml.runSync(withBlocks) as HastRoot);
  const notesRoot: MdastRoot = { type: 'root', children: notes };
  const notesHtml = notes.length ? toHtml.stringify(toHtml.runSync(notesRoot) as HastRoot) : null;

  return { html, notesHtml, text: plainText(withBlocks.children) };
}
