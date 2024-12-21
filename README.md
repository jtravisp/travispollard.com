# travispollard.com Infrastructure

This repository contains the Terraform configuration for deploying the infrastructure of `travispollard.com`. The infrastructure is hosted on AWS and includes resources like S3 for static site hosting, CloudFront for content delivery, Route 53 for DNS, and ACM for SSL/TLS certificates.

## Table of Contents
- [travispollard.com Infrastructure](#travispollardcom-infrastructure)
  - [Table of Contents](#table-of-contents)
  - [Project Structure](#project-structure)
  - [Getting Started](#getting-started)
  - [Prerequisites](#prerequisites)
  - [Resources Created](#resources-created)


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