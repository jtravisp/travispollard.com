/**
 * Identity facts that appear on more than one page.
 *
 * The role string was hardcoded in five places -- the metadata export, the home
 * whoami block, and the whoami blocks on /resume, /projects and /stack. When the
 * title changed, four of them changed and one did not. There is one now.
 */

export const site = {
  name: 'Travis Pollard',
  role: 'Platform Engineer',
  /** The line under the role in the hero, and on the OG card. */
  valueStatement: 'I build and operate scalable AWS infrastructure and AI-driven platforms.',
  email: 'travis@travispollard.com',
  location: 'Austin, TX',
  url: 'https://www.travispollard.com',
  github: 'https://github.com/jtravisp',
  linkedin: 'https://www.linkedin.com/in/travis-pollard',
  resumePdf: '/Travis%20Pollard%20Resume.pdf',
} as const;

export type WritingPost = {
  title: string;
  /** Where it was published, shown beside the title. */
  outlet: string;
  /** Publication year. Omitted rather than guessed when it is not known. */
  year?: number;
  /**
   * A single post, or an author profile on a platform. Both render as the same
   * row; a profile shows "Profile" where a post shows its year.
   */
  kind: 'post' | 'profile';
  url: string;
};

/**
 * Adding a post is one object in this array. Posts first, then the profiles
 * that hold everything else -- as rows of the same list, not a separate
 * "More on Medium" link styled differently from the rest.
 */
export const writing: WritingPost[] = [
  {
    title: 'From S3 to CI/CD: My Cloud Resume Challenge Journey',
    outlet: 'dev.to',
    // From the dev.to API rather than guessed: published_at 2025-04-24.
    year: 2025,
    kind: 'post',
    url: 'https://dev.to/jtravisp/from-s3-to-cicd-my-cloud-resume-challenge-journey-415o',
  },
  {
    title: 'All posts on Medium',
    outlet: 'Medium',
    kind: 'profile',
    url: 'https://medium.com/@travis_17385',
  },
  {
    title: 'All posts on dev.to',
    outlet: 'dev.to',
    kind: 'profile',
    url: 'https://dev.to/jtravisp',
  },
];
