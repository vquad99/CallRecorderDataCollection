# Recordings, originals, export bundles and the app's own database dumps: one private S3 bucket.
# Encrypted by S3 (SSE-S3: no key to manage, no per-request charge). Reached by the server's role.
#
# Versioning (on by default): a file deleted or overwritten by mistake can be brought back for
# recordings_noncurrent_days days, then it is gone for good. This does not fight the app's own
# retention: the app still deletes files when a project's rules say so; the deletion becomes final
# recordings_noncurrent_days later. No rule here ever deletes or moves a current file: what is kept
# is the app's decision only.

resource "aws_s3_bucket" "recordings" {
  bucket = "${var.name}-recordings-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_public_access_block" "recordings" {
  bucket                  = aws_s3_bucket.recordings.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "recordings" {
  bucket = aws_s3_bucket.recordings.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "recordings" {
  bucket = aws_s3_bucket.recordings.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_versioning" "recordings" {
  count  = var.recordings_versioning ? 1 : 0
  bucket = aws_s3_bucket.recordings.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "recordings" {
  bucket = aws_s3_bucket.recordings.id

  # Uploads that stopped half-way (a big file sent in parts) only cost money.
  rule {
    id     = "abort-unfinished-uploads"
    status = "Enabled"
    filter {}
    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }

  dynamic "rule" {
    for_each = var.recordings_versioning ? [1] : []
    content {
      id     = "deleted-files-gone-after-n-days"
      status = "Enabled"
      filter {}
      noncurrent_version_expiration {
        noncurrent_days = var.recordings_noncurrent_days
      }
      expiration {
        expired_object_delete_marker = true
      }
    }
  }

  depends_on = [aws_s3_bucket_versioning.recordings]
}

# HTTPS only.
data "aws_iam_policy_document" "recordings_bucket" {
  statement {
    sid     = "HttpsOnly"
    effect  = "Deny"
    actions = ["s3:*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    resources = [aws_s3_bucket.recordings.arn, "${aws_s3_bucket.recordings.arn}/*"]
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "recordings" {
  bucket     = aws_s3_bucket.recordings.id
  policy     = data.aws_iam_policy_document.recordings_bucket.json
  depends_on = [aws_s3_bucket_public_access_block.recordings]
}

# What the app (and the one-off file copy) may do. Not s3:DeleteObjectVersion: nobody on the server
# can remove a kept version; only the lifecycle rule above does, after recordings_noncurrent_days.
data "aws_iam_policy_document" "recordings_access" {
  statement {
    sid       = "Bucket"
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = [aws_s3_bucket.recordings.arn]
  }
  statement {
    sid = "Objects"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = ["${aws_s3_bucket.recordings.arn}/*"]
  }
}

# Only with storage_user_fallback: the same rights for an IAM user whose keys go into .env until the
# app can use the server's role. Make its access key by hand (IAM console), so it is not in the state.
resource "aws_iam_user" "storage" {
  count = var.storage_user_fallback ? 1 : 0
  name  = "${var.name}-storage"
}

resource "aws_iam_user_policy" "storage" {
  count  = var.storage_user_fallback ? 1 : 0
  name   = "recordings-bucket"
  user   = aws_iam_user.storage[0].name
  policy = data.aws_iam_policy_document.recordings_access.json
}
