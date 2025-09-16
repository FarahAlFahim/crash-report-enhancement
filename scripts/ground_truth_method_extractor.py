import json
import git
import re
import subprocess
from pathlib import Path

# Paths
ground_truth_file = "data/ground_truth/class_level/Zookeeper.json"
output_file = "data/ground_truth/method_level/Zookeeper.json"

# code changes commits
code_change_file = "data/ground_truth/code_changes.json"

# For Zookeeper.json
repo_path = "Projects/zookeeper"
git_branch = "master"



# Load JSON files
with open(ground_truth_file, "r") as f:
    ground_truth_data = json.load(f)

with open(code_change_file, "r") as f:
    code_change_data = json.load(f)

# Initialize Git repository
repo = git.Repo(repo_path)

# def checkout_to_commit(commit_version, repo_path, git_branch):
#     """Switches the repository to the specified commit version."""
#     subprocess.run('git stash --include-untracked', shell=True, cwd=repo_path)
#     subprocess.run(f'git checkout {git_branch}', shell=True, cwd=repo_path)
#     subprocess.run(f'git checkout {commit_version}', shell=True, cwd=repo_path)

def checkout_to_commit(commit_version, repo_path, git_branch):
    """Switches the repository to the specified commit version, handling uncommitted changes properly."""
    
    # Reset any local changes
    subprocess.run('git reset --hard', shell=True, cwd=repo_path)
    
    # Ensure a clean stash
    subprocess.run('git stash push --include-untracked', shell=True, cwd=repo_path)
    
    # Switch back to the main branch before checking out the commit
    subprocess.run(f'git checkout {git_branch}', shell=True, cwd=repo_path)
    
    # Ensure branch is up-to-date
    subprocess.run('git pull', shell=True, cwd=repo_path)
    
    # Checkout to the required commit
    subprocess.run(f'git checkout {commit_version}', shell=True, cwd=repo_path)
    
    # Create or overwrite the .gitattributes file to use custom diff for *.java files
    with open(f"{repo_path}/.gitattributes", "w") as f:
        f.write("*.java diff=java\n")
    
    # Drop the stash if it's no longer needed
    subprocess.run('git stash drop', shell=True, cwd=repo_path)





def extract_modified_methods(commit_hash, git_branch):
    """Extracts modified method names from a commit using simple regex parsing."""
    checkout_to_commit(commit_hash, repo_path, git_branch)

    repo = git.Repo(repo_path)
    commit = repo.commit(commit_hash)
    parent_commit = commit.parents[0] if commit.parents else None
    print("commit_hash:", commit_hash)
    print("commit:", commit)
    print("parent_commit:", parent_commit)
    print("commit.parents:", commit.parents[0])

    modified_methods = set()

    if parent_commit:
        diffs = commit.diff(parent_commit, create_patch=True)
        # print("--------------- diffs (start) --------------")
        # print(diffs)
        # print("--------------- diffs (end) --------------")

        for diff in diffs:
            print("--------------- diff in diffs (start) --------------")
            print(diff)
            print("--------------- diff in diffs (end) --------------")
            file_path = diff.b_path if diff.b_path else diff.a_path  # Modified file path
            # print("diff.a_path:", diff.a_path)
            # print("diff.b_path:", diff.b_path)
            # print("file_path:", file_path)
            # print("diff.diff:", diff.diff)
            if file_path and file_path.endswith(".java") and diff.diff:
                modified_methods.update(extract_methods_from_diff(diff.diff, file_path))

    # print("--------------- list(modified_methods) [START] --------------")
    # print(list(modified_methods))
    # print("--------------- list(modified_methods) [END] --------------")
    return list(modified_methods)



def extract_methods_from_diff(patch, file_path):
    """Extracts method names using regex from diff headers."""
    modified_methods = set()

    # Decode bytes to string
    patch = patch.decode("utf-8")

    # Find all diff headers
    method_headers = re.findall(r"@@ -\d+,\d+ \+\d+,\d+ @@ (.*)", patch)
    invalid_keywords = ["if", "else", "else if", "for", "while", "switch", "try", "catch", "finally", "return", "throw"]
    print("--------------- method_headers (start) --------------")
    print(method_headers)
    print("--------------- method_headers (end) --------------")
    for header in method_headers:
        if "(" in header:
            method_name = header.split("(")[0].strip().split(" ")[-1].strip()  # Extract method name
            if method_name in invalid_keywords:
                continue  # Skip invalid control-flow statements
            full_method_path = f"{file_path.replace('/', '.')[:-5]}.{method_name}"  # Convert file path to package format
            modified_methods.add(full_method_path)

    return modified_methods









# Process each entry in ground_truth.json
output_data = {}

for filename, ground_truth_classes in ground_truth_data.items():
    issue_id = filename.split(".")[0]  # Extract ZOOKEEPER-1864 from ZOOKEEPER-1864.json

    # Find the matching commit from code_change.json
    matching_key = next((key for key in code_change_data if key.startswith(issue_id)), None)

    if matching_key:
        commit_hash = matching_key.split("@")[1]
        print(f"Processing {issue_id} at commit {commit_hash}...")

        # Extract modified methods
        modified_methods = extract_modified_methods(commit_hash, git_branch)

        # Filter methods that match ground truth class names
        relevant_methods = [
            method for method in modified_methods
            if any(cls in method for cls in ground_truth_classes)  # Ensure class name exists in method path
        ]

        output_data[filename] = relevant_methods

# Write output to file
with open(output_file, "w") as f:
    json.dump(output_data, f, indent=4)

print(f"Results saved to {output_file}")
