{
  "mode": "infra",
  "cloud": "aws",
  "title": "use ec2_instance module",
  "summary": "Use approved tf-devops local module ec2_instance after retrieval review.",
  "files": [
    {
      "filename": "main.tf",
      "content": "module \"ec2_instance\" {\n  source = ../../modules/ec2_instance\n}\n"
    }
  ]
}
