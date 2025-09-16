import os
import json
import subprocess
from datetime import datetime
from pathlib import Path
import javalang
from openai import OpenAI
from langchain_openai import ChatOpenAI
from langchain import PromptTemplate
from langchain_core.prompts import PromptTemplate
from langchain.chat_models import ChatOpenAI
from langchain.chains import LLMChain




# Source Code Methods [from call graph of Stack Trace]
def get_source_code_dict(filename, source_code_file_path):
    with open(source_code_file_path, 'r') as f:
        data = json.load(f)
    
    for entry in data:
        if entry['filename'] == filename:
            return entry.get('source_code', {})
    
    return {}

# Code difference methods previously extracted [before and after commit]
def get_code_diff_from_file(filename, input_file_path):
    with open(input_file_path, "r") as f:
        data = json.load(f)
    for item in data:
        if item["filename"] == filename:
            return item.get("code_diff", {})
    return {}





def call_llm_judge(bug_report, ground_truth_methods, code_difference, source_code_methods):
    template = """
    You are a software engineering expert evaluating a bug report based on its ability to accurately describe and diagnose a real bug. You will be given:

    - A generated bug report
    - A list of method names where the bug actually occurred (ground truth)
    - The source code of those ground truth methods before and after the fix (representing the developer's actual fix)
    - Source code methods from the call dependency of the methods of stack traces

    Evaluate the bug report based on the following four criteria:

    1. **Root Cause Identification**  
    - **Precise**: Identifies the exact root cause related to any of the ground truth methods.
    - **Partial**: Mentions which error occurred and also mentions where the error occurred. But, it is not the actual root cause at the ground truth method(s). But refers to closely related methods, which you should classify into one of the following sub-categories: 
        - **Direct Caller/Callee**: A method that directly calls or is called by a ground truth method.  
        - **2-Hop Caller/Callee**: A method that is 2 levels away in the call graph from a ground truth method.  
        - **3-Hop Caller/Callee**: A method that is 3 levels away in the call graph from a ground truth method.
        - **3+ Hop Caller/Callee**: A method that is more than 3 levels away in the call graph from a ground truth method.    
        - **Same Class or Module**: A method in the same class or module as the ground truth method.  
        - **Shared Stack Trace Context**: A method mentioned in the same stack trace as the ground truth method. 
        - **Buggy Method**: A method Points to the method where the error occurred, but not where the actual fix was made.
    - **Missing**: No such fields or no information about the cause of the bug. If field such as `RootCause` appears in the bug report, it should not be in "Missing" category. Sometimes, even if the `RootCause` field is missing in the bug report, it can be mentioned in the `Description` field.

    2. **Fix Suggestion**  
    - **Correct**: Matches the developer’s fix as seen in the “after” version of the method. In case, there is no `Suggestions` or `problem_location` field in the bug report, check the `Description` field carefully to find if any fixing suggestions exists.
    - **Alternative Fix**: Different than the developer’s fix, but would likely resolve the bug in the same way. In case, there is no `Suggestions` or `problem_location` field in the bug report, check the `Description` field carefully to find if any fixing suggestions exists.
    - **Preventive**: Would prevent or mitigate the bug at any of the buggy locations. It can be as simple as implementing conditions to prevent the error. In case, there is no `Suggestions` or `problem_location` field in the bug report, check the `Description` field carefully to find if any fixing suggestions exists.
    - **Missing**: No suggestions provided to fix the bug. If fields such as `Suggestions` or `possible_fix` appear in the bug report, it should not be in "Missing" category.

    3. **Problem Location Identification**  
    - **Precise**: The `problem_location` field mentions at least one method from the ground truth list. If the `problem_location` field is missing, the `Title` field or the `Description` field might contain some information about it, but do not consider it, if it is inside stack traces of the `Description` field as that is not a direct problem location suggestion. Also, do not consider it as "Precise" if the `Title` or the `Description` field only mentions the ground truth class, but not ground truth methods. In such cases, it can be considered as 'Partial' with relevant sub-categories. 
    - **Partial**: The `problem_location` field mentions methods related to the problem or related to methods mentioned in the stack traces, but not from the ground truth list. If the `problem_location` field is missing, the `Title` field or the `Description` field might contain some information about it, but do not consider it, if it is inside stack traces of the `Description` field as that is not a direct problem location suggestion. For any of the partial cases, you should classify into one of the following sub-categories: 
        - **Direct Caller/Callee**: A method that directly calls or is called by a ground truth method.  
        - **2-Hop Caller/Callee**: A method that is 2 levels away in the call graph from a ground truth method.  
        - **3-Hop Caller/Callee**: A method that is 3 levels away in the call graph from a ground truth method.
        - **3+ Hop Caller/Callee**: A method that is more than 3 levels away in the call graph from a ground truth method. 
        - **Same Class or Module**: A method in the same class or module as the ground truth method.  
        - **Shared Stack Trace Context**: A method mentioned in the same stack trace as the ground truth method. 
        - **Buggy Method**: A method Points to the method where the error occurred, but not where the actual fix was made.
    - **Missing**: No methods or locations identified even from the `Title` or the `Description` fields of the bug report. If field such as `problem_location` appears in the bug report, it should not be in "Missing" category. Sometimes, even if the `problem_location` field is missing in the bug report, it can be mentioned in the `Title` or the `Description` fields.

    4. **Wrong Information**  
    - **Yes**: The bug report contains statements that are completely unrelated or incorrect.
    - **No**: All information appears grounded in the context of the bug.

    ---

    ### Bug Report:
    {bug_report}

    ---

    ### Ground Truth Method Names:
    {ground_truth_methods}

    ---

    ### Ground Truth Methods (Before and After Code):

    {code_difference}

    ---

    ### Source Code Methods (from the call dependency of the methods of stack traces):

    {source_code_methods}

    ---



    Provide your response in the following JSON format:
    ```json
    {{
        "root_cause_identification": {{
            "level": "[Precise | Partial | Missing]",
            "sub_category": "[Direct Caller/Callee | 2-Hop Caller/Callee | 3-Hop Caller/Callee | 3+ Hop Caller/Callee | Same Class or Module | Shared Stack Trace Context | Buggy Method]"
        }},
        "fix_suggestion": "[Correct | Alternative Fix | Preventive | Missing]",
        "problem_location_identification": {{
            "level": "[Precise | Partial | Missing]",
            "sub_category": "[Direct Caller/Callee | 2-Hop Caller/Callee | 3-Hop Caller/Callee | 3+ Hop Caller/Callee | Same Class or Module | Shared Stack Trace Context | Buggy Method]"
        }},
        "wrong_information": "[Yes | No]",
        "explanation_of_judgement": "<brief justification for each evaluation>"
    }}

    """

    prompt = PromptTemplate.from_template(template)
    llm = ChatOpenAI(model='gpt-4o', temperature = 0)

    chain = LLMChain(llm=llm, prompt=prompt)
    return chain.run({'bug_report': bug_report, 'ground_truth_methods': ground_truth_methods, 'code_difference': code_difference, 'source_code_methods': source_code_methods})







