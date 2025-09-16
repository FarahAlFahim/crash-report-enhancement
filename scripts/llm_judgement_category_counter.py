import os
import json
from collections import defaultdict

# Input configuration
bug_report_variation = 'results/llm_judge/developer_written_bug_reports'
file_paths = [
    f"{bug_report_variation}/Zookeeper.json",
    f"{bug_report_variation}/ActiveMQ.json",
    f"{bug_report_variation}/Hadoop.json",
    f"{bug_report_variation}/HDFS.json",
    f"{bug_report_variation}/Hive.json",
    f"{bug_report_variation}/MAPREDUCE.json",
    f"{bug_report_variation}/Storm.json",
    f"{bug_report_variation}/YARN.json"
]

# Define expected categories and their possible values
categories_with_options = {
    "root_cause_identification": ["precise", "partial", "missing"],
    "fix_suggestion": ["correct", "alternative fix", "preventive", "missing"],
    "problem_location_identification": ["precise", "partial", "missing"],
    "wrong_information": ["yes", "no"]
}

# Possible sub-categories for 'partial' levels
partial_sub_categories = [
    "Direct Caller/Callee", "2-Hop Caller/Callee", "3-Hop Caller/Callee",
    "3+ Hop Caller/Callee", "Same Class or Module", "Shared Stack Trace Context",
    "Buggy Method", "null"
]


# Initialize counts
category_counts = {
    category: defaultdict(int) for category in categories_with_options
}

# Initialize nested sub-category counts only for root_cause and problem_location
partial_sub_category_counts = {
    "root_cause_identification": defaultdict(int),
    "problem_location_identification": defaultdict(int)
}

# # ------------------ List of Manual Evaluation ------------------ #
# manual = ["ZOOKEEPER-1864.json", "ZOOKEEPER-2297.json", "ZOOKEEPER-2581.json", "HDFS-4558.json", "HDFS-8055.json", "HDFS-2245.json", "HDFS-13721.json", "HDFS-11827.json", "HDFS-10715.json", "HDFS-5710.json", "HDFS-12363.json",  "HADOOP-11878.json", "HADOOP-10937.json", "HADOOP-15121.json", "YARN-5918.json", "YARN-4763.json", "YARN-2414.json", "YARN-7786.json", "YARN-4152.json", "YARN-3537.json", "YARN-1032.json", "YARN-2813.json", "YARN-3369.json", "YARN-4235.json", "YARN-7511.json", "YARN-7249.json",  "MAPREDUCE-4048.json", "MAPREDUCE-6361.json", "MAPREDUCE-5260.json", "MAPREDUCE-4144.json", "MAPREDUCE-6492.json", "MAPREDUCE-6554.json", "STORM-2443.json", "STORM-2275.json", "STORM-2682.json", "STORM-3213.json", "AMQ-3622.json", "HIVE-6537.json", "HIVE-14303.json", "HIVE-15755.json", "HIVE-19130.json", "HIVE-13090.json", "HIVE-15778.json", "HIVE-6984.json", "HIVE-13065.json", "HIVE-11470.json", "HIVE-1547.json", "HIVE-1712.json", "HIVE-10816.json", "HIVE-16845.json"]
# # ------------------ List of Manual Evaluation ------------------ #

# List of Bug Reports to exclude 
bug_reports_to_skip_for_missing_path = ["ZOOKEEPER-1264.json", "ZOOKEEPER-1870.json", "HADOOP-6989.json", "HADOOP-8110.json", "HDFS-13039.json", "HDFS-6102.json", "HDFS-6250.json", "HDFS-6715.json", "HDFS-1085.json", "HDFS-10962.json", "HDFS-9549.json", "HDFS-2882.json", "HDFS-8276.json", "HIVE-13392.json", "HIVE-7799.json", "HIVE-5546.json", "HIVE-19248.json", "HIVE-11762.json", "MAPREDUCE-6815.json", "MAPREDUCE-2463.json", "MAPREDUCE-5260.json", "MAPREDUCE-4913.json", "MAPREDUCE-2238.json", "MAPREDUCE-3058.json", "STORM-2988.json", "STORM-2400.json", "STORM-2158.json", "YARN-370.json", "YARN-3790.json", "YARN-1903.json"]

# Process each file
for path in file_paths:
    if not os.path.exists(path):
        print(f"Warning: File not found {path}")
        continue

    with open(path, "r") as f:
        data = json.load(f)
    
    for report in data:

        # # ------------------ List of Manual Evaluation ------------------ #
        # if report.get("filename") not in manual:
        #     continue  # Skip if not in manual list
        # # ------------------ List of Manual Evaluation ------------------ #

        # List of Bug Reports to exclude 
        if report.get("filename") in bug_reports_to_skip_for_missing_path:
            continue  # Skip if in bug_reports_to_skip_for_missing_path


        llm_judgement = report.get("llm_judgement", {})
        for category, options in categories_with_options.items():
            # # for categories
            # value = llm_judgement.get(category, "missing").strip().lower()
            # # Normalize invalid values to 'missing'
            # if value not in options:
            #     value = "missing"
            # category_counts[category][value] += 1

            # # for sub-categories
            value = llm_judgement.get(category, "missing")
            if isinstance(value, dict):  # Nested: { "level": ..., "sub_category": ... }
                level = value.get("level", "missing").strip().lower()
                sub = value.get("sub_category", "null")
                if level not in options:
                    level = "missing"
                category_counts[category][level] += 1

                # Count partial sub-categories only for selected categories
                if level == "partial" and category in partial_sub_category_counts:
                    partial_sub_category_counts[category][sub] += 1

            else:  # Simple string value
                val = value.strip().lower()
                if val not in options:
                    val = "missing"
                category_counts[category][val] += 1

# Print results [for categories only]
for category, counts in category_counts.items():
    print(f"\nCategory: {category}")
    for option in categories_with_options[category]:
        print(f"  {option}_count = {counts[option]}")

    # If partial counts exist for this category, print sub-categories
    if category in partial_sub_category_counts:
        for sub in partial_sub_categories:
            count = partial_sub_category_counts[category][sub]
            print(f"  partial_{sub} = {count}")
