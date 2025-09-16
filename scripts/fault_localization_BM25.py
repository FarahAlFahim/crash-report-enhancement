import os
import re
import ssl
import json
import subprocess
import nltk
import javalang
from collections import defaultdict
from nltk.tokenize import word_tokenize
from rank_bm25 import BM25Okapi
from javalang.parse import parse
from javalang.tree import MethodDeclaration, ClassDeclaration

# Set SSL context to fix SSL certificate issue with nltk.download()
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

# Download the punkt tokenizer for word_tokenize
nltk.download("punkt")

# Load bug reports from JSON file
def load_bug_reports(file_path):
    with open(file_path, "r") as f:
        bug_reports = json.load(f)
    return bug_reports

# Load ground truth data
def load_ground_truth(file_path):
    with open(file_path, "r") as f:
        ground_truth = json.load(f)
    return ground_truth

# Convert JSON bug report to a string
def convert_bug_report_to_string(bug_report):
    return json.dumps(bug_report, indent=4)

# Get the commit version before a specific timestamp
def get_commit_version(creation_time, repo_path, git_branch):
    command = f'git rev-list -n 1 --before="{creation_time}" {git_branch}'
    result = subprocess.run(command, shell=True, capture_output=True, text=True, cwd=repo_path)
    commit_version = result.stdout.strip()
    return commit_version

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
    

# Preprocess text for tokenization
def preprocess_text(text):
    tokens = word_tokenize(text.lower())
    return [token for token in tokens if token.isalnum()]


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
            # print("------------------- method_name (start) --------------------")
            # print(f"{method_name}: {method_body}")
            # print("------------------- method_name (end) --------------------")

        # print(f"Extracted {len(methods)} methods from {file_path}")
    except Exception as e:
        print(f"Failed to parse {file_path}: {e}")
    # print("------------------- methods (start) --------------------")
    # print(methods)
    # print("------------------- methods (end) --------------------")
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




# Index codebase at method level using BM25
def index_codebase_with_bm25(codebase_dirs):
    if isinstance(codebase_dirs, str):  # Allow backward compatibility for a single directory
        codebase_dirs = [codebase_dirs]

    corpus = []
    method_list = []

    for codebase_dir in codebase_dirs:
        for root, _, files in os.walk(codebase_dir):
            for file in files:
                if file.endswith(".java"):
                    file_path = os.path.join(root, file)
                    methods = extract_methods_from_file(file_path)
                    for method_name, method_body in methods:
                        tokens = preprocess_text(method_body)
                        corpus.append(tokens)
                        method_list.append((file_path, method_name))

    # Handle empty corpus case
    if not corpus:
        return None, []

    bm25 = BM25Okapi(corpus)
    return bm25, method_list


# Extract stack trace and keywords
def extract_stack_trace(bug_report):
    pattern = r"at (.+?)\((.+?):(\d+)\)"
    stack_trace = re.findall(pattern, bug_report)
    return stack_trace

def extract_keywords(bug_report):
    words = word_tokenize(bug_report)
    keywords = [word.lower() for word in words if word.isalpha() and len(word) > 3]
    return keywords


# Rank methods using BM25
def rank_methods_with_bm25(bm25, method_list, keywords, stack_trace, codebase_dirs):
    if bm25 is None:  # Handle empty corpus case
        print("Warning: No indexed source code methods found. Returning empty rankings.")
        return []

    query = preprocess_text(" ".join(keywords))
    scores = bm25.get_scores(query)

    method_scores = {method: score for method, score in zip(method_list, scores)}
    for class_name, file_name, line_number in stack_trace:
        package_path = os.sep.join(class_name.split('.')[:-1]) + ".java"
        for codebase_dir in codebase_dirs:
            full_path = os.path.join(codebase_dir, package_path)
            for method in method_list:
                if method[0] == full_path:
                    method_scores[method] += 5

    ranked_methods = sorted(method_scores.items(), key=lambda x: x[1], reverse=True)
    return ranked_methods


