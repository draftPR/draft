# Environment Variables Setup

## AWS Bedrock Configuration

To use AWS Bedrock models with the Smart Kanban planner, add these variables to your `.env` file in the `backend/` directory:

```bash
# Required AWS Credentials
AWS_ACCESS_KEY_ID=your-access-key-id-here
AWS_SECRET_ACCESS_KEY=your-secret-access-key-here
AWS_REGION_NAME=us-east-1
```

### Notes:

1. **Model Configuration**: The model is configured in `smartkanban.yaml`:
   ```yaml
   planner_config:
     model: "bedrock/anthropic.claude-sonnet-4-5-20250929-v1:0"
   ```

2. **AWS Region**: Make sure your `AWS_REGION_NAME` matches where your Bedrock model is available. Common regions:
   - `us-east-1` (N. Virginia)
   - `us-west-2` (Oregon)
   - Check AWS Bedrock documentation for model availability by region

3. **Bedrock Access**: Ensure your AWS account has:
   - AWS Bedrock enabled
   - Model access requested and approved for Claude Sonnet 4.5
   - IAM permissions for `bedrock:InvokeModel`

4. **Alternative: AWS Profile**: Instead of access keys, you can use an AWS CLI profile:
   ```bash
   AWS_PROFILE=your-profile-name
   AWS_REGION_NAME=us-east-1
   ```

## Other Environment Variables

```bash
# Frontend URL for CORS (optional, defaults to http://localhost:5173)
FRONTEND_URL=http://localhost:5173

# Git repository path (optional, defaults to current directory)
GIT_REPO_PATH=/path/to/your/repo

# Database URL (optional, defaults to sqlite:///kanban.db)
DATABASE_URL=sqlite:///kanban.db
```

## Testing the Configuration

1. Make sure your `.env` file is in the `backend/` directory
2. Restart the backend server to load the new environment variables
3. Trigger a planner action (like proposing follow-ups for a blocked ticket) to test the LLM connection
4. Check the logs for any AWS authentication or model access errors

## Troubleshooting

- **Authentication errors**: Verify your AWS credentials are correct
- **Model not found**: Check if the model ID is correct and available in your region
- **Access denied**: Ensure your IAM user/role has Bedrock permissions
- **Region mismatch**: Verify the model is available in your configured region


