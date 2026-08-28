# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

A monorepo for travispollard.com holding three independent things:

- **Root Terraform** (`main.tf`, `modules/`) — the AWS site stack: S3 + CloudFront + Route53 + ACM.
- **`frontend/`** — the Next.js 15 site, statically exported and served from that stack.
- **`cfb/`** — a separate Python data pipeline with its own Terraform state and its own `CLAUDE.md`. Read `cfb/CLAUDE.md` before touching anything in there; its rules are stricter than the rest of the repo.

`www/` is the pre-Next.js static site. It is still tracked but dead — nothing builds or deploys it.

## Commands

Frontend (run from `frontend/`):

```bash
npm run dev            # next dev --turbopack
npm run build          # static export -> frontend/out, then next-sitemap (postbuild)
npm run lint
npx playwright test                                   # all browsers
npx playwright test tests/visitor-counter.spec.ts     # one file
npx playwright test --project=chromium                # one browser
```

Terraform (run from repo root):

```bash
./download-tfvars.sh   # terraform.tfvars is gitignored; pull it from SSM first
terraform init
terraform plan
./upload-tfvars.sh     # push local tfvars changes back to SSM
```

Both tfvars scripts use the `tp-site` AWS profile and the SSM parameter `/projects/cloudresume/terraform/tfvars`.

**Account `679878703800`, profile `tp-site`.** Everything is `us-east-1` except the Terraform state bucket
`travispollard.com-tf-state`, which is `us-west-2`. `AWS_PROFILE` is not set for you — export it per shell.
A second account, `100611042748`, is reachable under the similarly-named `jtravisp` profile; commands aimed
at it succeed and return nothing rather than erroring, so confirm with
`aws sts get-caller-identity --profile tp-site --query Account --output text` before believing an empty
result.

## Architecture

**Build/serve path.** `next.config.ts` sets `output: 'export'` and `trailingSlash: true`, so the site is fully static: no API routes, no server components with server work, no ISR. Anything dynamic must be a client component fetching at runtime. The export lands in `frontend/out/` and is uploaded to the S3 bucket, which CloudFront reads through the **S3 website endpoint as a custom origin** (`http-only`), not an OAC/REST origin — that is why the bucket policy is public-read and why routing depends on `aws_s3_bucket_website_configuration` rather than CloudFront.

**Terraform wiring.** `main.tf` composes four local modules; the dependency order is implicit through outputs: `acm` emits DNS validation records that `route53` creates, `cloudfront` consumes the cert ARN and the S3 bucket name, and `route53` points aliases at the distribution. State lives in the S3 backend `travispollard.com-tf-state` (us-west-2) while resources default to us-east-1 — ACM for CloudFront must stay in us-east-1.

**Visitor counter.** `components/VisitorCounter.tsx` fetches a hardcoded API Gateway URL. The Lambda and API Gateway behind it are **not** in this repo; they were created outside this Terraform. `tests/visitor-counter.spec.ts` hits that live endpoint, so the Playwright suite requires network and tests production, not a local build.

**Theming.** daisyUI themes are declared in `app/globals.css` via `@plugin "daisyui"`. `HeaderWithTheme.tsx` sets `data-theme` on `<html>` and persists it to `localStorage`, restoring it in a `useEffect` to avoid a hydration mismatch. The css block declares more themes than the selector exposes — add to both when adding one.

**CI.** `buildspec.yml` is a CodeBuild spec: `npm ci` in `frontend/`, build, then Playwright smoke tests post-build, artifacting `frontend/out`. The CodePipeline that runs it was created in the console and is not in Terraform, and it does **not** invalidate CloudFront — after a deploy, the invalidation is manual.

## Gotchas

- `terraform.tfvars` and all `*.tfvars` are gitignored. A plan without running `./download-tfvars.sh` will prompt for every variable.
- CloudFront aliases are hardcoded in `modules/cloudfront/main.tf`, not variables.
- `next-sitemap` runs at postbuild and writes `sitemap*.xml` / `robots.txt`; do not hand-edit the generated copies in `public/` or `out/`.
- `cfb/terraform` has state separate from the root. Never reference root state from it — the seam is SSM parameters under `/travispollard/cdn/`.