# Convert method path to ground truth format
def convert_to_ground_truth_format(method, codebase_dirs):
    file_path, method_name = method
    for codebase_dir in codebase_dirs:
        if file_path.startswith(codebase_dir):
            relative_path = file_path.replace(codebase_dir + os.sep, "").replace(".java", "")
            return f"{relative_path.replace(os.sep, '.')}.{method_name}"
    return None  # Handle methods that don't match any directory


# Transform ranked methods to ground truth format
def transform_ranked_methods(ranked_methods, codebase_dirs):
    return [convert_to_ground_truth_format(method, codebase_dirs) for method, _ in ranked_methods]



def save_ranked_methods(filename, ranked_methods, transformed_ranked_methods, ground_truth):
    results_file = f"results/method_level/BM25/{bug_report_folder}.json"
    # Load existing results if the file exists
    if os.path.exists(results_file):
        with open(results_file, "r") as f:
            try:
                results = json.load(f)
            except json.JSONDecodeError:
                results = []
    else:
        results = []

    # Append new data
    results.append({
        "filename": filename,
        "ranked_methods": ranked_methods,
        "transformed_ranked_methods": transformed_ranked_methods,
        "ground_truth": ground_truth.get(filename, [])
    })

    # Save the updated results back to the file
    with open(results_file, "w") as f:
        json.dump(results, f, indent=4)


# Perform fault localization for a single repository
def perform_fault_localization_single_repo(bug_reports_file, ground_truth_file, repo_path, codebase_dirs, git_branch, top_n_values):
    bug_reports = load_bug_reports(bug_reports_file)
    ground_truth = load_ground_truth(ground_truth_file)
    results = []

    # List of bug reports to skip for method level FL and for missing path
    bug_reports_to_skip_for_method_level_fl = ["HDFS-6533.json", "HADOOP-12611.json", "HADOOP-11149.json", "HDFS-6904.json", "HDFS-13635.json", "HDFS-7884.json", "HIVE-2958.json", "MAPREDUCE-3070.json", "MAPREDUCE-5451.json", "MAPREDUCE-3531.json", "MAPREDUCE-7077.json", "MAPREDUCE-6702.json", "STORM-1520.json", "STORM-2873.json", "YARN-1550.json", "YARN-2649.json", "YARN-5728.json", "YARN-7645.json", "YARN-7849.json"]
    bug_reports_to_skip_for_missing_path = ["ZOOKEEPER-1264.json", "ZOOKEEPER-1870.json", "HADOOP-6989.json", "HADOOP-8110.json", "HDFS-13039.json", "HDFS-6102.json", "HDFS-6250.json", "HDFS-6715.json", "HDFS-1085.json", "HDFS-10962.json", "HDFS-9549.json", "HDFS-2882.json", "HDFS-8276.json", "HIVE-13392.json", "HIVE-7799.json", "HIVE-5546.json", "HIVE-19248.json", "HIVE-11762.json", "MAPREDUCE-6815.json", "MAPREDUCE-2463.json", "MAPREDUCE-5260.json", "MAPREDUCE-4913.json", "MAPREDUCE-2238.json", "MAPREDUCE-3058.json", "STORM-2988.json", "STORM-2400.json", "STORM-2158.json", "YARN-370.json", "YARN-3790.json", "YARN-1903.json"]

    for report in bug_reports:
        filename = report["filename"]
        creation_time = report["creation_time"]
        bug_report_json = report["bug_report"]
        bug_report = convert_bug_report_to_string(bug_report_json)


        # Skip bug reports for method level FL and for missing path
        if filename in bug_reports_to_skip_for_method_level_fl or filename in bug_reports_to_skip_for_missing_path:
            print(f"Skipping bug report: {filename}")
            continue  # Move to the next bug report


        # Get commit version and checkout
        commit_version = get_commit_version(creation_time, repo_path, git_branch)
        if commit_version:
            checkout_to_commit(commit_version, repo_path, git_branch)

            # Index repository with BM25
            bm25, method_list = index_codebase_with_bm25(codebase_dirs)
            # print("------------------- bm25 (start) --------------------")
            # print(bm25)
            # print("------------------- bm25 (end) --------------------")
            # print("------------------- method_list (start) --------------------")
            # print(method_list)
            # print("------------------- method_list (end) --------------------")

            # Extract stack trace and keywords
            stack_trace = extract_stack_trace(bug_report)
            keywords = extract_keywords(bug_report)
            # print("------------------- stack_trace (start) --------------------")
            # print(stack_trace)
            # print("------------------- stack_trace (end) --------------------")
            # print("------------------- keywords (start) --------------------")
            # print(keywords)
            # print("------------------- keywords (end) --------------------")

            # Rank files using BM25
            ranked_methods = rank_methods_with_bm25(bm25, method_list, keywords, stack_trace, codebase_dirs)

            # Transform ranked files to ground truth format for comparison
            transformed_ranked_methods = transform_ranked_methods(ranked_methods, codebase_dirs)
            results.append((filename, transformed_ranked_methods))

            # Save to results file
            save_ranked_methods(filename, ranked_methods, transformed_ranked_methods, ground_truth)

    return evaluate_metrics(results, ground_truth, top_n_values)

