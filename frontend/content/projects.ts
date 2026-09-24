/**
 * One source of truth for project copy.
 *
 * The home page's featured cards and the /projects terminal blocks used to be
 * two hand-maintained lists, which is how the projects page ended up claiming a
 * CI/CD pipeline the repo had not used for months. They now read the same
 * objects: `summary` and `tags` render the card, `items` render the terminal
 * lines, and both come from the same entry.
 *
 * `TODO(travis)` markers are load-bearing. Anything here that could not be
 * verified carries one, and it renders in development rather than hiding in a
 * comment nobody opens -- a claim nobody can check is worse than a visibly
 * unfinished one.
 *
 * They do not ship. A line carrying one is dropped from a production build --
 * the whole line, not just the marker, because "X - TODO(travis): confirm"
 * means X is the thing unconfirmed. `scripts/check-no-todos.mjs` fails the
 * build if a marker reaches the export anyway. Answering it here is still the
 * only way to make the line real.
 *
 * An entry marked `unverified` goes further: in production it renders its
 * title and links and nothing else, because its summary and tags are claims
 * too.
 */

export type ProjectLink = {
  label: string;
  /** Rendered without the scheme; `href` is used as given. */
  url: string;
};

export type Project = {
  /** Stable key, also the React key. */
  id: string;
  /** Terminal heading on /projects. */
  title: string;
  /** Short form for the home page card, where width is tight. */
  cardTitle: string;
  /** One line. Home card only. */
  summary: string;
  /** 3-5, home card only. */
  tags: string[];
  links: ProjectLink[];
  /** Terminal body lines on /projects. */
  items: string[];
  /** Surfaced as a card on the home page, in this file's order. */
  featured?: boolean;
  /**
   * The whole entry is unconfirmed. Production renders the title and links
   * only; development renders everything so the claims stay in front of
   * whoever can check them.
   */
  unverified?: boolean;
};

