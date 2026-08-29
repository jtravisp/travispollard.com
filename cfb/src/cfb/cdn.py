"""The CloudFront seam (SPEC-phase1 6.5).

The second AWS boundary in this package, and it exists for the same reason
``storage`` does: so that the untested part is exactly one function whose whole
body is the call. Whether the distribution exists, whether the publisher role may
invalidate it, and whether the parameter holding its id is readable are facts
about an AWS account rather than about this code.

**The distribution belongs to the root Terraform stack and its id is read from
SSM, never hardcoded** (`cfb/CLAUDE.md`). `/travispollard/cdn/` is the entire
contract between the two stacks: root writes the id and the ARN there, cfb reads
them, and neither references the other's state.

**An invalidation is not part of the write.** §6.5 pairs it with the upload, but
the upload is what makes the new documents exist and the invalidation only makes
them visible sooner -- so a failure here is a slow page, not a wrong one, and the
two are worth distinguishing in a run that has to be read at 12:00 on a Friday.
`cfb publish` writes first and invalidates second for that reason.
"""

from cfb.errors import optional_import

__all__ = ["DATA_PATHS", "DISTRIBUTION_ID_PARAMETER", "REGION", "distribution_id", "invalidate"]

#: SPEC-phase0 10.2's seam. Written by the root stack's `cfb-wiring.tf`.
DISTRIBUTION_ID_PARAMETER = "/travispollard/cdn/distribution_id"

#: SPEC 2: us-east-1, passed explicitly and never inherited from ambient env.
#: CloudFront's own API is global and boto3 still wants a region for it.
REGION = "us-east-1"

#: §6.5. The published documents and nothing else -- an invalidation of `/*`
#: would flush the whole site on the pipeline's schedule, and the site deploys on
#: a different one.
DATA_PATHS = ("/cfb/data/*",)


def distribution_id(parameter: str = DISTRIBUTION_ID_PARAMETER, *, region: str = REGION) -> str:
    """Read the distribution id from SSM. **Not covered by any test, and cannot be.**

    Same shape as ``cfbd.ssm_secret`` and untested for the same reason: its whole
    body is one call whose answer is a property of an account.

    No ``WithDecryption``: this is a plain ``String`` parameter, not a
    ``SecureString``. A distribution id is not a secret -- it is in every response
    header the CDN sends -- and asking for decryption on a plain parameter would
    add a ``kms:Decrypt`` requirement the publisher role does not need for it.
    """
    with optional_import("boto3", extra="s3", needed_for="reading the CDN id from SSM"):
        import boto3

    client = boto3.client("ssm", region_name=region)
    return client.get_parameter(Name=parameter)["Parameter"]["Value"]


def invalidate(
    *, distribution: str, paths: tuple[str, ...] = DATA_PATHS, caller_reference: str
) -> str:
    """Invalidate ``paths`` and return the invalidation id.

    ``caller_reference`` is required rather than generated here. CloudFront uses
    it to make the call idempotent, and a value generated inside this function
    would be new on every retry -- which turns a retried publish into two
    invalidations of the same paths, each billed and each racing the other's
    completion. The caller has the one thing that identifies the run: the moment
    it was stamped with.
    """
    with optional_import("boto3", extra="s3", needed_for="invalidating the CDN"):
        import boto3

    client = boto3.client("cloudfront", region_name=REGION)
    response = client.create_invalidation(
        DistributionId=distribution,
        InvalidationBatch={
            "Paths": {"Quantity": len(paths), "Items": list(paths)},
            "CallerReference": caller_reference,
        },
    )
    return response["Invalidation"]["Id"]