# Function to compare if a ranked file ends with any ground truth file
def match_ranked_to_ground_truth(ranked_file, ground_truth_files):
    # Loop over each ground truth file
    for ground_truth_file in ground_truth_files:
        # Check if the ranked file ends with the ground truth file (i.e., matches the last part)
        if ground_truth_file.endswith(ranked_file): # changed for method level FL
            return True
    return False

# Evaluation function for MAP, MRR, and Top N scores
def evaluate_metrics(results, ground_truth, top_n_values):
    metrics = {"MAP": [], "MRR": [], "Top@N": {n: 0 for n in top_n_values}, "total_reports": 0}
    total_reports = 0

    for filename, ranked_methods in results:
        ground_truth_files = ground_truth.get(filename, [])
        if not ground_truth_files:
            continue

        total_reports += 1
        relevant_found = 0
        precision_sum = 0
        relevant_within_top_n = {n: False for n in top_n_values}

        for rank, file in enumerate(ranked_methods, start=1):
            # print("------------------- rank, methods (start) --------------------")
            # print(f"{rank}: {file}")
            # print("------------------- rank, methods (end) --------------------")
            # if file in ground_truth_files:
            # # Check if any ranked file ends with ground truth file (using endswith)
            if match_ranked_to_ground_truth(file, ground_truth_files):
                relevant_found += 1
                precision_sum += relevant_found / rank
                if relevant_found == 1:
                    metrics["MRR"].append(1 / rank)
                for n in top_n_values:
                    if rank <= n and not relevant_within_top_n[n]:
                        metrics["Top@N"][n] += 1
                        relevant_within_top_n[n] = True

        avg_precision = precision_sum / relevant_found if relevant_found > 0 else 0
        metrics["MAP"].append(avg_precision)

    metrics["total_reports"] = total_reports
    # Print Top@N for each repo
    print(f"Final Top@N totals: {metrics['Top@N']}")
    return metrics

# Aggregate results across multiple repositories
# def aggregate_results(results_list, top_n_values):
#     total_reports = sum(result["total_reports"] for result in results_list)
#     overall_metrics = {"MAP": 0, "MRR": 0, "Top@N": {n: 0 for n in top_n_values}}

#     for result in results_list:
#         overall_metrics["MAP"] += sum(result["MAP"]) / len(result["MAP"]) * result["total_reports"]
#         overall_metrics["MRR"] += sum(result["MRR"]) / len(result["MRR"]) * result["total_reports"]
#         for n in top_n_values:
#             overall_metrics["Top@N"][n] += result["Top@N"][n]

