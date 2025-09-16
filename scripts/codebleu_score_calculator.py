import json
import git
import re
import os
import subprocess
from pathlib import Path
from codebleu import compute_codebleu
import javalang


# Paths
output_file = "results/codebleu/agentic_llm/Zookeeper.json"

# code changes commits
code_change_file = "data/ground_truth/code_changes.json"


bug_report_folder = 'data/agentic_llm_possible_fix_full_code'
repositories = [
    {"bug_reports": f"{bug_report_folder}/Zookeeper.json", "ground_truth": "ground_truth/methods/Zookeeper.json", "repo_path": "Projects/zookeeper", "git_branch": 'master'},
    # {"bug_reports": f"{bug_report_folder}/ActiveMQ.json", "ground_truth": "ground_truth/methods/ActiveMQ.json", "repo_path": "Projects/activemq", "git_branch": 'main'},
    # {"bug_reports": f"{bug_report_folder}/Hadoop.json", "ground_truth": "ground_truth/methods/Hadoop.json", "repo_path": "Projects/hadoop", "git_branch": 'trunk'},
    # {"bug_reports": f"{bug_report_folder}/HDFS.json", "ground_truth": "ground_truth/methods/HDFS.json", "repo_path": "Projects/hadoop", "git_branch": 'trunk'},
    # {"bug_reports": f"{bug_report_folder}/Hive.json", "ground_truth": "ground_truth/methods/Hive.json", "repo_path": "Projects/hive", "git_branch": 'master'},
    # {"bug_reports": f"{bug_report_folder}/MAPREDUCE.json", "ground_truth": "ground_truth/methods/MAPREDUCE.json", "repo_path": "Projects/hadoop", "git_branch": 'trunk'},
    # {"bug_reports": f"{bug_report_folder}/Storm.json", "ground_truth": "ground_truth/methods/Storm.json", "repo_path": "Projects/storm", "git_branch": 'master'},
    # {"bug_reports": f"{bug_report_folder}/YARN.json", "ground_truth": "ground_truth/methods/YARN.json", "repo_path": "Projects/hadoop", "git_branch": 'trunk'}
]



# Checkout to the specific commit version
def checkout_to_commit(commit_version, repo_path, git_branch):
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
    # Drop the stash if it's no longer needed
    subprocess.run('git stash drop', shell=True, cwd=repo_path)



# Extract methods from Java files
def extract_methods_from_file(file_path):
    """
    Extract method names and bodies from a Java file using javalang.
    """
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    methods = []
    try:
        tree = javalang.parse.parse(content)
        for _, method in tree.filter(javalang.tree.MethodDeclaration):
            method_name = method.name
            if method.position:
                method_body = extract_method_code(content, method.position)
            else:
                method_body = ""

            methods.append((method_name, method_body))
    except Exception as e:
        print(f"Failed to parse {file_path}: {e}")
    return methods

def extract_method_code(file_content, position):
    """
    Extract the full method body using the position provided by javalang.
    """
    lines = file_content.splitlines()
    start_line = position.line - 1  # javalang position is 1-indexed
    method_lines = []
    open_braces = 0
    found_method_start = False  # To track when the method body starts

    for i in range(start_line, len(lines)):
        line = lines[i]
        method_lines.append(line)

        # Update brace counts
        open_braces += line.count('{')
        open_braces -= line.count('}')

        # Check if we are inside the method body
        if '{' in line and not found_method_start:
            found_method_start = True

        # Stop when all braces are balanced after method body starts
        if found_method_start and open_braces == 0:
            break

    return "\n".join(method_lines)




def get_last_two_tokens(full_method: str) -> str:
    """Return 'Class.method' from a full name like a.b.c.Class.method."""
    parts = full_method.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else full_method


