import json
import re
from langchain import PromptTemplate
from langchain_core.prompts import PromptTemplate
from langchain.chat_models import ChatOpenAI
from langchain.chains import LLMChain


def extract_full_method_paths(stack_trace: str):
    """
    Extracts fully qualified method paths from a stack trace.
    Example: 'org.apache.zookeeper.server.quorum.QuorumPeer.setQuorumVerifier'
    """
    pattern = re.compile(r'((?:[a-zA-Z_][\w$]*\.)+[A-Z][\w$]*\.[a-zA-Z_][\w$]*)\s*\(.*?\)')
    return set(match.strip() for match in pattern.findall(stack_trace))


def filter_source_code_by_full_paths(source_code_dict, full_paths):
    filtered_dict = {}
    for method_path in full_paths:
        for key in source_code_dict:
            if key.endswith(method_path):
                filtered_dict[key] = source_code_dict[key]
    return filtered_dict







# Non-META Prompt
template = '''
You are a professional bug report assistant. Your task is to enhance a given bug report by analyzing both the original developer-written bug report and the relevant source code methods mentioned in the stack trace to identify the root cause of the issue.

Return the enhanced bug report in JSON format:

```json
{{
    "Title": "<Bug title>",
    "Description": "<Improved description based on analysis>",
    "StackTrace": "string or array of stack trace lines",
    "RootCause": "<Identified root cause>",
    "StepsToReproduce": ["<Step-by-step reproduction guide>"] or null,
    "ExpectedBehavior": "<Correct system behavior>",
    "ObservedBehavior": "<Actual faulty behavior>",
    "Suggestions": "<Possible fixes or mitigation steps>",
    "problem_location": {{
        "files": ["file1.java", "file2.java"],
        "classes": ["com.example.ClassA", "com.example.ClassB"],
        "methods": ["ClassA.methodX", "ClassB.methodY"]
    }},
    "possible_fix": "[Suggested resolution, including code changes if necessary.]"
}}



## You are given the Developer-Written Bug Report below:

{bug_report}



## You are given the Source Code Methods below:

{source_code_methods}
'''



prompt = PromptTemplate.from_template(template)
llm = ChatOpenAI(model='gpt-4o-mini', temperature = 0)

chain = LLMChain(llm=llm, prompt=prompt)





# File paths
input_file = "data/source_code_data/Zookeeper.json"
output_file = "data/direct_llm_bug_reports/Zookeeper.json"



with open(input_file, 'r') as f:
    data = json.load(f)

output_data = []

for item in data:
    filename = item['filename']
    creation_time = item['creation_time']
    dev_written_bug_report = item.get("bug_report", {})
    stack_trace = item.get("stack_trace", "")
    source_code = item.get("source_code", {})

    # Extract method paths from stack trace
    method_paths = extract_full_method_paths(stack_trace)

    # Filter source code dictionary using endswith matching
    source_code_methods = filter_source_code_by_full_paths(source_code, method_paths)

    # processed_data.append({
    #     "filename": item.get("filename"),
    #     "bug_report": bug_report,
    #     "stack_trace": stack_trace,
    #     "method_paths_from_stack": list(method_paths),
    #     "relevant_source_code": source_code_methods
    # })


    # Generate improved bug report
    bug_report_str = chain.run({'bug_report': dev_written_bug_report, 'source_code_methods': source_code_methods})
    # print("--------------------------------------------------------------------")
    # print(bug_report_str)
    # print("--------------------------------------------------------------------")


    # Parse the bug report JSON from the generated string
    try:
        # Remove any markdown-style code block indicators (` ```json `) if present
        bug_report = json.loads(bug_report_str.replace("```json\n", "").replace("\n```", ""))
    except json.JSONDecodeError:
        print(f"Failed to parse JSON for filename: {filename}")
        continue  # Skip this entry if JSON parsing fails

    
    # Add to output data
    output_data.append({
        'filename': filename,
        'creation_time': creation_time,
        'bug_report': bug_report
    })

    # Write to output file after each bug report
    with open(output_file, "w") as outfile:
        json.dump(output_data, outfile, indent=4)
    print(f"Progress saved to {output_file}")


# # Write the summarized bug reports to a new JSON file
# with open(f"{output_file}", "w") as outfile:
#     json.dump(output_data, outfile, indent=4)

print(f"Bug reports have been generated and saved to '{output_file}'")















