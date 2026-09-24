/**
 * The resume, as data.
 *
 * Transcribed from the resume document on 2026-09-24 so the page and the PDF
 * say the same thing. It was hardcoded in JSX before, which is how the site
 * came to list certifications and a job the current resume had dropped.
 *
 * Anything here that the resume does not say has been removed rather than
 * kept "because it was already on the site" -- that drift is the whole reason
 * this file exists.
 */

export const certifications = [
  'Amazon Web Services Certified Developer - Associate',
  'Amazon Web Services Certified Solutions Architect - Associate',
  'HashiCorp Certified: Terraform Associate',
  'Secret Level Clearance, Active',
  'CompTIA Security+, Network+, A+',
];

export const skills = [
  {
    label: 'Programming Languages',
    value: 'Python, Go, Powershell, SQL',
  },
  {
    label: 'Cloud and Infrastructure',
    value:
      'AWS (EKS, ECS/Fargate, ECR, DynamoDB, Lambda, S3, CloudFront, Route 53, IAM, CloudWatch, SSO), Terraform, Linux, Azure / Entra ID',
  },
  {
    label: 'Platforms & Tools',
    value:
      'Kubernetes, Salesforce (Admin, Development), Git, Jira, Okta, Active Directory / Entra ID, Microsoft 365, Google Workspace, Connectwise Automate, Kandji, Netsuite',
  },
  {
    label: 'Other Skills',
    value:
      'Agile Project Management, Troubleshooting, Process Automation, Technical Documentation, Stakeholder Communication',
  },
];

export type Role = {
  employer: string;
  location: string;
  title: string;
  dates: string;
  bullets: string[];
};

export const experience: Role[] = [
  {
    employer: 'Nuvitek',
    location: 'Washington, DC',
    title: 'Platform Engineer (US Department of Labor)',
    dates: '2024 - Present',
    bullets: [
      'Owned a public-facing federal application serving nationwide workforce training outcome data on AWS EKS, with a Drupal backend, an Angular frontend, and an Elasticsearch search layer',
      'Operated containerized workloads on AWS EKS with kubectl - pod access, log inspection, and production troubleshooting. Diagnosed recurring OOMKilled failures on large migration jobs and specified the memory-limit increase that resolved them',
      'Managed Jenkins build and deployment pipelines for containerized applications, promoting releases across Development, Test, Staging, and Production, including Akamai CDN invalidation at production cutover',
      'Architected and containerized an internal learning platform on AWS ECS/Fargate using a custom Docker image, provisioned end to end in Terraform, replacing a vendor-packaged deployment',
      'Led incident response for a SAML certificate rotation failure that disrupted production authentication; restored access and authored the runbook now used for scheduled rotations',
      'Served as de facto project manager, business analyst, and QA lead following a team reduction',
    ],
  },
  {
    employer: 'United States Gold Bureau',
    location: 'Austin, TX',
    title: 'IT Support and Systems Specialist',
    dates: '2023 - 2024',
    bullets: [
      'Supported 200+ end users, managed implementation of an Apple mobile device management solution, trained new IT staff, automated company processes with PowerShell, Go, and Bash, and administered M365 and Entra',
    ],
  },
  {
    employer: 'Texas Army National Guard - 36th Infantry Division Band',
    location: 'Austin, TX',
    title: 'Sergeant First Class, Music Performance Team Leader',
    dates: '2007 - Present',
    bullets: ['Supervise a platoon of 12 soldiers and lead a performance team of 18 soldiers'],
  },
];

export const education = [
  "The University of Texas at Austin - Master's in Music and Human Learning",
  "Tennessee Technological University - Bachelor's in Music Education",
];