# File Path
bug_report_path = "data/direct_llm_bug_reports/Zookeeper.json"

# constant paths
ground_truth_methods_path = "data/ground_truth/method_level/Zookeeper.json"
code_difference_path = "results/llm_judge/developer_written_bug_reports/Zookeeper.json"
source_code_methods_from_call_graph = "data/source_code_data/Zookeeper.json"

# Output File Path
output_file = "results/llm_judge/direct_llm/Zookeeper.json"



with open(bug_report_path) as f:
    bug_reports = json.load(f)
with open(ground_truth_methods_path) as f:
    gt_methods = json.load(f)



output_data = []


processed_files = {entry['filename'] for entry in output_data}

# List of bug reports to skip for method level FL
bug_reports_to_skip_for_method_level_fl = ["HDFS-6533.json", "HADOOP-12611.json", "HADOOP-11149.json", "HDFS-6904.json", "HDFS-13635.json", "HDFS-7884.json", "HIVE-2958.json", "MAPREDUCE-3070.json", "MAPREDUCE-5451.json", "MAPREDUCE-3531.json", "MAPREDUCE-7077.json", "MAPREDUCE-6702.json", "STORM-1520.json", "STORM-2873.json", "YARN-1550.json", "YARN-2649.json", "YARN-5728.json", "YARN-7645.json", "YARN-7849.json"]
bug_reports_to_skip_for_missing_path = ["ZOOKEEPER-1264.json", "ZOOKEEPER-1870.json", "HADOOP-6989.json", "HADOOP-8110.json", "HDFS-13039.json", "HDFS-6102.json", "HDFS-6250.json", "HDFS-6715.json", "HDFS-1085.json", "HDFS-10962.json", "HDFS-9549.json", "HDFS-2882.json", "HDFS-8276.json", "HIVE-13392.json", "HIVE-7799.json", "HIVE-5546.json", "HIVE-19248.json", "HIVE-11762.json", "MAPREDUCE-6815.json", "MAPREDUCE-2463.json", "MAPREDUCE-5260.json", "MAPREDUCE-4913.json", "MAPREDUCE-2238.json", "MAPREDUCE-3058.json", "STORM-2988.json", "STORM-2400.json", "STORM-2158.json", "YARN-370.json", "YARN-3790.json", "YARN-1903.json"]


for report in bug_reports:
    filename = report['filename']

    if filename in processed_files:
        continue

    # Skip bug reports for method level FL and for missing path
    if filename in bug_reports_to_skip_for_method_level_fl or filename in bug_reports_to_skip_for_missing_path:
        print(f"Skipping bug report: {filename}")
        continue  # Move to the next bug report

    creation_time = report['creation_time']
    bug_report = report['bug_report']
    method_list = gt_methods.get(filename, [])
    

    source_code_methods = get_source_code_dict(filename, source_code_methods_from_call_graph)
    code_diff = get_code_diff_from_file(filename, code_difference_path)


    judgement_str = call_llm_judge(bug_report, method_list, code_diff, source_code_methods)
    # Parse the judgement reponse JSON from the generated string
    try:
        # Remove any markdown-style code block indicators (` ```json `) if present
        judgement = json.loads(judgement_str.replace("```json\n", "").replace("\n```", ""))
    except json.JSONDecodeError:
        print(f"Failed to parse JSON for filename: {filename}")
        continue  # Skip this entry if JSON parsing fails


    # Add to output data
    output_data.append({
        'filename': filename,
        'code_diff': code_diff,
        'llm_judgement': judgement
    })

    # Write to output file after each bug report
    with open(output_file, "w") as outfile:
        json.dump(output_data, outfile, indent=4)
    print(f"Progress saved to {output_file}")


print(f"LLM Judgement have been generated and saved to '{output_file}'")