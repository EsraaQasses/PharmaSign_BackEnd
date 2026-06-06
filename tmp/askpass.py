import os
import sys

# Print the password from the environment variable
print(os.environ.get("SSH_PASSWORD", ""))
