# travispollard.com Infrastructure

This repository contains the Terraform configuration for deploying the infrastructure of `travispollard.com`. The infrastructure is hosted on AWS and includes resources like S3 for static site hosting, CloudFront for content delivery, Route 53 for DNS, and ACM for SSL/TLS certificates.

## Table of Contents
- [travispollard.com Infrastructure](#travispollardcom-infrastructure)
  - [Table of Contents](#table-of-contents)
  - [Project Structure](#project-structure)
  - [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Resources Created](#resources-created)
  - [Publishing a music review](#publishing-a-music-review)


## Project Structure


## Getting Started

1. Clone this repository:
   ```bash
   git clone https://github.com/jtravisp/travispollard.com.git
   cd travispollard.com
   ```

## Prerequisites

- **Terraform**: Install [Terraform](https://www.terraform.io/) (v1.0+ recommended).
- **AWS CLI**: Install the [AWS CLI](https://aws.amazon.com/cli/) and configure it with appropriate credentials.
- **Git**: Install [Git](https://git-scm.com/).
- **S3 Bucket**: Ensure an S3 bucket exists for storing the Terraform remote state (if applicable).

## Resources Created

This Terraform configuration creates the following AWS resources:

- **S3 Bucket**: Stores static website files.
- **CloudFront Distribution**: Delivers website content with caching.
- **Route 53 Records**: Manages DNS for your domain.
- **ACM Certificate**: Provides SSL/TLS for HTTPS connections.

## Publishing a music review

Album reviews live at [travispollard.com/music](https://www.travispollard.com/music/). Each review is one
Markdown file plus its images, in its own folder. The build turns it into a static page, resizes the images,
and adds it to the index, the RSS feed (`/music/feed.xml`) and the search engines' structured data. There is no
CMS and no database: publishing a review is a pull request.

### 1. Create a branch and a folder

The folder name becomes the URL, `/music/<slug>/`. Use lowercase words joined by hyphens.

```powershell
git switch main; git pull
git switch -c music/artist-album
mkdir frontend/content/music/artist-album
```

### 2. Add the images

Put them **in the post's folder**, next to `index.md`, never in `frontend/public/`.

- `cover.jpg` (or `.png`, `.webp`, `.avif`): the album cover. Required. Ideally square and 1000–1600 px;
  images are never upscaled, so a small cover publishes small (and looks soft on high-resolution screens).
- Any other images the review uses, such as another album's cover.

At build time each image becomes WebP at up to 480/960/1600 px wide, and the cover also becomes a JPEG for
link previews. Only the originals are committed; the generated files are not.

### 3. Write `index.md`

```markdown
---
title: new avatar
artist: Kelela
released: 2026
date: 2026-09-25
summary: One sentence for the index card, search results and the RSS feed.
recommended_by: BG
rating: 8
cover: cover.png
favorite_tracks:
  - idea 1
  - linknb
tags:
  - r&b
  - electronic
links:
  spotify: https://open.spotify.com/album/...
  apple_music: https://music.apple.com/us/album/...
  youtube_music: https://music.youtube.com/playlist?list=...
  bandcamp: https://....bandcamp.com/album/...
draft: true
---

The review, in Markdown.
```

| Field | Notes |
|---|---|
| `title`, `artist` | As the artist styles them (lowercase is fine). |
| `released` | The album's release year. |
| `date` | The review date, `YYYY-MM-DD`. Sets the order: newest first. |
| `summary` | One sentence. Shown on the index card, in search results and in RSS. |
| `recommended_by` | Shown as "Recommended by …". |
| `rating` | A whole number from 1 to 10. |
| `cover` | The cover's file name in this folder. |
| `favorite_tracks`, `tags` | Lists. Either may be empty (`[]`). |
| `links` | Optional. Any of `spotify`, `apple_music`, `youtube_music`, `bandcamp`; `https://` only. Shown under "Listen" as plain links, not embedded players. Drop share-tracking parameters such as `&si=…` or `?si=…`: the link works without them. |
| `draft` | `true` keeps the review out of the live site entirely; `false` publishes it. |

### 4. Formatting the review

Standard Markdown works as expected: paragraphs, `## headings`, **bold**, *italic*, `[links](https://…)`,
lists and `> block quotes`. Four extras:

- **Images:** `![Description for screen readers](./photo.jpg)` — always a file in the post's folder, written
  with `./`. Full column width by default.
- **Small images:** `![Cover of Give Up by The Postal Service](./give-up.jpg "small")` caps the image at
  about 288 px. Use it for album art beside a paragraph.
- **Pull quote:** a line lifted out and set large. Credit it when the words aren't yours, or it reads as
  yours:

  ```markdown
  :::pullquote{cite="Kelela, on “crystalize,” to Zane Lowe"}
  What if Whitney Houston sang over a Cocteau Twins piece and Phil Collins produced it?
  :::
  ```

- **Musician's notes:** write `:::notes` … `:::` anywhere in the review. It always appears in its own
  "Musician's notes" box after Favorite tracks.

Raw HTML is ignored, and any other `:::name` block fails the build, so a typo can't slip through quietly.

### 5. Preview

From `frontend/`:

```powershell
npm run dev              # http://localhost:3000/music/  (shows drafts, reloads as you save)
npm run preview:music    # http://127.0.0.1:4321/music/  (the exported site, drafts included)
```

### 6. Publish

Set `draft: false`, then from `frontend/`:

```powershell
npm run build
git add content/music/artist-album public/sitemap-0.xml
git commit -m "review: Artist, Album"
git push -u origin music/artist-album
gh pr create --fill
```

- **`npm run build` checks the review.** A problem fails the build with the file and the field named, e.g.
  `front matter "rating" must be a whole number from 1 to 10`, `names cover.jpg, which is not in the post's
  folder`, or an image that isn't in the post's folder.
- **Commit `public/sitemap-0.xml` with every new review.** The deploy ships the committed copy, so a review
  missing from it is missing from the live sitemap.

When the pull request's check passes, merge it (`gh pr merge --merge`). CodePipeline builds and deploys the site
and clears the CDN cache within a few minutes. Then open `/music/`, the review, and `/music/feed.xml` to confirm.

### Editing a published review

Same flow: branch, edit `index.md` or replace an image in the post's folder, `npm run build`, pull request,
merge. Replacing an image keeps its file name; if the name changes, update `cover:` or the `![…](./…)` that
uses it. Only commit `public/sitemap-0.xml` if the build changed it for a new review, not for date-only churn.