#     # Print Top@N accross all repositories
#     print("\nTotal Top@N counts across all repositories (raw counts):")
#     for n in top_n_values:
#         print(f"Top-{n}: {overall_metrics['Top@N'][n]}")

#     overall_metrics["MAP"] /= total_reports
#     overall_metrics["MRR"] /= total_reports
#     for n in top_n_values:
#         overall_metrics["Top@N"][n] /= total_reports

#     return overall_metrics

def aggregate_results(results_list, top_n_values):
    total_reports = sum(result["total_reports"] for result in results_list)
    overall_metrics = {"MAP": 0, "MRR": 0, "Top@N": {n: 0 for n in top_n_values}}

    for result in results_list:
        if len(result["MAP"]) > 0:  # Check to avoid division by zero
            overall_metrics["MAP"] += sum(result["MAP"]) / len(result["MAP"]) * result["total_reports"]
        overall_metrics["MRR"] += (sum(result["MRR"]) / len(result["MRR"]) * result["total_reports"]) if len(result["MRR"]) > 0 else 0
        for n in top_n_values:
            overall_metrics["Top@N"][n] += result["Top@N"][n]

    # Print Top@N accross all repositories
    print("\nTotal Top@N counts across all repositories (raw counts):")
    top_n_counts = {}
    for n in top_n_values:
        print(f"Top-{n}: {overall_metrics['Top@N'][n]}")
        top_n_counts[f"Top-{n}"] = overall_metrics['Top@N'][n]

    if total_reports > 0:
        overall_metrics["MAP"] /= total_reports
        overall_metrics["MRR"] /= total_reports
        for n in top_n_values:
            overall_metrics["Top@N"][n] /= total_reports

    return overall_metrics, top_n_counts

# Main function to process all repositories
def process_repositories(repositories, top_n_values):
    results_list = []
    for repo_config in repositories:
        result = perform_fault_localization_single_repo(
            repo_config["bug_reports"],
            repo_config["ground_truth"],
            repo_config["repo_path"],
            repo_config["codebase_dir"],
            repo_config["git_branch"],
            top_n_values
        )
        results_list.append(result)

    overall_metrics, top_n_counts = aggregate_results(results_list, top_n_values)

    # Save overall result to the output file
    results_file = f"results/method_level/BM25/{bug_report_folder}.json"
    # Load existing results if the file exists
    if os.path.exists(results_file):
        with open(results_file, "r") as f:
            try:
                overall_results = json.load(f)
            except json.JSONDecodeError:
                overall_results = []
    else:
        overall_results = []

    overall_results.append({
        "bug_report_folder": bug_report_folder,
        "overall_metrics": overall_metrics,
        "top@N_value_counts": top_n_counts
    })
    # Save the updated results back to the file
    with open(results_file, "w") as f:
        json.dump(overall_results, f, indent=4)


    print("\nOverall Metrics:")
    print(f"Mean Average Precision (MAP): {overall_metrics['MAP']}")
    print(f"Mean Reciprocal Rank (MRR): {overall_metrics['MRR']}")
    for n in top_n_values:
        print(f"Top-{n} Accuracy: {overall_metrics['Top@N'][n]}")