export const cloudAiProjects: Project[] = [
  {
    id: 'ncoer-writer',
    title: 'NCOER Writer - Multi-Agent Army Evaluation Drafting',
    cardTitle: 'NCOER Writer',
    summary:
      'Multi-agent pipeline that turns raw performance notes into regulation-compliant Army NCOER bullets.',
    tags: ['Bedrock', 'AgentCore', 'Strands', 'Go', 'Cognito'],
    links: [{ label: 'live', url: 'https://ncoer.travispollard.com' }],
    featured: true,
    // Supplied verbatim by Travis on 2026-09-24, corrected the same day to
    // what is deployed. Reword only with him.
    items: [
      'Turns raw performance notes into regulation-compliant NCOER bullet drafts for Army Band NCOs across DA Form 2166-9-1 and 2166-9-2 formats',
      'Accepts pasted counseling notes, previous evaluation bullets, or raw performance dumps',
      'Python agents built with Strands on Amazon Bedrock: an intake agent that identifies missing detail and prompts for context, and a drafting agent grounded in DA Pam 623-3 and an Army Band MOS translation table',
      'Drafting pipeline is constrained from inventing statistics or accomplishments—prompts require verification for unstated metrics',
      'Go-based structural validator enforces Army Evaluation Entry System (EES) rules, including bullet counts per block and character-level formatting, integrated via an MCP server behind AgentCore Gateway',
      'Sign-in federated via Google through AWS Cognito, with access controlled via a DynamoDB allowlist checked during session creation',
      'Stateless request architecture ensures no Soldier performance data is persisted after session termination',
      'Static Next.js frontend hosted on S3 and CloudFront, deployed via GitHub Actions over OIDC and provisioned with Terraform',
    ],
  },
  {
    id: 'cfb-forecast',
    title: 'CFB Forecast - An Elo Model That Scores Itself',
    cardTitle: 'CFB Forecast',
    summary:
      'Predicts every FBS game each week, then grades itself against the betting market in public.',
    tags: ['Python', 'Elo', 'S3', 'GitHub Actions', 'Terraform'],
    links: [
      { label: 'live', url: 'https://travispollard.com/cfb' },
      { label: 'repo', url: 'https://github.com/jtravisp/travispollard.com' },
    ],
    featured: true,
    items: [
      'Predicts every FBS game each week, writes the forecast to immutable storage before kickoff, and scores it against both the result and the closing betting line',
      'Elo model seeded from Sagarin preseason ratings; the rating scale, K, and the margin-of-victory floor were fitted by grid search over a 2015-2025 backfill rather than picked by convention',
      'Python pipeline ingests the CollegeFootballData API and parses the Sagarin ratings page into timestamped, immutable raw snapshots, with a manifest written beside every object',
      'Validation failures raise rather than log-and-continue, an unmapped team name is an error rather than a fuzzy match, and every published mean carries its own denominator - a silently dropped row is the one failure the whole design exists to prevent',
      'Published JSON lands in a dedicated S3 bucket and is served through a second CloudFront origin behind an Origin Access Control, to static Next.js pages on this site',
      'Scheduled GitHub Actions assume a publisher role by OIDC with no stored keys, the vendor API key lives in SSM Parameter Store, and the pipeline keeps its Terraform state isolated from the site stack',
      'A per-run API call budget is enforced inside the client, with mutation tests proving the assertions catch a guard that counts after sending rather than before',
    ],
  },
  {
    id: 'near-mint-radar',
    title: 'Near Mint Radar - Trading Card Price Tracker',
    cardTitle: 'Near Mint Radar',
    summary:
      'Watchlist a trading card with a target price and get an email when the market drops below it.',
    tags: ['FastAPI', 'Lambda', 'DynamoDB', 'EventBridge', 'Terraform'],
    links: [
      { label: 'live', url: 'https://nearmintradar.com' },
      { label: 'app repo', url: 'https://github.com/jtravisp/magictracker-app' },
      { label: 'infra repo', url: 'https://github.com/jtravisp/magictracker-infra' },
    ],
    featured: true,
    items: [
      'Built a trading card price tracker - users watchlist cards with a target price and get an email when the price drops',
      'Next.js frontend on AWS Amplify with Google OAuth',
      'Python FastAPI backend running on Lambda behind an API Gateway HTTP API',
      'Single-table DynamoDB design, S3 price cache, and an EventBridge-scheduled daily polling job',
      'SES alert emails, Secrets Manager for credentials, and GitHub OIDC for keyless CI/CD',
      'Sending domain authenticated for SES with DKIM and DMARC, and moved out of the sandbox to production access - TODO(travis): confirm',
      'Entire stack provisioned with Terraform',
    ],
  },
  {
    id: 'privatepaste',
    title: 'PrivatePaste - Zero-Knowledge Encrypted Vault (archived)',
    cardTitle: 'PrivatePaste',
    summary: 'An encrypted text vault whose server only ever stores ciphertext.',
    tags: ['Go', 'Web Crypto', 'DynamoDB', 'Fargate', 'Terraform'],
    links: [{ label: 'repo', url: 'https://github.com/jtravisp/privatepaste' }],
    items: [
      'Built an encrypted text vault where the server only ever stores ciphertext and can never read a paste',
      'AES-256-GCM encryption in the browser via the Web Crypto API - the key lives in the URL fragment and is never transmitted',
      'Go standard-library HTTP server with the frontend embedded in the binary using go:embed',
      'DynamoDB with native TTL powering burn-after-read and timed paste expiry',
      'Owner tokens stored only as SHA-256 hashes; request bodies capped at 512KB at the HTTP layer',
      'Containerized on ECS Fargate behind an ALB, provisioned with Terraform using S3 remote state',
      'Taken down after tracing the idle cost: an ALB and a warm Fargate task bill by the hour whether or not anyone pastes anything, which is the wrong shape for traffic that arrives in bursts. The source is still public',
    ],
  },
  {
    id: 'lone-star-ampa',
    title: 'The Lone Star AMPA - 36th Infantry Division Band',
    cardTitle: 'The Lone Star AMPA',
    summary: 'Study portal for the Army Musician Proficiency Assessment.',
    tags: ['Next.js', 'MDX', 'Tailwind', 'Cloudflare Pages'],
    links: [
      { label: 'live', url: 'https://lonestarampa.com' },
      { label: 'repo', url: 'https://github.com/jtravisp/lonestarampa.com' },
    ],
    items: [
      'Built a study portal for the Army Musician Proficiency Assessment used by soldiers preparing for evaluation',
      'Next.js static export with an MDX content pipeline so instrument guides are authored in Markdown',
      'Per-instrument tabbed guides, rubric breakdowns, and downloadable Army regulation PDFs',
      'Styled with Tailwind CSS and deployed on Cloudflare Pages',
    ],
  },
  {
    id: 'travispollard-com',
    title: 'travispollard.com - This Site',
    cardTitle: 'travispollard.com',
    summary: 'Static Next.js on S3 and CloudFront, gated by CI before it can reach production.',
    tags: ['Next.js', 'Terraform', 'CloudFront', 'Lambda', 'Playwright'],
    links: [{ label: 'repo', url: 'https://github.com/jtravisp/travispollard.com' }],
    items: [
      'Next.js static export served from S3 through CloudFront, with Route 53 and an ACM certificate, provisioned end to end by Terraform modules for s3, cloudfront, acm, and route53',
      'GitHub Actions gates every pull request: typecheck, lint, a full static export, and the Playwright suite across Chromium and Firefox - pinned to UTC and to the same Node version the deploy builds with, because a gate running a different environment from the deploy has a gap in it',
      'A merge to main triggers CodePipeline: CodeBuild runs the same suite, the export deploys to S3, and a final stage invalidates the CloudFront distribution',
      'Visitor counter is a Python Lambda behind API Gateway incrementing a DynamoDB item',
      'A second CloudFront origin serves the football pipeline JSON from its own bucket over an Origin Access Control, with SSM parameters as the only seam between the two Terraform states',
    ],
  },
  {
    id: 'moodle-containerization',
    title: 'Moodle Containerization - Internal LMS',
    cardTitle: 'Moodle Containerization',
    summary: 'Replaced deprecated upstream images with a purpose-built Moodle 5 container.',
    tags: ['Docker', 'PHP 8.3', 'MariaDB', 'Redis', 'ECS'],
    links: [],
    items: [
      'Containerized Moodle 5 on PHP 8.3 with MariaDB and Redis, replacing a set of deprecated upstream Bitnami images that were no longer receiving updates',
      'Handled the /public restructure Moodle 5 introduces and the Apache DocumentRoot change it forces, plus OPcache, Redis session handling, and igbinary serialization',
      'Designed for ECS with EFS for shared moodledata and ElastiCache for sessions',
    ],
  },
  {
    id: 'jenkins-ha',
    title: 'Jenkins HA on AWS',
    cardTitle: 'Jenkins HA on AWS',
    summary: 'Immutable Jenkins AMIs in an autoscaling group behind an ALB.',
    tags: ['Packer', 'Ansible', 'Terraform', 'EFS'],
    links: [],
    items: [
      'Built Jenkins controller and agent AMIs with Packer and Ansible provisioning, so replacing a node is a launch rather than a rebuild',
      'Terraform for the whole stack - IAM, an autoscaling group behind an ALB with a static DNS name, and EFS so controller state survives the instance',
      'SSH keys held in Parameter Store and retrieved at boot with boto3 rather than baked into an image',
    ],
  },
  {
    id: 'linux-from-scratch',
    title: 'Linux From Scratch',
    cardTitle: 'Linux From Scratch',
    summary: 'A bootable Linux system compiled from source on a Proxmox VM.',
    tags: ['Linux', 'Proxmox', 'systemd', 'Glibc'],
    links: [],
    items: [
      'Completed a full Linux From Scratch build on a Proxmox VM with a custom 6.13.4 kernel',
      'Compiled and configured systemd, Glibc, Bash, and the rest of the toolchain by hand, with custom partitioning',
      'Ended with a bootable system reachable over SSH',
    ],
  },
];

