{
  "provider": {
    "aws": {
      "region": "us-east-1"
    }
  },
  "resource": {
    "aws_instance": {
      "ec2": {
        "ami": "ami-0c55b159cbfafe1f0",
        "instance_type": "t2.micro",
        "tags": {
          "Name": "ec2"
        }
      }
    },
    "aws_s3_bucket": {
      "prod": {
        "bucket": "tf-devops-prod",
        "tags": {
          "env": "prod",
          "managed_by": "terraform",
          "repository": "tf-devops"
        }
      }
    }
  }
}
