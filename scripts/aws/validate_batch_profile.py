#!/usr/bin/env python3
"""Validate the AWS Batch profile without submitting or mutating cloud resources."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, dataclass
from typing import Any
from urllib.parse import urlparse

import boto3

IMAGE_PATTERN = re.compile(
    r"^(?P<account>[0-9]{12})\.dkr\.ecr\.(?P<region>[a-z0-9-]+)\.amazonaws\.com/"
    r"(?P<repository>[a-z0-9._/-]+)@sha256:(?P<digest>[a-f0-9]{64})$"
)
ROLE_PATTERN = re.compile(r"^arn:(?:aws|aws-us-gov|aws-cn):iam::[0-9]{12}:role/.+$")


@dataclass(frozen=True, slots=True)
class BatchProfile:
    region: str
    queue: str
    job_role_arn: str
    log_group: str
    scientific_image: str
    work_uri: str
    reference_cache_uri: str


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def load_profile() -> BatchProfile:
    """Load and structurally validate the environment consumed by Nextflow."""
    profile = BatchProfile(
        region=_required("TRANSCRIPTFORGE_AWS_REGION"),
        queue=_required("TRANSCRIPTFORGE_AWS_BATCH_QUEUE"),
        job_role_arn=_required("TRANSCRIPTFORGE_AWS_BATCH_JOB_ROLE_ARN"),
        log_group=_required("TRANSCRIPTFORGE_AWS_BATCH_LOG_GROUP"),
        scientific_image=_required("TRANSCRIPTFORGE_AWS_SCIENTIFIC_IMAGE"),
        work_uri=_required("TRANSCRIPTFORGE_AWS_WORK_URI"),
        reference_cache_uri=_required("TRANSCRIPTFORGE_AWS_REFERENCE_CACHE_URI"),
    )
    parsed = urlparse(profile.work_uri)
    if parsed.scheme != "s3" or not parsed.netloc or parsed.path in {"", "/"}:
        raise ValueError("TRANSCRIPTFORGE_AWS_WORK_URI must include an S3 bucket and prefix")
    image_match = IMAGE_PATTERN.fullmatch(profile.scientific_image)
    if image_match is None:
        raise ValueError("TRANSCRIPTFORGE_AWS_SCIENTIFIC_IMAGE must be an ECR image digest")
    if image_match.group("region") != profile.region:
        raise ValueError("The ECR image and Batch profile must use the same AWS Region")
    if ROLE_PATTERN.fullmatch(profile.job_role_arn) is None:
        raise ValueError("TRANSCRIPTFORGE_AWS_BATCH_JOB_ROLE_ARN is not an IAM role ARN")
    reference = urlparse(profile.reference_cache_uri)
    if reference.scheme != "s3" or not reference.netloc or reference.path in {"", "/"}:
        raise ValueError(
            "TRANSCRIPTFORGE_AWS_REFERENCE_CACHE_URI must include an S3 bucket and prefix"
        )
    if reference.netloc != parsed.netloc:
        raise ValueError("Work and reference-cache URIs must use the provisioned data bucket")
    return profile


def validate_live(profile: BatchProfile) -> dict[str, Any]:
    """Read cloud control planes to prove the configured boundary exists and is encrypted."""
    session = boto3.Session(region_name=profile.region)
    identity = session.client("sts").get_caller_identity()

    queues = session.client("batch").describe_job_queues(jobQueues=[profile.queue])["jobQueues"]
    if len(queues) != 1 or queues[0]["state"] != "ENABLED" or queues[0]["status"] != "VALID":
        raise RuntimeError("Batch queue must exist with ENABLED/VALID state")

    role_name = profile.job_role_arn.partition(":role/")[2]
    role = session.client("iam").get_role(RoleName=role_name)["Role"]

    groups = session.client("logs").describe_log_groups(
        logGroupNamePrefix=profile.log_group,
    )["logGroups"]
    group = next((item for item in groups if item["logGroupName"] == profile.log_group), None)
    if group is None or not group.get("kmsKeyId"):
        raise RuntimeError("Batch log group must exist and use a customer-managed KMS key")

    parsed = urlparse(profile.work_uri)
    s3 = session.client("s3")
    s3.head_bucket(Bucket=parsed.netloc)
    encryption = s3.get_bucket_encryption(Bucket=parsed.netloc)
    rules = encryption["ServerSideEncryptionConfiguration"]["Rules"]
    if not any(
        item["ApplyServerSideEncryptionByDefault"]["SSEAlgorithm"] == "aws:kms"
        for item in rules
    ):
        raise RuntimeError("Nextflow S3 bucket does not default to SSE-KMS")
    public = s3.get_public_access_block(Bucket=parsed.netloc)["PublicAccessBlockConfiguration"]
    if not all(public.values()):
        raise RuntimeError("All S3 public-access-block controls must be enabled")

    image = IMAGE_PATTERN.fullmatch(profile.scientific_image)
    assert image is not None
    session.client("ecr").describe_images(
        registryId=image.group("account"),
        repositoryName=image.group("repository"),
        imageIds=[{"imageDigest": f"sha256:{image.group('digest')}"}],
    )

    return {
        "account_id": identity["Account"],
        "caller_arn": identity["Arn"],
        "queue_arn": queues[0]["jobQueueArn"],
        "job_role_id": role["RoleId"],
        "s3_kms_encrypted": True,
        "s3_public_access_blocked": True,
        "log_kms_encrypted": True,
        "image_digest_present": True,
        "reference_cache": "s3",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="perform read-only AWS API checks")
    args = parser.parse_args()
    try:
        profile = load_profile()
        result: dict[str, Any] = {"status": "VALID", "profile": asdict(profile)}
        if args.live:
            result["aws"] = validate_live(profile)
    except (ValueError, RuntimeError) as error:
        print(json.dumps({"status": "INVALID", "error": str(error)}, indent=2), file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
