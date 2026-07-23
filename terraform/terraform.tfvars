region  = "us-east-1"
project = "evoweather-modeldownload-ncephurricane-production" #Comes manually

container_image = "754676389626.dkr.ecr.us-east-1.amazonaws.com/evoweather-modeldownload-ncephurricane" #From ecr
ecr_repository_name  = "evoweather-modeldownload-ncephurricane" #Part of the slash after container_image
ecr_image_tag        = "latest"

sqs_queue_name  = "ModelDownloadNCEPHurricaneQueue" #From SQS
public_subnets  = ["subnet-0152bb3102bdede4f", "subnet-0a42ccdcb20f946ff", "subnet-0bc38a940df7ad6e9", "subnet-00f3421ddcbb750b1", "subnet-0b0de1cf8907c0fef", "subnet-06a5340f7cbd682ce"]
security_groups = ["sg-0f4bfe0eaaff84919"]

task_s3_resources = [
  "arn:aws:s3:::evo-weather-model-data",
  "arn:aws:s3:::evo-weather-model-data/*"
]