def find_single_gt_match_for_candidate(cand_key: str, gt_methods_for_bug):
    """
    For a candidate key like 'QuorumPeerConfig.parseProperties' (or sometimes just 'parseProperties'),
    find ONE GT method full name:
      1) try endswith(Class.method) using last two tokens of cand_key
      2) else try method-name-only
    Return the matched GT full name or None.
    """
    if not cand_key:
        return None

    ck = cand_key.strip()
    cand_parts = ck.split(".")
    cand_last_two = ".".join(cand_parts[-2:]) if len(cand_parts) >= 2 else ck
    cand_last_one = cand_parts[-1]

    # Prefer Class.method endswith match
    two_token_matches = [gt for gt in gt_methods_for_bug if gt.endswith(cand_last_two)]
    if two_token_matches:
        return sorted(two_token_matches)[0]

    # Fallback: method-only exact match on last token
    one_token_matches = [gt for gt in gt_methods_for_bug if gt.split(".")[-1] == cand_last_one]
    if one_token_matches:
        return sorted(one_token_matches)[0]

    return None


def gt_fullname_to_path_and_method(gt_fullname):
    """
    Convert a GT full name like:
      'src.java.main.org.apache.zookeeper.server.quorum.QuorumPeerConfig.parseProperties'
    into:
      file_rel_path: 'src/java/main/org/apache/zookeeper/server/quorum/QuorumPeerConfig.java'
      method_name:   'parseProperties'
    """
    parts = gt_fullname.split('.')
    method_name = parts[-1]
    class_path_parts = parts[:-1]  # everything except method name
    file_rel_path = "/".join(class_path_parts) + ".java"
    return file_rel_path, method_name


def compute_codebleu_single(candidate_code, reference_code, lang="java"):
    refs = [[str(reference_code).strip()]]
    cands = [str(candidate_code).strip()]
    score_dict = compute_codebleu(
        refs,
        cands,
        lang,
        weights=(1/3, 1/3, 0, 1/3)  # bleu, ngram, syntax=0, dataflow
    )
    return score_dict









# Store all CodeBLEU scores
all_scores = []
results = []

# List of bug reports to skip for method level FL and for missing path
bug_reports_to_skip_for_method_level_fl = ["HDFS-6533.json", "HADOOP-12611.json", "HADOOP-11149.json", "HDFS-6904.json", "HDFS-13635.json", "HDFS-7884.json", "HIVE-2958.json", "MAPREDUCE-3070.json", "MAPREDUCE-5451.json", "MAPREDUCE-3531.json", "MAPREDUCE-7077.json", "MAPREDUCE-6702.json", "STORM-1520.json", "STORM-2873.json", "YARN-1550.json", "YARN-2649.json", "YARN-5728.json", "YARN-7645.json", "YARN-7849.json"]
bug_reports_to_skip_for_missing_path = ["ZOOKEEPER-1264.json", "ZOOKEEPER-1870.json", "HADOOP-6989.json", "HADOOP-8110.json", "HDFS-13039.json", "HDFS-6102.json", "HDFS-6250.json", "HDFS-6715.json", "HDFS-1085.json", "HDFS-10962.json", "HDFS-9549.json", "HDFS-2882.json", "HDFS-8276.json", "HIVE-13392.json", "HIVE-7799.json", "HIVE-5546.json", "HIVE-19248.json", "HIVE-11762.json", "MAPREDUCE-6815.json", "MAPREDUCE-2463.json", "MAPREDUCE-5260.json", "MAPREDUCE-4913.json", "MAPREDUCE-2238.json", "MAPREDUCE-3058.json", "STORM-2988.json", "STORM-2400.json", "STORM-2158.json", "YARN-370.json", "YARN-3790.json", "YARN-1903.json"]