# Example repository configuration and usage
bug_report_folder = 'data/agentic_llm_bug_reports'
repositories = [
    {"bug_reports": f"{bug_report_folder}/Zookeeper.json", "ground_truth": "data/ground_truth/method_level/Zookeeper.json", "repo_path": "Projects/zookeeper", "codebase_dir": ['Projects/zookeeper/src/java/main'], "git_branch": 'master'},
    {"bug_reports": f"{bug_report_folder}/ActiveMQ.json", "ground_truth": "data/ground_truth/method_level/ActiveMQ.json", "repo_path": "Projects/activemq", "codebase_dir": ['Projects/activemq/activemq-broker/src/main/java', 'Projects/activemq/activemq-client/src/main/java', 'Projects/activemq/activemq-core/src/main/java', 'Projects/activemq/activemq-jdbc-store/src/main/java', 'Projects/activemq/activemq-kahadb-store/src/main/java', 'Projects/activemq/activemq-karaf/src/main/java', 'Projects/activemq/activemq-optional/src/main/java', 'Projects/activemq/kahadb/src/main/java'], "git_branch": 'main'},
    {"bug_reports": f"{bug_report_folder}/Hadoop.json", "ground_truth": "data/ground_truth/method_level/Hadoop.json", "repo_path": "Projects/hadoop", "codebase_dir": ['Projects/hadoop/hadoop-common-project/hadoop-auth/src/main/java', 'Projects/hadoop/hadoop-common-project/hadoop-common/src/main/java', 'Projects/hadoop/hadoop-common-project/hadoop-kms/src/main/java', 'Projects/hadoop/hadoop-common-project/hadoop-nfs/src/main/java', 'Projects/hadoop/hadoop-hdfs-project/hadoop-hdfs/src/main/java', 'Projects/hadoop/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-app/src/main/java', 'Projects/hadoop/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java', 'Projects/hadoop/hadoop-tools/hadoop-aws/src/main/java', 'Projects/hadoop/hadoop-tools/hadoop-azure/src/main/java', 'Projects/hadoop/hadoop-tools/hadoop-distcp/src/main/java', 'Projects/hadoop/hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-nodemanager/src/main/java', 'Projects/hadoop/src/java'], "git_branch": 'trunk'},
    {"bug_reports": f"{bug_report_folder}/HDFS.json", "ground_truth": "data/ground_truth/method_level/HDFS.json", "repo_path": "Projects/hadoop", "codebase_dir": ['Projects/hadoop/hadoop-common-project/hadoop-common/src/main/java', 'Projects/hadoop/hadoop-common-project/hadoop-nfs/src/main/java', 'Projects/hadoop/hadoop-hdfs-project/hadoop-hdfs-client/src/main/java', 'Projects/hadoop/hadoop-hdfs-project/hadoop-hdfs-nfs/src/main/java', 'Projects/hadoop/hadoop-hdfs-project/hadoop-hdfs/src/main/java', 'Projects/hadoop/hdfs/src/java', 'Projects/hadoop/src/core', 'Projects/hadoop/src/hdfs'], "git_branch": 'trunk'},
    {"bug_reports": f"{bug_report_folder}/Hive.json", "ground_truth": "data/ground_truth/method_level/Hive.json", "repo_path": "Projects/hive", "codebase_dir": ['Projects/hive/common/src/java', 'Projects/hive/hbase-handler/src/java', 'Projects/hive/hcatalog/core/src/main/java', 'Projects/hive/hcatalog/server-extensions/src/main/java', 'Projects/hive/hcatalog/webhcat/svr/src/main/java', 'Projects/hive/metastore/src/java', 'Projects/hive/orc/src/java', 'Projects/hive/ql/src/java', 'Projects/hive/serde/src/java', 'Projects/hive/service/src/java', 'Projects/hive/shims/0/20S/src/main/java', 'Projects/hive/shims/0/23/src/main/java', 'Projects/hive/shims/common/src/main/java', 'Projects/hive/shims/src/0/20/java', 'Projects/hive/shims/src/common-secure/java', 'Projects/hive/spark-client/src/main/java', 'Projects/hive/standalone-metastore/src/main/java'], "git_branch": 'master'},
    {"bug_reports": f"{bug_report_folder}/MAPREDUCE.json", "ground_truth": "data/ground_truth/method_level/MAPREDUCE.json", "repo_path": "Projects/hadoop", "codebase_dir": ['Projects/hadoop/hadoop-common-project/hadoop-common/src/main/java', 'Projects/hadoop/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-app/src/main/java', 'Projects/hadoop/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-common/src/main/java', 'Projects/hadoop/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-core/src/main/java', 'Projects/hadoop/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-hs/src/main/java', 'Projects/hadoop/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-jobclient/src/main/java', 'Projects/hadoop/hadoop-mapreduce-project/hadoop-yarn/hadoop-yarn-api/src/main/java', 'Projects/hadoop/hadoop-mapreduce-project/hadoop-yarn/hadoop-yarn-common/src/main/java', 'Projects/hadoop/hadoop-mapreduce-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-nodemanager/src/main/java', 'Projects/hadoop/hadoop-mapreduce-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/main/java', 'Projects/hadoop/hadoop-mapreduce-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-web-proxy/src/main/java', 'Projects/hadoop/hadoop-mapreduce-project/src/contrib/gridmix/src/java', 'Projects/hadoop/hadoop-mapreduce-project/src/tools', 'Projects/hadoop/hadoop-tools/hadoop-streaming/src/main/java', 'Projects/hadoop/mapreduce/src/java', 'Projects/hadoop/src/contrib/fairscheduler/src/java', 'Projects/hadoop/src/core', 'Projects/hadoop/src/examples', 'Projects/hadoop/src/mapred'], "git_branch": 'trunk'},
    {"bug_reports": f"{bug_report_folder}/Storm.json", "ground_truth": "data/ground_truth/method_level/Storm.json", "repo_path": "Projects/storm", "codebase_dir": ['Projects/storm/examples/storm-loadgen/src/main/java', 'Projects/storm/external/storm-hdfs-blobstore/src/main/java', 'Projects/storm/external/storm-hdfs/src/main/java', 'Projects/storm/external/storm-kafka-client/src/main/java', 'Projects/storm/storm-client/src/jvm', 'Projects/storm/storm-core/src/jvm', 'Projects/storm/storm-server/src/main/java', 'Projects/storm/storm-webapp/src/main/java'], "git_branch": 'master'},
    {"bug_reports": f"{bug_report_folder}/YARN.json", "ground_truth": "data/ground_truth/method_level/YARN.json", "repo_path": "Projects/hadoop", "codebase_dir": ['Projects/hadoop/hadoop-common-project/hadoop-common/src/main/java', 'Projects/hadoop/hadoop-mapreduce-project/hadoop-mapreduce-client/hadoop-mapreduce-client-app/src/main/java', 'Projects/hadoop/hadoop-tools/hadoop-sls/src/main/java', 'Projects/hadoop/hadoop-yarn-project/hadoop-yarn/hadoop-yarn-api/src/main/java', 'Projects/hadoop/hadoop-yarn-project/hadoop-yarn/hadoop-yarn-applications/hadoop-yarn-applications-distributedshell/src/main/java', 'Projects/hadoop/hadoop-yarn-project/hadoop-yarn/hadoop-yarn-applications/hadoop-yarn-applications-unmanaged-am-launcher/src/main/java', 'Projects/hadoop/hadoop-yarn-project/hadoop-yarn/hadoop-yarn-applications/hadoop-yarn-services/hadoop-yarn-services-core/src/main/java', 'Projects/hadoop/hadoop-yarn-project/hadoop-yarn/hadoop-yarn-client/src/main/java', 'Projects/hadoop/hadoop-yarn-project/hadoop-yarn/hadoop-yarn-common/src/main/java', 'Projects/hadoop/hadoop-yarn-project/hadoop-yarn/hadoop-yarn-registry/src/main/java', 'Projects/hadoop/hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-applicationhistoryservice/src/main/java', 'Projects/hadoop/hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-common/src/main/java', 'Projects/hadoop/hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-nodemanager/src/main/java', 'Projects/hadoop/hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-resourcemanager/src/main/java', 'Projects/hadoop/hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-timelineservice/src/main/java', 'Projects/hadoop/hadoop-yarn-project/hadoop-yarn/hadoop-yarn-server/hadoop-yarn-server-web-proxy/src/main/java'], "git_branch": 'trunk'}
]


top_n_values = [1, 3, 5, 10]
process_repositories(repositories, top_n_values)
