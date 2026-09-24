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
  /** One line under the role in every whoami block. */
  valueStatement:
    'I build and operate AWS infrastructure and AI-powered apps: Terraform, serverless, Go, Python.',
  email: 'travis@travispollard.com',
  location: 'Austin, TX',
  url: 'https://www.travispollard.com',
  github: 'https://github.com/jtravisp',
  linkedin: 'https://www.linkedin.com/in/travis-pollard',
  resumePdf: '/Travis%20Pollard%20Resume.pdf',
} as const;

export type WritingPost = {
  title: string;
  /** Where it was published, shown under the title. */
  outlet: string;
  url: string;
};

/**
 * Adding a post is one object in this array. That is the entire reason this
 * file exists -- the section previously hardcoded a single link plus a "more
 * posts" catch-all, which is a shape that discourages ever adding a second one.
 */
export const writing: WritingPost[] = [
  {
    title: 'From S3 to CI/CD: My Cloud Resume Challenge Journey',
    outlet: 'dev.to',
    url: 'https://dev.to/jtravisp/from-s3-to-cicd-my-cloud-resume-challenge-journey-415o',
  },
  {
    title: 'More posts on cloud, automation, and career change',
    outlet: 'Medium',
    url: 'https://medium.com/@travis_17385',
  },
];
