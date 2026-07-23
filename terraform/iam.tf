data "aws_iam_policy_document" "ecs_task_execution_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ecs_task_execution" {
  name               = "${var.project}-exec-role"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_execution_assume.json
}

# Grants ecr:GetAuthorizationToken, logs:CreateLogStream, etc.
resource "aws_iam_role_policy_attachment" "ecs_task_execution" {
  role       = aws_iam_role.ecs_task_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# ---------- Task role (app code uses this) ----------
data "aws_iam_policy_document" "task_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "task" {
  name               = "${var.project}-task-role"
  assume_role_policy = data.aws_iam_policy_document.task_assume.json
}

# Look up the target SQS queue by NAME
data "aws_sqs_queue" "target" {
  name = var.sqs_queue_name
}

# Minimal SQS worker permissions
data "aws_iam_policy_document" "task_sqs" {
  statement {
    sid    = "SqsWorker"
    effect = "Allow"
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:ChangeMessageVisibility",
      "sqs:GetQueueAttributes",
      "sqs:GetQueueUrl",
    ]
    resources = [data.aws_sqs_queue.target.arn]
  }
}

resource "aws_iam_role_policy" "task_sqs" {
  name   = "${var.project}-task-sqs"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task_sqs.json
}

data "aws_iam_policy_document" "task_s3" {
  statement {
    sid    = "ReadWriteModelBucket"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket"
    ]
    resources = var.task_s3_resources
  }
}

resource "aws_iam_role_policy" "task_s3" {
  name   = "${var.project}-task-s3"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task_s3.json
}

data "aws_caller_identity" "current" {}

# --- DynamoDB access for the worker ---
data "aws_iam_policy_document" "task_dynamodb" {
  statement {
    sid    = "ReadWriteModelUrlTable"
    effect = "Allow"
    actions = [
      "dynamodb:PutItem",
      "dynamodb:GetItem",
      "dynamodb:UpdateItem",
      "dynamodb:DescribeTable"
    ]
    resources = [
      "arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.current.account_id}:table/EvoWeather-ModelURLTable",
      "arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.current.account_id}:table/EvoWeather-ModelURLTable/index/*"
    ]
  }
}

resource "aws_iam_role_policy" "task_dynamodb" {
  name   = "${var.project}-task-dynamodb"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task_dynamodb.json
}