/** The home page cards, in file order. */
export const featuredProjects: Project[] = cloudAiProjects.filter((p) => p.featured);

/**
 * Pre-cloud work, condensed.
 *
 * This was six separate terminal blocks covering identity, monitoring, imaging,
 * device management, internal tools, and metrics. At that length it read as the
 * main event; what it actually is, is evidence that the cloud work has a decade
 * of operations underneath it. One block, strongest items only.
 */
export const earlierWork = {
  title: 'Earlier IT & Identity Work',
  items: [
    'Cleaned up Jira licensing, saving $20K+ annually with no loss of user access',
    'Wrote a Go tool to automate retrieval and download of security camera footage from S3 Glacier',
    'Built internal Okta API tooling to batch manage users and group assignments',
    'Automated Active Directory onboarding with a script that clones department-based templates to create new users',
    'Rolled out Kandji MDM with custom blueprints and profiles, and opened an Apple Business account to enable zero-touch deployment for every new Mac',
    'Automated employee data updates across Active Directory, Okta, and Azure with PowerShell, and added alerting for BitLocker keys missing from AD',
    'Replaced MDT with SmartDeploy for PXE imaging, with BitLocker key escrow into Active Directory',
    'Built a helpdesk dashboard in Zendesk with automated weekly reporting to stakeholders',
  ],
};


/** True in `next dev`, false in the exported build. */
const SHOW_TODOS = process.env.NODE_ENV === 'development';

/**
 * A project's lines, with unverified ones removed outside development.
 *
 * Every rendering path goes through these rather than reading the fields
 * directly. Any line containing a marker is dropped whole: an earlier version
 * kept the text before a trailing ` - TODO(travis): confirm`, which shipped
 * exactly the part that was waiting to be confirmed.
 */
export function visibleItems(project: Project): string[] {
  if (SHOW_TODOS) return project.items;
  if (project.unverified) return [];
  return project.items.filter((item) => !item.includes('TODO(travis)'));
}

/**
 * Whether the project has a public, running deployment -- a `live` link.
 * Being up is a checkable fact independent of the claims about how it is
 * built, so it shows even on an `unverified` entry.
 */
export function isLive(project: Project): boolean {
  return project.links.some((link) => link.label === 'live');
}

/** The one-line summary, or null where the entry is unverified in production. */
export function visibleSummary(project: Project): string | null {
  return !SHOW_TODOS && project.unverified ? null : project.summary;
}

/** The tag list, empty where the entry is unverified in production. */
export function visibleTags(project: Project): string[] {
  return !SHOW_TODOS && project.unverified ? [] : project.tags;
}