for repo_info in repositories:
    bug_report_file = repo_info["bug_reports"]
    repo_path = repo_info["repo_path"]
    git_branch = repo_info["git_branch"]
    gt_file = repo_info["ground_truth"]


    # Load agent-generated possible fixes (list of entries)
    with open(bug_report_file, "r") as f:
        bug_report_data = json.load(f)

    # Load ground truth methods per bug file
    with open(gt_file, "r") as f:
        ground_truth_methods_by_bug = json.load(f)

    # Load commit mapping
    with open(code_change_file, "r") as f:
        code_change_data = json.load(f)

    # Process each bug report
    for entry in bug_report_data:
        filename = entry["filename"]
        creation_time = entry['creation_time']
        issue_id = filename.split(".")[0]
        # candidate_fix = entry.get("possible_fix_code", "")


        # Skip bug reports for method level FL and for missing path
        if filename in bug_reports_to_skip_for_method_level_fl or filename in bug_reports_to_skip_for_missing_path:
            print(f"Skipping bug report: {filename}")
            continue  # Move to the next bug report

        
        # Candidate methods dict
        possible_fix_code = entry.get("possible_fix_code", {})
        if not isinstance(possible_fix_code, dict) or not possible_fix_code:
            print(f"[{filename}] Skipped: possible_fix_code is empty or not a dict")
            continue


        # Per-filename GT method list
        gt_methods_for_bug = ground_truth_methods_by_bug.get(filename, [])
        if not gt_methods_for_bug:
            print(f"[{filename}] Skipped: no ground-truth methods listed")
            continue


        # Find corresponding commit
        matching_key = next((key for key in code_change_data if key.startswith(issue_id + "@")), None)
        if not matching_key:
            print(f"[{filename}] Skipped: no commit mapping found")
            continue
        commit_hash = matching_key.split("@")[1]


        # Pre-check: build candidate -> single GT match mapping
        candidate_to_gt = {}
        for cand_key in possible_fix_code.keys():
            matched_gt = find_single_gt_match_for_candidate(cand_key, gt_methods_for_bug)
            if matched_gt is not None:
                candidate_to_gt[cand_key] = matched_gt

        if not candidate_to_gt:
            print(f"[{filename}] Skipped: no candidate->ground-truth method matches")
            continue

        if candidate_to_gt:
            checkout_to_commit(commit_hash, repo_path, git_branch)
            print(f"Processing {filename} @ {commit_hash} with {len(candidate_to_gt)} matched candidate methods")

        # Compare each matched candidate to the method extracted from the checked-out code
        for cand_key, gt_fullname in candidate_to_gt.items():
            cand_code = possible_fix_code.get(cand_key, "")
            if not cand_code or not isinstance(cand_code, str):
                print(f"[{filename}] Skipped {cand_key}: candidate code missing")
                continue

            file_rel_path, method_name = gt_fullname_to_path_and_method(gt_fullname)
            file_abs_path = os.path.join(repo_path, file_rel_path)

            if not os.path.exists(file_abs_path):
                print(f"[{filename}] {cand_key} -> {file_rel_path}: file does not exist at commit")
                continue

            # Extract all methods and pick the one with matching name
            methods_in_file = extract_methods_from_file(file_abs_path)
            ref_method_code = None
            for name, body in methods_in_file:
                if name == method_name:
                    ref_method_code = body
                    break

            if not ref_method_code:
                print(f"[{filename}] {cand_key} -> GT {gt_fullname}: method not found in {file_rel_path}")
                continue

            # Compute CodeBLEU
            try:
                score = compute_codebleu_single(cand_code, ref_method_code, lang="java")
                all_scores.append(score['codebleu'])
                results.append({
                    "filename": filename,
                    "creation_time": creation_time,
                    "commit": commit_hash,
                    "candidate_key": cand_key,
                    "ground_truth_method": gt_fullname,
                    "file_path": file_rel_path,
                    "codebleu": score
                })
                print(f"[{filename}] {cand_key} == {gt_fullname} → CodeBLEU: {score['codebleu']:.4f}")
            except Exception as e:
                print(f"[{filename}] CodeBLEU failed for {cand_key} vs {gt_fullname}: {e}")

        # Save after each bug
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(results, f, indent=4)
            print(f"Results saved to {output_file}")
        except Exception as e:
            print(f"Failed to write {output_file}: {e}")

# Final average
average_codebleu = sum(all_scores) / len(all_scores) if all_scores else 0.0
print(f"Average CodeBLEU across all matched methods ({len(all_scores)} bugs): {average_codebleu:.4f}")





